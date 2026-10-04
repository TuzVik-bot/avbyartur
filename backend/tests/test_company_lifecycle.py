import uuid

import pytest
from app.models import Company, Listing, ListingPhoto, LocationRegion, User
from app.schemas import CompanyInput
from app.security import hash_password
from fastapi.testclient import TestClient
from pydantic import ValidationError

PASSWORD = "company-lifecycle-test-password-123"


@pytest.mark.parametrize("field", ["name", "address", "phone"])
def test_company_required_text_rejects_whitespace_only(field):
    payload = {
        "name": "Pilot Motors",
        "unp": "123456789",
        "address": "Minsk",
        "phone": "+375291234567",
    }
    payload[field] = "   "

    with pytest.raises(ValidationError):
        CompanyInput.model_validate(payload)


def _add_user(factory, *, role: str = "user") -> User:
    email = f"{role}-{uuid.uuid4().hex[:12]}@example.com"
    user = User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password(PASSWORD),
        role=role,
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def test_company_review_listing_publication_and_blocking(integration):
    factory = integration["SessionLocal"]
    company_unp = str(100_000_000 + uuid.uuid4().int % 900_000_000)
    owner = _add_user(factory)
    admin = _add_user(factory, role="admin")
    visitor = _add_user(factory)
    owner_client = TestClient(integration["client"].app, base_url="http://testserver")
    admin_client = TestClient(integration["client"].app, base_url="http://testserver")
    visitor_client = TestClient(integration["client"].app, base_url="http://testserver")
    owner_csrf = _login(owner_client, owner.email)
    admin_csrf = _login(admin_client, admin.email)
    visitor_csrf = _login(visitor_client, visitor.email)

    invalid = owner_client.post(
        "/api/v1/companies",
        json={
            "name": "   ", "unp": "123456789", "address": "Minsk", "phone": "+375291234567",
        },
        headers=_csrf(owner_csrf),
    )
    assert invalid.status_code == 422, invalid.text

    created = owner_client.post(
        "/api/v1/companies",
        json={
            "name": "  Pilot Motors  ", "unp": company_unp, "address": "  Minsk  ",
            "phone": "  +375291234567  ",
        },
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    company = created.json()["company"]
    company_id = company["id"]
    assert (company["name"], company["address"], company["phone"]) == (
        "Pilot Motors", "Minsk", "+375291234567",
    )
    assert company["status"] == "pending"

    duplicate_owner = _add_user(factory)
    duplicate_client = TestClient(integration["client"].app, base_url="http://testserver")
    duplicate_csrf = _login(duplicate_client, duplicate_owner.email)
    duplicate_unp = duplicate_client.post(
        "/api/v1/companies",
        json={
            "name": "Another Motors", "unp": company_unp, "address": "Minsk",
            "phone": "+375291234568",
        },
        headers=_csrf(duplicate_csrf),
    )
    assert duplicate_unp.status_code == 409, duplicate_unp.text
    duplicate_error = duplicate_unp.json()
    assert set(duplicate_error) == {"code", "message", "field_errors", "request_id"}
    assert duplicate_error["code"] == "company_unp_exists"
    assert duplicate_error["message"] == "This UNP is already assigned to a company"
    assert duplicate_error["field_errors"] == {}

    assert owner_client.get("/api/v1/dealers").json()["items"] == []
    assert owner_client.get(f"/api/v1/dealers/{company['slug']}").status_code == 404

    early_draft = owner_client.post(
        "/api/v1/listings/drafts",
        json={"seller_type": "company"},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "company-before-approval"},
    )
    assert early_draft.status_code == 403, early_draft.text
    assert early_draft.json()["code"] == "company_not_approved"

    queued = admin_client.get("/api/v1/moderation/companies")
    assert queued.status_code == 200, queued.text
    assert [item["id"] for item in queued.json()["items"]] == [company_id]
    approved_company = admin_client.post(
        f"/api/v1/moderation/companies/{company_id}/approve",
        json={"expected_revision": company["revision"]},
        headers=_csrf(admin_csrf),
    )
    assert approved_company.status_code == 200, approved_company.text
    assert approved_company.json()["company"]["status"] == "approved"

    with factory() as db:
        region = LocationRegion(slug=f"company-region-{uuid.uuid4().hex[:10]}", name="Minsk region")
        db.add(region)
        db.commit()
        region_id = region.id

    draft_response = owner_client.post(
        "/api/v1/listings/drafts",
        json={
            "seller_type": "company", "manual_make": "Mazda", "manual_model": "3", "year": 2021,
            "mileage_km": 42000, "fuel": "petrol", "transmission": "automatic", "drive": "front",
            "condition": "used", "damaged": False, "parts_only": False,
            "price": {"amount": "14500.00", "currency": "BYN"},
            "region_id": str(region_id), "manual_city": "Minsk",
            "description": "Company lifecycle listing", "contact_phone": "+375291111111",
        },
        headers={**_csrf(owner_csrf), "Idempotency-Key": "company-listing-draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    listing = draft_response.json()["listing"]
    listing_id = listing["id"]
    assert listing["seller"]["type"] == "company"
    assert listing["seller"]["id"] == company_id

    with factory() as db:
        db.add(ListingPhoto(
            listing_id=uuid.UUID(listing_id), storage_name=f"{uuid.uuid4().hex}",
            original_name=f"{uuid.uuid4().hex}.upload", status="ready", position=0,
            is_cover=True, width=48, height=32, idempotency_key="company-ready-photo",
        ))
        db.commit()

    submitted = owner_client.post(
        f"/api/v1/listings/{listing_id}/submit",
        json={"expected_revision": listing["revision"]},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "company-listing-submit"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["listing"]["status"] == "pending_review"
    published = admin_client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve",
        json={"expected_revision": submitted.json()["listing"]["revision"]},
        headers=_csrf(admin_csrf),
    )
    assert published.status_code == 200, published.text
    assert published.json()["listing"]["status"] == "active"

    directory = visitor_client.get("/api/v1/dealers")
    assert directory.status_code == 200, directory.text
    assert [item["id"] for item in directory.json()["items"]] == [company_id]
    assert "unp" not in directory.json()["items"][0]
    detail = visitor_client.get(f"/api/v1/dealers/{company['slug']}")
    assert detail.status_code == 200, detail.text
    dealer_listings = detail.json()["listings"]["items"]
    assert [item["id"] for item in dealer_listings] == [listing_id]
    assert "contact_phone" not in dealer_listings[0]
    public_listing = visitor_client.get(f"/api/v1/listings/{listing_id}")
    assert public_listing.status_code == 200, public_listing.text

    blocked = admin_client.post(
        f"/api/v1/moderation/companies/{company_id}/block",
        json={"expected_revision": approved_company.json()["company"]["revision"], "reason": "Review required"},
        headers=_csrf(admin_csrf),
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["company"]["status"] == "blocked"
    assert visitor_client.get("/api/v1/dealers").json()["items"] == []
    assert visitor_client.get(f"/api/v1/dealers/{company['slug']}").status_code == 404
    assert visitor_client.get(f"/api/v1/listings/{listing_id}").status_code == 404
    search = visitor_client.get("/api/v1/listings", params={"seller_type": "company"})
    assert search.status_code == 200, search.text
    assert listing_id not in [item["id"] for item in search.json()["items"]]
    hidden_phone = visitor_client.post(
        f"/api/v1/listings/{listing_id}/phone-reveal", headers=_csrf(visitor_csrf),
    )
    assert hidden_phone.status_code == 404

    with factory() as db:
        persisted_company = db.get(Company, uuid.UUID(company_id))
        persisted_listing = db.get(Listing, uuid.UUID(listing_id))
        assert persisted_company is not None and persisted_company.status == "blocked"
        assert persisted_listing is not None and persisted_listing.company_id == persisted_company.id


def test_company_business_hours_and_team_profile_permissions(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    admin = _add_user(factory)
    platform_admin = _add_user(factory, role="admin")
    seller = _add_user(factory)
    viewer = _add_user(factory)
    owner_client = TestClient(integration["client"].app, base_url="http://testserver")
    admin_client = TestClient(integration["client"].app, base_url="http://testserver")
    seller_client = TestClient(integration["client"].app, base_url="http://testserver")
    viewer_client = TestClient(integration["client"].app, base_url="http://testserver")
    platform_admin_client = TestClient(integration["client"].app, base_url="http://testserver")
    owner_csrf = _login(owner_client, owner.email)
    admin_csrf = _login(admin_client, admin.email)
    seller_csrf = _login(seller_client, seller.email)
    viewer_csrf = _login(viewer_client, viewer.email)
    platform_admin_csrf = _login(platform_admin_client, platform_admin.email)
    initial_hours = {
        "mon": {"open": "09:00", "close": "18:00"},
        "tue": {"open": "09:00", "close": "18:00"},
        "wed": {"open": "09:00", "close": "18:00"},
        "thu": {"open": "09:00", "close": "18:00"},
        "fri": {"open": "09:00", "close": "18:00"},
        "sat": {"closed": True},
        "sun": {"closed": True},
    }
    owner_payload = {
        "name": "Shared Dealer Profile", "unp": str(100_000_000 + uuid.uuid4().int % 900_000_000),
        "address": "Minsk", "phone": "+375291234567", "business_hours": initial_hours,
    }
    created = owner_client.post("/api/v1/companies", json=owner_payload, headers=_csrf(owner_csrf))
    assert created.status_code == 200, created.text
    company = created.json()["company"]
    company_id = company["id"]
    assert company["business_hours"] == initial_hours

    denied_moderation = admin_client.post(
        f"/api/v1/moderation/companies/{company_id}/approve",
        json={"expected_revision": company["revision"]},
        headers=_csrf(admin_csrf),
    )
    assert denied_moderation.status_code == 403, denied_moderation.text
    approved = platform_admin_client.post(
        f"/api/v1/moderation/companies/{company_id}/approve",
        json={"expected_revision": company["revision"]},
        headers=_csrf(platform_admin_csrf),
    )
    assert approved.status_code == 200, approved.text
    revision = approved.json()["company"]["revision"]

    for member, role in ((admin, "admin"), (seller, "seller"), (viewer, "viewer")):
        added = owner_client.post(
            "/api/v1/dealer/team", json={"user_id": str(member.id), "role": role},
            headers=_csrf(owner_csrf),
        )
        assert added.status_code == 200, added.text

    for client, member, role in (
        (owner_client, owner, "owner"),
        (admin_client, admin, "admin"),
        (seller_client, seller, "seller"),
        (viewer_client, viewer, "viewer"),
    ):
        context = client.get("/api/v1/me")
        assert context.status_code == 200, context.text
        assert context.json()["user"]["company_id"] == company_id
        assert context.json()["user"]["company_role"] == role
        profile = client.get("/api/v1/me/company")
        assert profile.status_code == 200, profile.text
        assert profile.json()["company"]["id"] == company_id
        assert profile.json()["company"]["business_hours"] == initial_hours

    member_company = seller_client.post(
        "/api/v1/companies",
        json={
            "name": "Second Dealer", "unp": str(100_000_000 + uuid.uuid4().int % 900_000_000),
            "address": "Minsk", "phone": "+375291234568",
        },
        headers=_csrf(seller_csrf),
    )
    assert member_company.status_code == 409, member_company.text
    assert member_company.json()["code"] == "user_already_in_company"

    owner_hours = {**initial_hours, "sat": {"open": "10:00", "close": "15:00"}}
    owner_update = owner_client.patch(
        f"/api/v1/companies/{company_id}",
        json={**owner_payload, "business_hours": owner_hours, "expected_revision": revision},
        headers=_csrf(owner_csrf),
    )
    assert owner_update.status_code == 200, owner_update.text
    assert owner_update.json()["company"]["status"] == "approved"
    revision = owner_update.json()["company"]["revision"]

    admin_hours = {**owner_hours, "sun": {"open": "11:00", "close": "14:00"}}
    admin_update = admin_client.patch(
        f"/api/v1/companies/{company_id}",
        json={**owner_payload, "business_hours": admin_hours, "expected_revision": revision},
        headers=_csrf(admin_csrf),
    )
    assert admin_update.status_code == 200, admin_update.text
    assert admin_update.json()["company"]["status"] == "approved"
    revision = admin_update.json()["company"]["revision"]

    denied_payload = {**owner_payload, "expected_revision": revision}
    for client, token in ((seller_client, seller_csrf), (viewer_client, viewer_csrf)):
        denied = client.patch(
            f"/api/v1/companies/{company_id}", json=denied_payload, headers=_csrf(token),
        )
        assert denied.status_code == 403, denied.text

    public = owner_client.get("/api/v1/dealers")
    assert public.status_code == 200, public.text
    public_company = next(item for item in public.json()["items"] if item["id"] == company_id)
    assert public_company["business_hours"] == admin_hours
    assert "unp" not in public_company and "phone" not in public_company
    detail = owner_client.get(f"/api/v1/dealers/{company["slug"]}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["company"]["business_hours"] == admin_hours

    other_owner = _add_user(factory)
    other_unp = str(100_000_000 + uuid.uuid4().int % 900_000_000)
    with factory() as db:
        db.add(Company(
            owner_id=other_owner.id, name="Other Dealer", slug=f"other-{other_unp}",
            unp=other_unp, address="Minsk", phone="+375291234569", status="approved",
        ))
        db.commit()
    duplicate_unp = admin_client.patch(
        f"/api/v1/companies/{company_id}",
        json={**owner_payload, "unp": other_unp, "business_hours": admin_hours, "expected_revision": revision},
        headers=_csrf(admin_csrf),
    )
    assert duplicate_unp.status_code == 409, duplicate_unp.text
    assert duplicate_unp.json()["code"] == "company_unp_exists"

    critical_update = admin_client.patch(
        f"/api/v1/companies/{company_id}",
        json={
            **owner_payload, "name": "Updated Shared Dealer", "business_hours": admin_hours,
            "expected_revision": revision,
        },
        headers=_csrf(admin_csrf),
    )
    assert critical_update.status_code == 200, critical_update.text
    assert critical_update.json()["company"]["status"] == "pending"
    assert critical_update.json()["company"]["business_hours"] == admin_hours
