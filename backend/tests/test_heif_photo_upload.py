import io
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from PIL import Image

from app.api.media import _validate_image_data
from app import worker
from app.models import LocationRegion, User
from app.security import hash_password


def collection():
    output = io.BytesIO()
    Image.new("RGB", (32, 24), "red").save(
        output, format="HEIF", save_all=True,
        append_images=[Image.new("RGB", (48, 32), "blue")], primary_index=1,
    )
    return output.getvalue()


def mpo_collection():
    output = io.BytesIO()
    Image.new("RGB", (48, 32), "blue").save(
        output, format="MPO", save_all=True,
        append_images=[Image.new("RGB", (16, 12), "red")],
    )
    return output.getvalue()


@pytest.mark.parametrize("image_data,mime", [(collection, "image/heic"), (mpo_collection, "image/jpeg")])
def test_heif_collection_upload_uses_primary_photo(image_data, mime):
    assert _validate_image_data(image_data(), 60_000_000, mime) == (48, 32)


@pytest.mark.parametrize("image_data", [collection, mpo_collection])
def test_worker_processes_only_primary_photo_from_heif_collection(tmp_path, monkeypatch, image_data):
    photo = SimpleNamespace(
        id=uuid4(), status="processing", storage_name="photo", original_name="source.heic",
        perceptual_hash=None,
    )
    quarantine = tmp_path / ".quarantine"
    quarantine.mkdir()
    (quarantine / photo.original_name).write_bytes(image_data())

    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return photo
        def commit(self): pass
        def rollback(self): pass

    monkeypatch.setattr(worker, "SessionLocal", Session)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(media_root=tmp_path, upload_max_pixels=60_000_000))
    worker._make_variants(photo.id)

    assert photo.status == "ready"
    assert (photo.width, photo.height) == (48, 32)
    for edge in (320, 768, 1600):
        with Image.open(tmp_path / "photo" / f"{edge}.webp") as result:
            assert result.size == (48, 32)
            assert result.getpixel((20, 20))[2] > 200
            assert not result.getexif()
    assert not (quarantine / photo.original_name).exists()


@pytest.mark.parametrize("image_data,mime,filename", [(collection, "image/heic", "spatial.heic"), (mpo_collection, "image/jpeg", "IMG_8730.jpeg")])
def test_absent_vehicle_can_be_created_with_heif_photo_and_submitted(integration, image_data, mime, filename):
    with integration["SessionLocal"]() as db:
        region = LocationRegion(slug=f"photo-test-region-{filename}", name="Тестовая область")
        db.add_all([region, User(email=f"photo-test-{filename.lower()}@example.com", display_name="Photo test", status="active", password_hash=hash_password("local-photo-test-password"))])
        db.commit()
        region_id = str(region.id)
    client = integration["client"]
    login = client.post("/api/v1/auth/login", json={"email": f"photo-test-{filename.lower()}@example.com", "password": "local-photo-test-password"})
    assert login.status_code == 200, login.text
    headers = {"X-CSRF-Token": login.json()["csrf_token"], "Idempotency-Key": f"manual-photo-draft-{filename}"}
    result = client.post("/api/v1/listings/drafts", headers=headers, json={
        "seller_type": "private", "manual_make": "Редкая марка", "manual_model": "Редкая модель",
        "year": 2020, "mileage_km": 80000, "fuel": "petrol", "transmission": "automatic", "drive": "front",
        "condition": "used", "description": "Изолированное тестовое объявление", "price": {"amount": "10000", "currency": "BYN"},
        "region_id": region_id, "manual_city": "Тестовый город", "contact_phone": "+375290000000",
    })
    assert result.status_code == 200, result.text
    listing_id = result.json()["listing"]["id"]
    headers["Idempotency-Key"] = f"manual-photo-upload-{filename}"
    result = client.post(f"/api/v1/listings/{listing_id}/photos", headers=headers, files={"file": (filename, image_data(), mime)})
    assert result.status_code == 200, result.text
    worker._make_variants(UUID(result.json()["id"]))
    latest = client.get(f"/api/v1/listings/{listing_id}").json()["listing"]
    headers["Idempotency-Key"] = f"manual-photo-submit-{filename}"
    result = client.post(f"/api/v1/listings/{listing_id}/submit", headers=headers, json={"expected_revision": latest["revision"]})
    assert result.status_code == 200, result.text
    assert result.json()["listing"]["status"] == "pending_review"
