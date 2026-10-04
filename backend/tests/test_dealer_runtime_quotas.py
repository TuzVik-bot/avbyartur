import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from app.models import Company, DealerTeamMember, Listing, User
from app.security import hash_password


PASSWORD = "dealer-quota-test-password-123"


def _create_user(factory, label: str, *, role: str = "user") -> tuple[uuid.UUID, str]:
    email = f"{label}-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name=label,
            password_hash=hash_password(PASSWORD),
            role=role,
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email


def _client(integration, email: str) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(integration["client"].app)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def _change(value: int) -> dict:
    return {
        "value": value,
        "expected_revision": 0,
        "reason": "Dealer quota behavior test",
        "current_password": PASSWORD,
        "confirmation": "UPDATE_SETTING",
    }


def _listing(owner_id: uuid.UUID, slug: str, *, company_id: uuid.UUID | None, status: str) -> Listing:
    return Listing(
        owner_id=owner_id,
        company_id=company_id,
        slug=slug,
        title=slug,
        description="Quota test listing",
        contact_phone="+375291234567",
        status=status,
        revision=1,
    )


def test_admin_lowered_company_and_private_quotas_block_real_resume_requests(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _create_user(factory, "quota-owner")
    seller_id, seller_email = _create_user(factory, "quota-seller")
    admin_id, admin_email = _create_user(factory, "quota-admin", role="admin")
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    with factory() as db:
        company = Company(
            owner_id=owner_id,
            name=f"Dealer {suffix}",
            slug=f"dealer-{suffix}",
            unp=str(suffix),
            address="Minsk",
            phone="+375291234567",
            status="approved",
            revision=1,
        )
        db.add(company)
        db.flush()
        company_id = company.id
        db.add(DealerTeamMember(
            company_id=company_id,
            user_id=seller_id,
            role="seller",
            status="active",
            revision=1,
            granted_by=owner_id,
        ))
        db.add_all([
            _listing(owner_id, f"company-active-{uuid.uuid4().hex}", company_id=company_id, status="active"),
            _listing(seller_id, f"company-paused-{uuid.uuid4().hex}", company_id=company_id, status="paused"),
            _listing(owner_id, f"private-active-{uuid.uuid4().hex}", company_id=None, status="active"),
            _listing(owner_id, f"private-paused-{uuid.uuid4().hex}", company_id=None, status="paused"),
        ])
        db.commit()
        company_paused = db.query(Listing).filter(Listing.owner_id == seller_id, Listing.company_id == company_id).one()
        private_paused = db.query(Listing).filter(Listing.owner_id == owner_id, Listing.company_id.is_(None), Listing.status == "paused").one()
        company_paused_id, private_paused_id = company_paused.id, private_paused.id

    admin, admin_headers = _client(integration, admin_email)
    owner, owner_headers = _client(integration, owner_email)
    seller, seller_headers = _client(integration, seller_email)
    company_setting = admin.patch(
        "/api/v1/admin/settings/company_listing_quota",
        json=_change(1),
        headers=admin_headers,
    )
    assert company_setting.status_code == 200, company_setting.text
    company_resume = seller.post(
        f"/api/v1/listings/{company_paused_id}/resume",
        json={"expected_revision": 1},
        headers=seller_headers,
    )
    assert company_resume.status_code == 409, company_resume.text
    assert company_resume.json()["code"] == "quota_exceeded"

    private_setting = admin.patch(
        "/api/v1/admin/settings/private_listing_quota",
        json=_change(1),
        headers=admin_headers,
    )
    assert private_setting.status_code == 200, private_setting.text
    private_resume = owner.post(
        f"/api/v1/listings/{private_paused_id}/resume",
        json={"expected_revision": 1},
        headers=owner_headers,
    )
    assert private_resume.status_code == 409, private_resume.text
    assert private_resume.json()["code"] == "quota_exceeded"


def test_company_quota_serializes_concurrent_resumes_across_members(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _create_user(factory, "concurrent-quota-owner")
    seller_id, seller_email = _create_user(factory, "concurrent-quota-seller")
    _, admin_email = _create_user(factory, "concurrent-quota-admin", role="admin")
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    with factory() as db:
        company = Company(
            owner_id=owner_id,
            name=f"Dealer {suffix}",
            slug=f"dealer-{suffix}",
            unp=str(suffix),
            address="Minsk",
            phone="+375291234567",
            status="approved",
            revision=1,
        )
        db.add(company)
        db.flush()
        company_id = company.id
        db.add(DealerTeamMember(
            company_id=company_id,
            user_id=seller_id,
            role="seller",
            status="active",
            revision=1,
            granted_by=owner_id,
        ))
        owner_listing = _listing(owner_id, f"owner-paused-{uuid.uuid4().hex}", company_id=company_id, status="paused")
        seller_listing = _listing(seller_id, f"seller-paused-{uuid.uuid4().hex}", company_id=company_id, status="paused")
        db.add_all([owner_listing, seller_listing])
        db.commit()
        listing_ids = [owner_listing.id, seller_listing.id]

    admin, admin_headers = _client(integration, admin_email)
    changed = admin.patch(
        "/api/v1/admin/settings/company_listing_quota",
        json=_change(1),
        headers=admin_headers,
    )
    assert changed.status_code == 200, changed.text
    owner, owner_headers = _client(integration, owner_email)
    seller, seller_headers = _client(integration, seller_email)
    start = Barrier(2)

    def resume(client: TestClient, headers: dict[str, str], listing_id: uuid.UUID):
        start.wait(timeout=5)
        return client.post(
            f"/api/v1/listings/{listing_id}/resume",
            json={"expected_revision": 1},
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        owner_result, seller_result = list(pool.map(
            lambda args: resume(*args),
            [(owner, owner_headers, listing_ids[0]), (seller, seller_headers, listing_ids[1])],
        ))
    statuses = sorted([owner_result.status_code, seller_result.status_code])
    assert statuses == [200, 409], (owner_result.text, seller_result.text)
    rejected = owner_result if owner_result.status_code == 409 else seller_result
    assert rejected.json()["code"] == "quota_exceeded"
