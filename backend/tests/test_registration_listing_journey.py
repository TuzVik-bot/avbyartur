import io
import uuid
import pytest
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app import worker
from app.api import auth as auth_api
from app.api import listings as listings_api
from app.config import get_settings
from app.email_registration_policy import PILOT_PRIVACY_VERSION, PILOT_TERMS_VERSION
from app.models import ContactReveal, LocationRegion, User
from app.security import hash_password

PASSWORD = "Journey-test-password-123"
PHONE = "+375291234567"


def _client(integration) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver")


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 32), (30, 80, 120)).save(output, format="JPEG")
    return output.getvalue()


def _add_buyer(factory) -> User:
    user = User(
        email=f"journey-buyer-{uuid.uuid4().hex}@example.com",
        display_name="Local journey buyer",
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


@pytest.mark.parametrize("auto_publish", [False, True])
def test_email_registration_to_published_listing_and_contact(integration, monkeypatch, auto_publish):
    """Exercise the seller journey against the isolated disposable test database."""
    factory = integration["SessionLocal"]
    settings = get_settings().model_copy(
        update={
            "email_registration_enabled": True,
            "email_registration_pilot_enabled": True,
            "registration_terms_version": PILOT_TERMS_VERSION,
            "registration_privacy_version": PILOT_PRIVACY_VERSION,
            "session_cookie_secure": False,
            "public_guest_contact_enabled": False,
            "listing_auto_publish_enabled": auto_publish,
        }
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(listings_api, "get_settings", lambda: settings)

    # Local-only account created through the same pre-auth CSRF and registration API as the UI.
    seller = _client(integration)
    email = f"journey-seller-{uuid.uuid4().hex}@example.com"
    pre_auth = seller.get("/api/v1/auth/otp/csrf")
    assert pre_auth.status_code == 200, pre_auth.text
    registration = seller.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "display_name": "Local journey seller",
            "accept_terms": True,
            "accept_privacy": True,
            "terms_version": PILOT_TERMS_VERSION,
            "privacy_version": PILOT_PRIVACY_VERSION,
        },
        headers=_csrf(pre_auth.json()["csrf_token"]),
    )
    assert registration.status_code == 201, registration.text
    seller_csrf = registration.json()["csrf_token"]
    seller_id = registration.json()["user"]["id"]
    assert seller.get("/api/v1/me").status_code == 200

    with factory() as db:
        region = LocationRegion(
            slug=f"journey-region-{uuid.uuid4().hex}",
            name="Local test region",
        )
        db.add(region)
        db.commit()
        region_id = region.id

    draft = seller.post(
        "/api/v1/listings/drafts",
        json={"seller_type": "private"},
        headers={
            **_csrf(seller_csrf),
            "Idempotency-Key": f"journey-draft-{uuid.uuid4().hex}",
        },
    )
    assert draft.status_code == 200, draft.text
    listing = draft.json()["listing"]
    assert listing["status"] == "draft"
    assert listing["revision"] == 1

    edited = seller.patch(
        f"/api/v1/listings/{listing['id']}",
        json={
            "expected_revision": listing["revision"],
            "title": "Local test vehicle",
            "manual_make": "Test make",
            "manual_model": "Test model",
            "year": 2020,
            "mileage_km": 42000,
            "fuel": "petrol",
            "transmission": "automatic",
            "drive": "front",
            "condition": "used",
            "description": "Synthetic listing for isolated journey acceptance.",
            "price": {"amount": "14500.00", "currency": "BYN"},
            "region_id": str(region_id),
            "manual_city": "Local test town",
            "contact_phone": PHONE,
        },
        headers=_csrf(seller_csrf),
    )
    assert edited.status_code == 200, edited.text
    edited_listing = edited.json()["listing"]
    assert edited_listing["revision"] == 2
    assert edited_listing["status"] == "draft"
    assert edited_listing["manual_city"] == "Local test town"
    assert edited_listing["contact_phone"] == PHONE

    uploaded = seller.post(
        f"/api/v1/listings/{listing['id']}/photos",
        files={"file": ("journey.jpg", _jpeg(), "image/jpeg")},
        headers={
            **_csrf(seller_csrf),
            "Idempotency-Key": f"journey-photo-{uuid.uuid4().hex}",
        },
    )
    assert uploaded.status_code == 200, uploaded.text
    photo_id = UUID(uploaded.json()["id"])
    assert uploaded.json()["status"] == "processing"
    worker._make_variants(photo_id)

    owner_detail = seller.get(f"/api/v1/listings/{listing['id']}")
    assert owner_detail.status_code == 200, owner_detail.text
    latest = owner_detail.json()["listing"]
    assert latest["photos"][0]["status"] == "ready"
    assert latest["photos"][0]["id"] == str(photo_id)
    submitted = seller.post(
        f"/api/v1/listings/{listing['id']}/submit",
        json={"expected_revision": latest["revision"]},
        headers={
            **_csrf(seller_csrf),
            "Idempotency-Key": f"journey-submit-{uuid.uuid4().hex}",
        },
    )
    assert submitted.status_code == 200, submitted.text
    pending = submitted.json()["listing"]
    assert pending["status"] == ("active" if auto_publish else "pending_review")

    if not auto_publish:
        # The moderator exists only in this test database; approval models the local review boundary.
        moderator = User(
            email=f"journey-moderator-{uuid.uuid4().hex}@example.com",
            display_name="Local test moderator",
            password_hash=hash_password(PASSWORD),
            role="moderator",
            status="active",
        )
        with factory() as db:
            db.add(moderator)
            db.commit()

        moderator_client = _client(integration)
        moderator_login = moderator_client.post(
            "/api/v1/auth/login",
            json={"email": moderator.email, "password": PASSWORD},
        )
        assert moderator_login.status_code == 200, moderator_login.text
        approved = moderator_client.post(
            f"/api/v1/moderation/listings/{listing['id']}/approve",
            json={"expected_revision": pending["revision"]},
            headers=_csrf(moderator_login.json()["csrf_token"]),
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["listing"]["status"] == "active"

    public = _client(integration)
    public_detail = public.get(f"/api/v1/listings/{listing['id']}")
    assert public_detail.status_code == 200, public_detail.text
    public_listing = public_detail.json()["listing"]
    assert public_listing["status"] == "active"
    assert public_listing["seller"]["id"] == seller_id
    assert PHONE not in public_detail.text
    assert "contact_phone" not in public_listing
    public_photo = public.get(f"/api/v1/photos/{photo_id}/768")
    assert public_photo.status_code == 200, public_photo.text
    assert public_photo.headers["content-type"].startswith("image/webp")

    anonymous_reveal = public.post(f"/api/v1/listings/{listing['id']}/phone-reveal")
    assert anonymous_reveal.status_code == 401, anonymous_reveal.text

    buyer = _add_buyer(factory)
    buyer_client = _client(integration)
    buyer_login = buyer_client.post(
        "/api/v1/auth/login",
        json={"email": buyer.email, "password": PASSWORD},
    )
    assert buyer_login.status_code == 200, buyer_login.text
    phone_url = f"/api/v1/listings/{listing['id']}/phone-reveal"
    missing_csrf = buyer_client.post(phone_url)
    assert missing_csrf.status_code == 403, missing_csrf.text
    reveal = buyer_client.post(
        phone_url,
        headers=_csrf(buyer_login.json()["csrf_token"]),
    )
    assert reveal.status_code == 200, reveal.text
    assert reveal.json() == {"phone": PHONE, "messengers": []}

    with factory() as db:
        event = db.scalar(
            select(ContactReveal).where(ContactReveal.listing_id == UUID(listing["id"]))
        )
        assert event is not None
        assert event.user_id == buyer.id
