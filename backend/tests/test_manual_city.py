import uuid

import pytest
from pydantic import ValidationError

from app.models import Listing, ListingPhoto, LocationCity, LocationRegion, User
from app.schemas import ListingForm
from app.security import hash_password

PASSWORD = "manual-city-test-password-123"


def test_manual_city_normalizes_whitespace_and_limits_length():
    payload = ListingForm(manual_city="  Новополоцк\t\tмикрорайон   5  ")
    assert payload.manual_city == "Новополоцк микрорайон 5"

    with pytest.raises(ValidationError):
        ListingForm(manual_city="x" * 161)


def _create_location_and_user(integration):
    suffix = uuid.uuid4().hex
    user = User(
        email=f"manual-city-{suffix}@example.com",
        display_name="Manual City Seller",
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    region = LocationRegion(slug=f"region-{suffix}", name="Pilot region")
    foreign_region = LocationRegion(slug=f"foreign-region-{suffix}", name="Other region")
    email = user.email
    with integration["SessionLocal"]() as db:
        db.add_all([user, region, foreign_region])
        db.flush()
        city = LocationCity(region_id=region.id, slug=f"city-{suffix}", name="Catalog city")
        foreign_city = LocationCity(region_id=foreign_region.id, slug=f"foreign-city-{suffix}", name="Foreign city")
        db.add_all([city, foreign_city])
        db.commit()
        ids = (user.id, region.id, city.id, foreign_city.id)

    client = integration["client"]
    client.cookies.clear()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client, login.json()["csrf_token"], ids


def test_manual_city_create_patch_and_catalog_switching(integration):
    client, csrf, (_, region_id, city_id, foreign_city_id) = _create_location_and_user(integration)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "manual-city-create"}
    created = client.post(
        "/api/v1/listings/drafts",
        json={"region_id": str(region_id), "city_id": None, "manual_city": "  Березино   центр "},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    listing = created.json()["listing"]
    assert listing["city"] is None
    assert listing["manual_city"] == "Березино центр"
    assert listing["region"]["id"] == str(region_id)

    catalog = client.patch(
        f"/api/v1/listings/{listing['id']}",
        json={"expected_revision": listing["revision"], "city_id": str(city_id), "manual_city": None},
        headers={"X-CSRF-Token": csrf},
    )
    assert catalog.status_code == 200, catalog.text
    catalog_listing = catalog.json()["listing"]
    assert catalog_listing["city"]["id"] == str(city_id)
    assert catalog_listing["manual_city"] is None

    manual = client.patch(
        f"/api/v1/listings/{listing['id']}",
        json={"expected_revision": catalog_listing["revision"], "city_id": None, "manual_city": "  Логойск  "},
        headers={"X-CSRF-Token": csrf},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["listing"]["city"] is None
    assert manual.json()["listing"]["manual_city"] == "Логойск"

    both = client.post(
        "/api/v1/listings/drafts",
        json={"region_id": str(region_id), "city_id": str(city_id), "manual_city": "Ручной город"},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "manual-city-conflict"},
    )
    assert both.status_code == 422, both.text
    assert set(both.json()["field_errors"]) == {"city_id", "manual_city"}

    wrong_region = client.post(
        "/api/v1/listings/drafts",
        json={"region_id": str(region_id), "city_id": str(foreign_city_id), "manual_city": None},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "manual-city-foreign-region"},
    )
    assert wrong_region.status_code == 422, wrong_region.text
    assert "city_id" in wrong_region.json()["field_errors"]


def _create_ready_listing(client, integration, csrf, *, region_id=None, city_id=None, manual_city=None, key="manual-city-submit"):
    payload = {
        "seller_type": "private",
        "manual_make": "Test make",
        "manual_model": "Test model",
        "title": "Manual location pilot vehicle",
        "year": 2024,
        "mileage_km": 10000,
        "fuel": "petrol",
        "transmission": "manual",
        "drive": "front",
        "condition": "used",
        "price": {"amount": "10000", "currency": "BYN"},
        "region_id": str(region_id) if region_id else None,
        "city_id": str(city_id) if city_id else None,
        "manual_city": manual_city,
        "description": "Complete listing used to verify manual location submission.",
        "contact_phone": "+375291234567",
    }
    created = client.post(
        "/api/v1/listings/drafts", json=payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
    )
    assert created.status_code == 200, created.text
    listing = created.json()["listing"]
    photo_suffix = uuid.uuid4().hex
    with integration["SessionLocal"]() as db:
        db.add(ListingPhoto(
            listing_id=uuid.UUID(listing["id"]),
            storage_name=f"manual-city-{photo_suffix}.webp",
            original_name=f"manual-city-{photo_suffix}.jpg",
            status="ready",
            position=0,
            is_cover=True,
            width=1,
            height=1,
        ))
        db.commit()
    return listing


def test_public_text_search_includes_manual_city(integration):
    client = integration["client"]
    owner = User(
        email=f"manual-city-search-{uuid.uuid4().hex}@example.com",
        display_name="Manual City Search Seller",
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    listing_id = uuid.uuid4()
    with integration["SessionLocal"]() as db:
        db.add(owner)
        db.flush()
        db.add(Listing(
            id=listing_id,
            owner_id=owner.id,
            slug=f"manual-city-search-{uuid.uuid4().hex}",
            status="active",
            title="Vehicle with a manual location",
            manual_city="Березино",
        ))
        db.commit()

    response = client.get("/api/v1/listings", params={"q": "  БЕРЕЗИНО  "})
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["total"] == 1
    assert response.json()["items"][0]["id"] == str(listing_id)


def test_submit_requires_region_and_one_city_representation(integration):
    client, csrf, (_, region_id, city_id, _) = _create_location_and_user(integration)

    no_region = _create_ready_listing(
        client, integration, csrf, manual_city="Manual town", key="manual-submit-no-region",
    )
    missing_region = client.post(
        f"/api/v1/listings/{no_region['id']}/submit",
        json={"expected_revision": no_region["revision"]},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "manual-submit-no-region-action"},
    )
    assert missing_region.status_code == 422, missing_region.text
    assert "region_id" in missing_region.json()["field_errors"]

    no_city = _create_ready_listing(
        client, integration, csrf, region_id=region_id, key="manual-submit-no-city",
    )
    missing_city = client.post(
        f"/api/v1/listings/{no_city['id']}/submit",
        json={"expected_revision": no_city["revision"]},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "manual-submit-no-city-action"},
    )
    assert missing_city.status_code == 422, missing_city.text
    assert "city_id" in missing_city.json()["field_errors"]

    manual = _create_ready_listing(
        client, integration, csrf, region_id=region_id, manual_city="  Ручной   населённый пункт ",
        key="manual-submit-success",
    )
    submitted = client.post(
        f"/api/v1/listings/{manual['id']}/submit",
        json={"expected_revision": manual["revision"]},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "manual-submit-success-action"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["listing"]["status"] == "pending_review"
    assert submitted.json()["listing"]["city"] is None
    assert submitted.json()["listing"]["manual_city"] == "Ручной населённый пункт"

    moderator_email = f"manual-city-moderator-{uuid.uuid4().hex}@example.com"
    with integration["SessionLocal"]() as db:
        db.add(User(
            email=moderator_email,
            display_name="Manual City Moderator",
            password_hash=hash_password(PASSWORD),
            role="moderator",
            status="active",
        ))
        db.commit()
    moderator_client = client.__class__(client.app, base_url="http://testserver")
    moderator_login = moderator_client.post(
        "/api/v1/auth/login", json={"email": moderator_email, "password": PASSWORD},
    )
    assert moderator_login.status_code == 200, moderator_login.text
    queue = moderator_client.get("/api/v1/moderation/listings")
    assert queue.status_code == 200, queue.text
    moderated_listing = next(item for item in queue.json()["items"] if item["id"] == manual["id"])
    assert moderated_listing["manual_city"] == "Ручной населённый пункт"
    assert moderated_listing["city"] is None

    catalog = _create_ready_listing(
        client, integration, csrf, region_id=region_id, city_id=city_id,
        key="catalog-submit-success",
    )
    catalog_submitted = client.post(
        f"/api/v1/listings/{catalog['id']}/submit",
        json={"expected_revision": catalog["revision"]},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "catalog-submit-success-action"},
    )
    assert catalog_submitted.status_code == 200, catalog_submitted.text
    assert catalog_submitted.json()["listing"]["city"]["id"] == str(city_id)
    assert catalog_submitted.json()["listing"]["manual_city"] is None
