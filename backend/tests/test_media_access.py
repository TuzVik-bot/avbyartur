import io
import json
import os
import shutil
import stat
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from app import worker
from app.api.media import _validate_image_data, photo_statuses, serve_photo
from app.db import get_db
from app.models import (
    ExchangeRate,
    Listing,
    ListingPhoto,
    LocationRegion,
    User,
    WorkerJob,
)
from app.security import hash_password
from app.worker import (
    PermanentJobError,
    _cleanup_retention,
    _make_variants,
    _refresh_usd_rate,
    _schedule_daily_rates,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

PASSWORD = "media-access-test-password"


def _add_user(factory, email: str, *, role: str = "user") -> uuid.UUID:
    with factory() as db:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password(PASSWORD),
            role=role,
            status="active",
        )
        db.add(user)
        db.commit()
        return user.id


def _add_listing(factory, owner_id: uuid.UUID, *, status: str = "draft") -> uuid.UUID:
    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            slug=f"media-{uuid.uuid4().hex}",
            title="Media access test",
            status=status,
        )
        db.add(listing)
        db.commit()
        return listing.id


def _login(app, email: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _jpeg(*, with_exif: bool = False, size: tuple[int, int] = (48, 32)) -> bytes:
    stream = io.BytesIO()
    options = {}
    if with_exif:
        exif = Image.Exif()
        exif[306] = "2026:09:27 01:02:03"
        exif[274] = 6
        options["exif"] = exif
    Image.new("RGB", size, (30, 80, 120)).save(stream, format="JPEG", **options)
    return stream.getvalue()


def _image_bytes(format_name: str, size: tuple[int, int] = (48, 32)) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, (30, 80, 120)).save(stream, format=format_name)
    return stream.getvalue()


class _PhotoStatusRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _PhotoStatusSession:
    def __init__(self, listing, photos):
        self.listing = listing
        self.photos = photos

    def scalar(self, statement):
        return self.listing

    def scalars(self, statement):
        return _PhotoStatusRows(self.photos)

    def get(self, model, identifier):
        if model is ListingPhoto:
            return next((photo for photo in self.photos if photo.id == identifier), None)
        if model is Listing:
            return self.listing if self.listing.id == identifier else None
        return None


@pytest.mark.parametrize("role", ["moderator", "admin"])
def test_reviewer_can_read_pending_review_photo_status_metadata_without_file_access(role):
    owner_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    listing = SimpleNamespace(id=listing_id, owner_id=owner_id, status="pending_review")
    photo = SimpleNamespace(id=photo_id, status="processing", position=2, is_cover=True)
    reviewer = SimpleNamespace(id=uuid.uuid4(), role=role)
    db = _PhotoStatusSession(listing, [photo])

    result = photo_statuses(listing_id, reviewer, db)

    assert result == {"items": [{
        "id": str(photo_id), "status": "processing", "position": 2,
        "is_cover": True, "url": None,
    }]}
    with pytest.raises(HTTPException) as failure:
        serve_photo(photo_id, 768, None, db, reviewer)
    assert failure.value.status_code == 404


@pytest.mark.parametrize("role", ["moderator", "admin"])
@pytest.mark.parametrize("status", ["draft", "paused", "active", "rejected", "blocked", "archived", "sold"])
def test_reviewer_cannot_read_photo_status_metadata_outside_pending_review(role, status):
    owner_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    listing = SimpleNamespace(id=listing_id, owner_id=owner_id, status=status, company_id=None)
    reviewer = SimpleNamespace(id=uuid.uuid4(), role=role)

    with pytest.raises(HTTPException) as failure:
        photo_statuses(listing_id, reviewer, _PhotoStatusSession(listing, []))

    assert failure.value.status_code == 404


def test_unrelated_user_cannot_read_pending_review_photo_status_metadata():
    owner_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    listing = SimpleNamespace(id=listing_id, owner_id=owner_id, status="pending_review", company_id=None)
    other_user = SimpleNamespace(id=uuid.uuid4(), role="user")

    with pytest.raises(HTTPException) as failure:
        photo_statuses(listing_id, other_user, _PhotoStatusSession(listing, []))

    assert failure.value.status_code == 404


@pytest.mark.parametrize("format_name", ["PNG", "WEBP"])
def test_animated_supported_formats_are_rejected(format_name):
    stream = io.BytesIO()
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    frames[0].save(
        stream, format=format_name, save_all=True, append_images=frames[1:],
        duration=100, loop=0,
    )

    with pytest.raises(HTTPException) as failure:
        _validate_image_data(stream.getvalue(), max_pixels=60_000_000)

    assert failure.value.status_code == 415
    assert failure.value.detail["code"] == "animated_photo"


@pytest.mark.parametrize(
    ("format_name", "content_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp"), ("HEIF", "image/heif")],
)
def test_supported_formats_are_detected_from_image_data(format_name, content_type):
    data = _image_bytes(format_name)

    assert _validate_image_data(data, max_pixels=60_000_000, content_type=content_type) == (48, 32)


@pytest.mark.parametrize(
    ("data", "content_type"),
    [
        (_image_bytes("PNG"), "image/jpeg"),
        (_image_bytes("JPEG"), "image/png"),
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
        (b"MZ\x90\x00\x03\x00", "image/jpeg"),
        (b"not an image", "image/jpeg"),
    ],
)
def test_mismatched_mime_and_non_image_payloads_are_rejected(data, content_type):
    with pytest.raises(HTTPException) as failure:
        _validate_image_data(data, max_pixels=60_000_000, content_type=content_type)

    assert failure.value.status_code == 415


def test_pixel_limit_is_checked_before_image_decode():
    data = _image_bytes("JPEG", size=(11, 10))

    with pytest.raises(HTTPException) as failure:
        _validate_image_data(data, max_pixels=100, content_type="image/jpeg")

    assert failure.value.status_code == 413
    assert failure.value.detail["code"] == "photo_pixel_limit"


def test_production_pixel_limit_rejects_more_than_sixty_megapixels():
    data = bytearray(_image_bytes("JPEG"))
    sof = data.find(b"\xff\xc0")
    assert sof >= 0
    data[sof + 5:sof + 7] = (10_000).to_bytes(2, "big")
    data[sof + 7:sof + 9] = (6_001).to_bytes(2, "big")

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with pytest.raises(HTTPException) as failure:
            _validate_image_data(bytes(data), max_pixels=60_000_000, content_type="image/jpeg")

    assert failure.value.status_code == 413
    assert failure.value.detail["code"] == "photo_pixel_limit"


def _add_processing_photo(
    factory, media_root, listing_id: uuid.UUID, *, source_bytes: bytes | None = None,
    idempotency_key: str = "draft-photo-1",
) -> tuple[uuid.UUID, str, bytes]:
    photo_id = uuid.uuid4()
    storage_name = uuid.uuid4().hex
    original_name = f"{uuid.uuid4().hex}.upload"
    source = media_root / ".quarantine" / original_name
    source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_bytes = source_bytes or _jpeg(with_exif=True)
    source.write_bytes(source_bytes)
    with Image.open(io.BytesIO(source_bytes)) as image:
        width, height = image.size
    with factory() as db:
        db.add(ListingPhoto(
            id=photo_id,
            listing_id=listing_id,
            storage_name=storage_name,
            original_name=original_name,
            status="processing",
            position=0,
            is_cover=True,
            width=width,
            height=height,
            idempotency_key=idempotency_key,
        ))
        db.commit()
    _make_variants(photo_id)
    return photo_id, storage_name, source_bytes


def _add_pending_photo(factory, media_root, listing_id: uuid.UUID) -> tuple[uuid.UUID, str, str]:
    photo_id = uuid.uuid4()
    storage_name = uuid.uuid4().hex
    original_name = f"{uuid.uuid4().hex}.upload"
    source = media_root / ".quarantine" / original_name
    source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_bytes = _jpeg()
    source.write_bytes(source_bytes)
    with Image.open(io.BytesIO(source_bytes)) as image:
        width, height = image.size
    with factory() as db:
        db.add(ListingPhoto(
            id=photo_id,
            listing_id=listing_id,
            storage_name=storage_name,
            original_name=original_name,
            status="processing",
            position=0,
            is_cover=True,
            width=width,
            height=height,
            idempotency_key=f"pending-{uuid.uuid4().hex}",
        ))
        db.commit()
    return photo_id, storage_name, original_name


def _add_running_photo_job(factory, photo_id: uuid.UUID) -> uuid.UUID:
    job_id = uuid.uuid4()
    now = datetime.now(UTC)
    with factory() as db:
        db.add(WorkerJob(
            id=job_id,
            job_key=f"photo.process:{photo_id}",
            kind="photo.process",
            payload={"photo_id": str(photo_id)},
            status="running",
            attempts=1,
            max_attempts=4,
            run_after=now,
            lease_until=now + timedelta(minutes=3),
            locked_by="test-worker",
        ))
        db.commit()
    return job_id


def _add_ready_photo(factory, media_root, listing_id: uuid.UUID) -> tuple[uuid.UUID, str, str]:
    photo_id = uuid.uuid4()
    storage_name = uuid.uuid4().hex
    original_name = f"{uuid.uuid4().hex}.upload"
    source = media_root / ".quarantine" / original_name
    source.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source.write_bytes(_jpeg())
    variant_dir = media_root / storage_name
    variant_dir.mkdir(parents=True)
    for edge in (320, 768, 1600):
        Image.new("RGB", (min(edge, 48), min(edge, 32)), (30, 80, 120)).save(
            variant_dir / f"{edge}.webp", format="WEBP",
        )
    with factory() as db:
        db.add(ListingPhoto(
            id=photo_id,
            listing_id=listing_id,
            storage_name=storage_name,
            original_name=original_name,
            status="ready",
            position=0,
            is_cover=True,
            width=48,
            height=32,
            idempotency_key=f"delete-{uuid.uuid4().hex}",
        ))
        db.commit()
    return photo_id, storage_name, original_name


def test_upload_checks_declared_type_and_keeps_quarantine_private(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_email = f"upload-photo-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    listing_id = _add_listing(factory, owner_id)
    client, csrf = _login(integration["client"].app, owner_email)
    quarantine = media_root / ".quarantine"
    quarantine.mkdir(mode=0o755)
    quarantine.chmod(0o755)
    upload_url = f"/api/v1/listings/{listing_id}/photos"

    mismatch = client.post(
        upload_url,
        files={"file": ("photo.jpg", _image_bytes("JPEG"), "image/png")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "mismatched-mime"},
    )
    assert mismatch.status_code == 415
    assert list(quarantine.iterdir()) == []

    accepted = client.post(
        upload_url,
        files={"file": ("photo.jpg", _image_bytes("JPEG"), "image/jpeg")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "private-quarantine"},
    )
    assert accepted.status_code == 200, accepted.text
    with factory() as db:
        photo = db.get(ListingPhoto, uuid.UUID(accepted.json()["id"]))
        source = quarantine / photo.original_name
        job = db.scalar(select(WorkerJob).where(WorkerJob.payload["photo_id"].as_string() == str(photo.id)))
        assert job is not None and job.kind == "photo.process"
        job.status = "succeeded"
        db.commit()

    assert stat.S_IMODE(quarantine.stat().st_mode) == 0o700
    assert stat.S_IMODE(source.stat().st_mode) == 0o600


def test_upload_enforces_twenty_mib_and_thirty_photo_limits(integration):
    factory = integration["SessionLocal"]
    owner_email = f"limit-photo-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    listing_id = _add_listing(factory, owner_id)
    client, csrf = _login(integration["client"].app, owner_email)
    upload_url = f"/api/v1/listings/{listing_id}/photos"
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "oversize-photo"}

    too_large = client.post(
        upload_url,
        files={"file": ("large.jpg", b"x" * (20 * 1024 * 1024 + 1), "image/jpeg")},
        headers=headers,
    )
    assert too_large.status_code == 413
    assert too_large.json()["code"] == "photo_too_large"

    with factory() as db:
        db.add_all([
            ListingPhoto(
                id=uuid.uuid4(), listing_id=listing_id, storage_name=uuid.uuid4().hex,
                original_name=f"{uuid.uuid4().hex}.upload", status="processing", position=index,
                is_cover=index == 0, width=48, height=32, idempotency_key=f"limit-{index}",
            )
            for index in range(30)
        ])
        db.commit()
    capped = client.post(
        upload_url,
        files={"file": ("photo.jpg", _jpeg(), "image/jpeg")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "thirty-first-photo"},
    )
    assert capped.status_code == 409
    assert capped.json()["code"] == "photo_limit"


def test_photo_reorder_and_cover_preserve_existing_uploads(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_email = f"reorder-photo-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    listing_id = _add_listing(factory, owner_id)
    photos = [_add_ready_photo(factory, media_root, listing_id)[0] for _ in range(3)]
    with factory() as db:
        for index, photo_id in enumerate(photos):
            photo = db.get(ListingPhoto, photo_id)
            photo.position = index
            photo.is_cover = index == 0
        db.commit()
    client, csrf = _login(integration["client"].app, owner_email)
    headers = {"X-CSRF-Token": csrf}

    reordered = client.post(
        f"/api/v1/listings/{listing_id}/photos/reorder",
        json={"expected_revision": 1, "photo_ids": [str(photos[2]), str(photos[0]), str(photos[1])]},
        headers=headers,
    )
    assert reordered.status_code == 200, reordered.text
    cover = client.post(
        f"/api/v1/listings/{listing_id}/photos/{photos[0]}/cover",
        json={"expected_revision": 2}, headers=headers,
    )
    assert cover.status_code == 200, cover.text

    items = client.get(f"/api/v1/listings/{listing_id}/photos").json()["items"]
    assert [item["id"] for item in items] == [str(photos[2]), str(photos[0]), str(photos[1])]
    assert all(item["status"] == "ready" for item in items)
    assert [item["is_cover"] for item in items] == [False, True, False]


def test_listing_cannot_be_submitted_until_every_photo_is_ready(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_email = f"submit-photo-{uuid.uuid4().hex[:8]}@example.com"
    _add_user(factory, owner_email)
    with factory() as db:
        region = LocationRegion(slug=f"submit-region-{uuid.uuid4().hex[:8]}", name="Minsk region")
        db.add(region)
        db.commit()
        region_id = region.id
    client, csrf = _login(integration["client"].app, owner_email)
    created = client.post(
        "/api/v1/listings/drafts",
        json={
            "seller_type": "private", "manual_make": "Toyota", "manual_model": "Corolla", "year": 2021,
            "mileage_km": 42000, "fuel": "petrol", "transmission": "automatic", "drive": "front",
            "condition": "used", "damaged": False, "parts_only": False,
            "price": {"amount": "14500.00", "currency": "BYN"}, "region_id": str(region_id),
            "manual_city": "Minsk", "description": "Photo publication gate test", "contact_phone": "+375291111111",
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "photo-gate-draft"},
    )
    assert created.status_code == 200, created.text
    listing = created.json()["listing"]
    listing_id = uuid.UUID(listing["id"])
    _add_ready_photo(factory, media_root, listing_id)
    processing_id = uuid.uuid4()
    processing_storage = uuid.uuid4().hex
    with factory() as db:
        db.add(ListingPhoto(
            id=processing_id, listing_id=listing_id, storage_name=processing_storage,
            original_name=f"{uuid.uuid4().hex}.upload", status="processing", position=1,
            is_cover=False, width=48, height=32, idempotency_key="photo-gate-processing",
        ))
        db.commit()

    def submit(key: str):
        return client.post(
            f"/api/v1/listings/{listing_id}/submit", json={"expected_revision": listing["revision"]},
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
        )

    processing = submit("photo-gate-processing-submit")
    assert processing.status_code == 409
    assert processing.json()["code"] == "photos_processing"
    with factory() as db:
        db.get(ListingPhoto, processing_id).status = "failed"
        db.commit()
    failed = submit("photo-gate-failed-submit")
    assert failed.status_code == 422
    assert failed.json()["code"] == "photo_processing_failed"

    variant_dir = media_root / processing_storage
    variant_dir.mkdir()
    for edge in (320, 768, 1600):
        Image.new("RGB", (48, 32), (30, 80, 120)).save(variant_dir / f"{edge}.webp", format="WEBP")
    with factory() as db:
        db.get(ListingPhoto, processing_id).status = "ready"
        db.commit()
    submitted = submit("photo-gate-ready-submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["listing"]["status"] == "pending_review"


def test_worker_claim_uses_database_clock_when_application_clock_is_behind(integration, monkeypatch):
    factory = integration["SessionLocal"]
    job_id = uuid.uuid4()
    with factory() as db:
        database_now = db.scalar(select(func.now()))
        db.add(WorkerJob(
            id=job_id,
            job_key=f"clock-skew:{job_id}",
            kind="photo.process",
            payload={"photo_id": str(uuid.uuid4())},
            status="queued",
            attempts=0,
            max_attempts=4,
            run_after=database_now - timedelta(seconds=1),
        ))
        db.commit()

    class ApplicationClockBehind:
        @staticmethod
        def now(tz=None):
            return database_now - timedelta(days=1)

    monkeypatch.setattr(worker, "datetime", ApplicationClockBehind)

    assert worker._claim_one("clock-skew-worker") == job_id


def test_worker_retry_uses_database_clock_when_application_clock_is_behind(integration, monkeypatch):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"worker-clock-retry-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    photo_id, _, _ = _add_pending_photo(factory, media_root, listing_id)
    job_id = _add_running_photo_job(factory, photo_id)
    with factory() as db:
        database_now = db.scalar(select(func.now()))

    def fail_transiently(_requested_photo_id):
        raise OSError("temporary processing failure")

    class ApplicationClockBehind:
        @staticmethod
        def now(tz=None):
            return database_now - timedelta(days=1)

    monkeypatch.setattr(worker, "datetime", ApplicationClockBehind)
    monkeypatch.setattr(worker, "_make_variants", fail_transiently)
    worker._run_job(job_id, "test-worker")

    with factory() as db:
        job = db.get(WorkerJob, job_id)
        current_database_time = db.scalar(select(func.now()))
        assert job.status == "queued"
        delay_seconds = (job.run_after - current_database_time).total_seconds()
        assert 59 <= delay_seconds <= 61


def test_worker_applies_orientation_and_writes_bounded_exif_free_variants(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"variant-photo-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, _ = _add_processing_photo(
        factory, media_root, listing_id, source_bytes=_jpeg(with_exif=True, size=(2400, 1600)),
    )

    expected_sizes = {320: (213, 320), 768: (512, 768), 1600: (1067, 1600)}
    for edge, expected_size in expected_sizes.items():
        with Image.open(media_root / storage_name / f"{edge}.webp") as image:
            assert image.format == "WEBP"
            assert image.size == expected_size
            assert not image.getexif()
    with factory() as db:
        photo = db.get(ListingPhoto, photo_id)
        assert photo.status == "ready"
        assert (photo.width, photo.height) == (1600, 2400)
        original_name = photo.original_name
    assert not (media_root / ".quarantine" / original_name).exists()


@pytest.mark.parametrize("format_name", ["JPEG", "PNG", "WEBP", "HEIF"])
def test_worker_processes_each_supported_static_format(integration, format_name):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"format-{format_name.lower()}-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, _ = _add_processing_photo(
        factory, media_root, listing_id,
        source_bytes=_image_bytes(format_name), idempotency_key=f"format-{format_name.lower()}",
    )

    with factory() as db:
        assert db.get(ListingPhoto, photo_id).status == "ready"
    for edge in (320, 768, 1600):
        with Image.open(media_root / storage_name / f"{edge}.webp") as image:
            assert image.format == "WEBP"
            assert image.size == (48, 32)


def test_worker_retry_after_commit_ack_failure_keeps_published_variants(integration, monkeypatch):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"worker-commit-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, original_name = _add_pending_photo(factory, media_root, listing_id)
    job_id = _add_running_photo_job(factory, photo_id)
    fail_after_commit = {"enabled": True}

    def session_factory():
        db = factory()
        commit = db.commit

        def commit_with_lost_ack():
            photo_was_marked_ready = any(
                isinstance(row, ListingPhoto) and row.status == "ready"
                for row in db.dirty
            )
            commit()
            if photo_was_marked_ready and fail_after_commit["enabled"]:
                fail_after_commit["enabled"] = False
                raise RuntimeError("simulated commit acknowledgement failure")

        db.commit = commit_with_lost_ack
        return db

    monkeypatch.setattr(worker, "SessionLocal", session_factory)
    worker._run_job(job_id, "test-worker")

    variant_dir = media_root / storage_name
    assert sorted(path.name for path in variant_dir.iterdir()) == ["1600.webp", "320.webp", "768.webp"]
    with factory() as db:
        photo = db.get(ListingPhoto, photo_id)
        job = db.get(WorkerJob, job_id)
        assert photo.status == "ready"
        assert job.status == "queued"
        assert job.attempts == 1

    with factory() as db:
        db.get(WorkerJob, job_id).run_after = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert worker._claim_one("test-worker") == job_id
    worker._run_job(job_id, "test-worker")

    with factory() as db:
        photo = db.get(ListingPhoto, photo_id)
        job = db.get(WorkerJob, job_id)
        assert photo.status == "ready"
        assert job.status == "succeeded"
        assert job.attempts == 2
    assert (media_root / ".quarantine" / original_name).exists() is False
    assert sorted(path.name for path in variant_dir.iterdir()) == ["1600.webp", "320.webp", "768.webp"]


def test_worker_retries_transient_photo_failure_without_duplicate_job_or_variants(integration, monkeypatch):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"worker-retry-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, original_name = _add_pending_photo(factory, media_root, listing_id)
    job_id = _add_running_photo_job(factory, photo_id)
    make_variants = worker._make_variants
    attempts = {"count": 0}

    def fail_once(requested_photo_id):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("simulated temporary photo processing failure")
        make_variants(requested_photo_id)

    monkeypatch.setattr(worker, "_make_variants", fail_once)
    worker._run_job(job_id, "test-worker")

    variant_dir = media_root / storage_name
    assert not variant_dir.exists()
    with factory() as db:
        assert db.get(ListingPhoto, photo_id).status == "processing"
        job = db.get(WorkerJob, job_id)
        assert job.status == "queued"
        assert job.attempts == 1
        assert job.last_error == "simulated temporary photo processing failure"
        db.get(WorkerJob, job_id).run_after = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    assert worker._claim_one("test-worker") == job_id
    worker._run_job(job_id, "test-worker")

    with factory() as db:
        assert db.get(ListingPhoto, photo_id).status == "ready"
        job = db.get(WorkerJob, job_id)
        assert job.status == "succeeded"
        assert job.attempts == 2
        assert len(db.scalars(select(WorkerJob.id).where(WorkerJob.job_key == job.job_key)).all()) == 1
    assert attempts["count"] == 2
    assert not (media_root / ".quarantine" / original_name).exists()
    assert sorted(path.name for path in variant_dir.iterdir()) == ["1600.webp", "320.webp", "768.webp"]


@pytest.mark.parametrize("photo_state", ["missing", "failed"])
def test_worker_does_not_succeed_when_photo_cannot_be_processed(integration, photo_state):
    factory = integration["SessionLocal"]
    owner_id = _add_user(factory, f"worker-{photo_state}-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    photo_id, _, _ = _add_pending_photo(factory, integration["media_root"], listing_id)
    if photo_state == "failed":
        with factory() as db:
            db.get(ListingPhoto, photo_id).status = "failed"
            db.commit()
    else:
        with factory() as db:
            db.delete(db.get(ListingPhoto, photo_id))
            db.commit()
    job_id = _add_running_photo_job(factory, photo_id)

    worker._run_job(job_id, "test-worker")

    with factory() as db:
        job = db.get(WorkerJob, job_id)
        assert job.status == "failed"
        assert job.last_error
        assert (db.get(ListingPhoto, photo_id).status if photo_state == "failed" else None) == (
            "failed" if photo_state == "failed" else None
        )


def test_bad_photo_failure_does_not_block_another_photo(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"isolated-photo-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    bad_id = uuid.uuid4()
    bad_storage = uuid.uuid4().hex
    bad_name = f"{uuid.uuid4().hex}.upload"
    bad_source = media_root / ".quarantine" / bad_name
    bad_source.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    bad_source.write_bytes(_jpeg()[:-10])
    partial_dir = media_root / bad_storage
    partial_dir.mkdir()
    (partial_dir / "768.webp").write_bytes(b"partial")
    with factory() as db:
        db.add(ListingPhoto(
            id=bad_id, listing_id=listing_id, storage_name=bad_storage, original_name=bad_name,
            status="processing", position=0, is_cover=True, width=1, height=1,
            idempotency_key="bad-photo",
        ))
        db.commit()

    with pytest.raises(PermanentJobError):
        _make_variants(bad_id)
    with factory() as db:
        assert db.get(ListingPhoto, bad_id).status == "failed"
    assert not bad_source.exists()
    assert not partial_dir.exists()

    good_id, _, _ = _add_processing_photo(
        factory, media_root, listing_id, idempotency_key="good-photo",
    )
    with factory() as db:
        assert db.get(ListingPhoto, good_id).status == "ready"


def test_retention_cleans_stuck_and_orphaned_upload_files_after_twenty_four_hours(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"cleanup-photo-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id)
    now = datetime.now(UTC)
    stale_id = uuid.uuid4()
    stale_storage = uuid.uuid4().hex
    stale_name = f"{uuid.uuid4().hex}.upload"
    stale_source = media_root / ".quarantine" / stale_name
    stale_source.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    stale_source.write_bytes(_jpeg())
    stale_dir = media_root / stale_storage
    stale_dir.mkdir()
    (stale_dir / "320.webp").write_bytes(b"partial")
    fresh_id = uuid.uuid4()
    fresh_name = f"{uuid.uuid4().hex}.upload"
    fresh_source = media_root / ".quarantine" / fresh_name
    fresh_source.write_bytes(_jpeg())
    orphan_name = f"{uuid.uuid4().hex}.upload"
    orphan_source = media_root / ".quarantine" / orphan_name
    orphan_source.write_bytes(b"orphan")
    orphan_storage = uuid.uuid4().hex
    orphan_dir = media_root / orphan_storage
    orphan_dir.mkdir()
    staging_dir = media_root / f".photo-{uuid.uuid4().hex}-{uuid.uuid4().hex}.tmp"
    staging_dir.mkdir()
    old_timestamp = (now - timedelta(hours=25)).timestamp()
    os.utime(orphan_source, (old_timestamp, old_timestamp))
    os.utime(orphan_dir, (old_timestamp, old_timestamp))
    os.utime(staging_dir, (old_timestamp, old_timestamp))
    with factory() as db:
        db.add_all([
            ListingPhoto(
                id=stale_id, listing_id=listing_id, storage_name=stale_storage, original_name=stale_name,
                status="processing", position=0, is_cover=True, width=48, height=32,
                idempotency_key="stale-photo", created_at=now - timedelta(hours=25),
            ),
            ListingPhoto(
                id=fresh_id, listing_id=listing_id, storage_name=uuid.uuid4().hex, original_name=fresh_name,
                status="processing", position=1, is_cover=False, width=48, height=32,
                idempotency_key="fresh-photo",
            ),
            WorkerJob(
                id=uuid.uuid4(), job_key=f"photo.process:{stale_id}", kind="photo.process",
                payload={"photo_id": str(stale_id)}, status="running", attempts=1, max_attempts=4,
                run_after=now - timedelta(hours=25), lease_until=now - timedelta(hours=24), locked_by="dead-worker",
            ),
        ])
        db.commit()

    _cleanup_retention()
    _cleanup_retention()

    with factory() as db:
        assert db.get(ListingPhoto, stale_id) is None
        assert db.get(ListingPhoto, fresh_id).status == "processing"
        stale_job = db.scalar(select(WorkerJob).where(WorkerJob.payload["photo_id"].as_string() == str(stale_id)))
        assert stale_job is None
    assert not stale_source.exists()
    assert not stale_dir.exists()
    assert fresh_source.exists()
    assert not orphan_source.exists()
    assert not orphan_dir.exists()
    assert not staging_dir.exists()


def test_retention_removes_stale_photo_rows_from_upload_quota(integration):
    factory = integration["SessionLocal"]
    owner_email = f"cleanup-quota-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    listing_id = _add_listing(factory, owner_id)
    now = datetime.now(UTC)
    fresh_id = uuid.uuid4()
    stale_ids = [uuid.uuid4() for _ in range(30)]
    with factory() as db:
        db.add(ListingPhoto(
            id=fresh_id, listing_id=listing_id, storage_name=uuid.uuid4().hex,
            original_name=f"{uuid.uuid4().hex}.upload", status="ready", position=0,
            is_cover=True, width=48, height=32, idempotency_key="fresh-ready-photo",
            created_at=now,
        ))
        db.add_all([
            ListingPhoto(
                id=photo_id, listing_id=listing_id, storage_name=uuid.uuid4().hex,
                original_name=f"{uuid.uuid4().hex}.upload", status="failed", position=index + 1,
                is_cover=False, width=48, height=32, idempotency_key=f"stale-quota-{index}",
                created_at=now - timedelta(hours=25),
            )
            for index, photo_id in enumerate(stale_ids)
        ])
        db.commit()

    with factory() as db:
        assert db.scalar(select(func.count(ListingPhoto.id)).where(ListingPhoto.listing_id == listing_id)) == 31

    _cleanup_retention()

    with factory() as db:
        assert db.scalar(select(func.count(ListingPhoto.id)).where(ListingPhoto.listing_id == listing_id)) == 1
        assert db.get(ListingPhoto, fresh_id) is not None
        assert all(db.get(ListingPhoto, photo_id) is None for photo_id in stale_ids)

    client, csrf = _login(integration["client"].app, owner_email)
    uploaded = client.post(
        f"/api/v1/listings/{listing_id}/photos",
        files={"file": ("photo.jpg", _jpeg(), "image/jpeg")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "after-retention-cleanup"},
    )
    assert uploaded.status_code == 200, uploaded.text
    with factory() as db:
        job = db.scalar(select(WorkerJob).where(
            WorkerJob.payload["photo_id"].as_string() == uploaded.json()["id"],
        ))
        assert job is not None
        job.status = "succeeded"
        db.commit()


def test_recent_rate_does_not_skip_daily_photo_cleanup_schedule(integration):
    factory = integration["SessionLocal"]
    now = datetime.now(UTC)
    with factory() as db:
        db.query(WorkerJob).filter(WorkerJob.kind.in_(["rates.refresh", "cleanup.retention"])).delete(synchronize_session=False)
        db.add(ExchangeRate(
            id=uuid.uuid4(), currency="USD", rate_date="2099-01-01", official_rate=Decimal("3.20"),
            scale=1, source="test", fetched_at=now,
        ))
        db.commit()

    _schedule_daily_rates()

    with factory() as db:
        cleanup = db.scalar(select(WorkerJob).where(
            WorkerJob.kind == "cleanup.retention", WorkerJob.status == "queued",
        ))
        assert cleanup is not None
        cleanup.status = "succeeded"
        db.commit()


def test_worker_imports_and_upserts_the_nbrb_usd_rate_contract(integration, monkeypatch):
    factory = integration["SessionLocal"]
    rate_date = datetime.now(UTC).date().isoformat()
    payloads = [
        {"Date": f"{rate_date}T00:00:00", "Cur_Scale": 1, "Cur_OfficialRate": 3.4512},
        {"Date": f"{rate_date}T00:00:00", "Cur_Scale": 10, "Cur_OfficialRate": 34.5678},
    ]
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return io.BytesIO(json.dumps(payloads.pop(0)).encode())

    monkeypatch.setattr(worker.urllib.request, "urlopen", fake_urlopen)

    _refresh_usd_rate()
    with factory() as db:
        rate = db.scalar(select(ExchangeRate).where(
            ExchangeRate.currency == "USD", ExchangeRate.rate_date == rate_date,
        ))
        assert rate is not None
        rate_id = rate.id
        assert rate.official_rate == Decimal("3.451200")
        assert rate.scale == 1

    _refresh_usd_rate()
    with factory() as db:
        rates = db.scalars(select(ExchangeRate).where(
            ExchangeRate.currency == "USD", ExchangeRate.rate_date == rate_date,
        )).all()
        assert len(rates) == 1
        assert rates[0].id == rate_id
        assert rates[0].official_rate == Decimal("34.567800")
        assert rates[0].scale == 10
        assert rates[0].source == "https://api.nbrb.by/exrates/rates/USD?parammode=2"

    assert len(requests) == 2
    assert all(request.full_url == "https://api.nbrb.by/exrates/rates/USD?parammode=2" for request, _ in requests)
    assert all(timeout == 12 for _, timeout in requests)


def test_draft_photos_are_owner_only_and_do_not_expose_file_metadata(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_email = f"media-owner-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    other_email = f"media-other-{uuid.uuid4().hex[:8]}@example.com"
    _add_user(factory, other_email)
    moderator_email = f"media-mod-{uuid.uuid4().hex[:8]}@example.com"
    _add_user(factory, moderator_email, role="moderator")
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, original_bytes = _add_processing_photo(factory, media_root, listing_id)

    owner, owner_csrf = _login(integration["client"].app, owner_email)
    other, other_csrf = _login(integration["client"].app, other_email)
    moderator, _ = _login(integration["client"].app, moderator_email)
    with Image.open(io.BytesIO(original_bytes)) as original:
        assert original.getexif()
    for edge in (320, 768, 1600):
        with Image.open(media_root / storage_name / f"{edge}.webp") as variant:
            assert variant.size == (32, 48)
            assert not variant.getexif()
    statuses_url = f"/api/v1/listings/{listing_id}/photos"
    owner_items = owner.get(statuses_url).json()["items"]
    assert owner_items == [{
        "id": str(photo_id), "status": "ready", "position": 0, "is_cover": True,
        "url": f"/api/v1/photos/{photo_id}/768",
    }]
    assert other.get(statuses_url).status_code == 404
    assert moderator.get(statuses_url).status_code == 404
    assert other.get(f"/api/v1/listings/{listing_id}").status_code == 404
    assert moderator.get(f"/api/v1/listings/{listing_id}").status_code == 404
    assert owner.get(f"/api/v1/photos/{photo_id}/768").status_code == 200
    assert other.get(f"/api/v1/photos/{photo_id}/768").status_code == 404
    assert moderator.get(f"/api/v1/photos/{photo_id}/768").status_code == 404
    assert integration["client"].get(f"/api/v1/photos/{photo_id}/768").status_code == 404

    response = owner.get(f"/api/v1/photos/{photo_id}/768")
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "etag" not in response.headers
    assert "last-modified" not in response.headers
    with Image.open(io.BytesIO(response.content)) as image:
        assert not image.getexif()

    upload_url = f"/api/v1/listings/{listing_id}/photos"
    repeated = owner.post(
        upload_url,
        files={"file": ("ignored.jpg", _jpeg(), "image/jpeg")},
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "draft-photo-1"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == str(photo_id)
    rejected = other.post(
        upload_url,
        files={"file": ("ignored.jpg", _jpeg(), "image/jpeg")},
        headers={"X-CSRF-Token": other_csrf, "Idempotency-Key": "draft-photo-1"},
    )
    assert rejected.status_code == 404
    with factory() as db:
        photos = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing_id)).all()
        assert len(photos) == 1
        assert photos[0].storage_name == storage_name

    pending_listing_id = _add_listing(factory, owner_id, status="pending_review")
    pending_photo_id, _, _ = _add_ready_photo(factory, media_root, pending_listing_id)
    pending = moderator.get(f"/api/v1/listings/{pending_listing_id}")
    assert pending.status_code == 200, pending.text
    assert pending.json()["listing"]["status"] == "pending_review"
    assert pending.json()["listing"]["photos"][0]["id"] == str(pending_photo_id)
    assert moderator.get(f"/api/v1/photos/{pending_photo_id}/768").status_code == 200


def test_reviewers_can_read_pending_review_photo_statuses_only(integration):
    factory = integration["SessionLocal"]
    owner_id = _add_user(factory, f"review-status-owner-{uuid.uuid4().hex[:8]}@example.com")
    moderator_email = f"review-status-mod-{uuid.uuid4().hex[:8]}@example.com"
    admin_email = f"review-status-admin-{uuid.uuid4().hex[:8]}@example.com"
    other_email = f"review-status-other-{uuid.uuid4().hex[:8]}@example.com"
    _add_user(factory, moderator_email, role="moderator")
    _add_user(factory, admin_email, role="admin")
    _add_user(factory, other_email)
    listing_id = _add_listing(factory, owner_id, status="pending_review")
    photo_id, _, _ = _add_pending_photo(factory, integration["media_root"], listing_id)

    moderator, _ = _login(integration["client"].app, moderator_email)
    admin, _ = _login(integration["client"].app, admin_email)
    other, _ = _login(integration["client"].app, other_email)
    statuses_url = f"/api/v1/listings/{listing_id}/photos"
    expected_items = [{
        "id": str(photo_id), "status": "processing", "position": 0,
        "is_cover": True, "url": None,
    }]

    assert moderator.get(statuses_url).json() == {"items": expected_items}
    assert admin.get(statuses_url).json() == {"items": expected_items}
    assert other.get(statuses_url).status_code == 404
    assert moderator.get(f"/api/v1/photos/{photo_id}/768").status_code == 404
    assert admin.get(f"/api/v1/photos/{photo_id}/768").status_code == 404


@pytest.mark.parametrize("status", ["draft", "paused", "active", "rejected", "blocked", "archived", "sold"])
def test_reviewers_cannot_read_photo_statuses_outside_pending_review(integration, status):
    factory = integration["SessionLocal"]
    owner_email = f"hidden-status-owner-{uuid.uuid4().hex[:8]}@example.com"
    moderator_email = f"hidden-status-mod-{uuid.uuid4().hex[:8]}@example.com"
    admin_email = f"hidden-status-admin-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    _add_user(factory, moderator_email, role="moderator")
    _add_user(factory, admin_email, role="admin")
    listing_id = _add_listing(factory, owner_id, status=status)
    _add_pending_photo(factory, integration["media_root"], listing_id)

    owner, _ = _login(integration["client"].app, owner_email)
    moderator, _ = _login(integration["client"].app, moderator_email)
    admin, _ = _login(integration["client"].app, admin_email)
    statuses_url = f"/api/v1/listings/{listing_id}/photos"

    assert owner.get(statuses_url).status_code == 200
    assert moderator.get(statuses_url).status_code == 404
    assert admin.get(statuses_url).status_code == 404


def test_published_photos_remain_public(integration):
    factory = integration["SessionLocal"]
    owner_id = _add_user(factory, f"public-photo-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id, status="active")
    photo_id, _, _ = _add_ready_photo(factory, integration["media_root"], listing_id)

    response = integration["client"].get(f"/api/v1/photos/{photo_id}/768")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "no-store"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.format == "WEBP"


@pytest.mark.parametrize("status", ["paused", "rejected", "blocked", "archived", "sold"])
def test_reviewers_cannot_access_photos_for_nonpublic_listing_states(integration, status):
    factory = integration["SessionLocal"]
    owner_email = f"hidden-photo-owner-{uuid.uuid4().hex[:8]}@example.com"
    moderator_email = f"hidden-photo-mod-{uuid.uuid4().hex[:8]}@example.com"
    admin_email = f"hidden-photo-admin-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    _add_user(factory, moderator_email, role="moderator")
    _add_user(factory, admin_email, role="admin")
    listing_id = _add_listing(factory, owner_id, status=status)
    if status == "sold":
        with factory() as db:
            db.get(Listing, listing_id).sold_at = datetime.now(UTC) - timedelta(days=31)
            db.commit()
    photo_id, _, _ = _add_ready_photo(factory, integration["media_root"], listing_id)

    owner, _ = _login(integration["client"].app, owner_email)
    moderator, _ = _login(integration["client"].app, moderator_email)
    admin, _ = _login(integration["client"].app, admin_email)

    photo_url = f"/api/v1/photos/{photo_id}/768"
    assert owner.get(photo_url).status_code == 200
    assert moderator.get(photo_url).status_code == 404
    assert admin.get(photo_url).status_code == 404


def test_photo_storage_path_cannot_escape_media_root(integration):
    factory = integration["SessionLocal"]
    media_root = integration["media_root"]
    owner_id = _add_user(factory, f"path-photo-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = _add_listing(factory, owner_id, status="active")
    photo_id = uuid.uuid4()
    outside_dir = media_root.parent / f"outside-{uuid.uuid4().hex}"
    outside_dir.mkdir()
    Image.new("RGB", (8, 8), (30, 80, 120)).save(outside_dir / "768.webp", format="WEBP")
    try:
        with factory() as db:
            db.add(ListingPhoto(
                id=photo_id,
                listing_id=listing_id,
                storage_name=f"../{outside_dir.name}",
                original_name=f"{uuid.uuid4().hex}.upload",
                status="ready",
                position=0,
                is_cover=True,
                width=8,
                height=8,
            ))
            db.commit()
        response = TestClient(integration["client"].app).get(f"/api/v1/photos/{photo_id}/768")
        assert response.status_code == 404
    finally:
        shutil.rmtree(outside_dir)


def test_photo_delete_commits_record_before_removing_files(integration):
    factory = integration["SessionLocal"]
    owner_email = f"delete-photo-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, original_name = _add_ready_photo(factory, integration["media_root"], listing_id)
    client, csrf = _login(integration["client"].app, owner_email)

    deleted = client.request(
        "DELETE",
        f"/api/v1/listings/{listing_id}/photos/{photo_id}",
        json={"expected_revision": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 200, deleted.text
    with factory() as db:
        assert db.get(ListingPhoto, photo_id) is None
    assert not (integration["media_root"] / storage_name).exists()
    assert not (integration["media_root"] / ".quarantine" / original_name).exists()


def test_failed_photo_delete_commit_leaves_files_and_record_intact(integration):
    factory = integration["SessionLocal"]
    owner_email = f"rollback-photo-{uuid.uuid4().hex[:8]}@example.com"
    owner_id = _add_user(factory, owner_email)
    listing_id = _add_listing(factory, owner_id)
    photo_id, storage_name, original_name = _add_ready_photo(factory, integration["media_root"], listing_id)
    client, csrf = _login(integration["client"].app, owner_email)
    app = integration["client"].app
    original_override = app.dependency_overrides[get_db]

    def failed_commit_db():
        with factory() as db:
            def fail_commit():
                raise RuntimeError("simulated database failure")

            db.commit = fail_commit
            yield db

    app.dependency_overrides[get_db] = failed_commit_db
    try:
        failure_client = TestClient(app, raise_server_exceptions=False)
        failure_client.cookies.update(client.cookies)
        response = failure_client.request(
            "DELETE",
            f"/api/v1/listings/{listing_id}/photos/{photo_id}",
            json={"expected_revision": 1},
            headers={"X-CSRF-Token": csrf},
        )
    finally:
        app.dependency_overrides[get_db] = original_override

    assert response.status_code == 500
    with factory() as db:
        assert db.get(ListingPhoto, photo_id) is not None
    assert (integration["media_root"] / storage_name / "768.webp").is_file()
    assert (integration["media_root"] / ".quarantine" / original_name).is_file()
