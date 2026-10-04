import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from PIL import Image
from sqlalchemy import event, func, select

from app.catalog_import import import_catalog
from app.models import (
    AuditEvent,
    CatalogBodyType,
    CatalogImport,
    CatalogMake,
    CatalogModel,
    Company,
    ExchangeRate,
    Listing,
    ListingCategoryDetails,
    ListingPhoto,
    ListingStatusEvent,
    LocationCity,
    LocationRegion,
    User,
    WorkerJob,
)
from app.security import hash_password
from app.worker import _claim_one, _run_job

PASSWORD = "pilot-test-password-123"


def assert_photo_job_is_due(factory, photo_id: str) -> WorkerJob:
    with factory() as db:
        job = db.scalar(select(WorkerJob).where(WorkerJob.job_key == f"photo.process:{photo_id}"))
        database_now = db.scalar(select(func.now()))
    application_now = datetime.now(timezone.utc)
    assert job is not None, f"Photo upload did not persist a worker job for {photo_id}"
    assert job.status == "queued", f"Photo job is not queued: {job.status}"
    assert job.run_after <= database_now, (
        f"Photo job is not due by database time: run_after={job.run_after}, "
        f"database_now={database_now}, application_now={application_now}"
    )
    return job


def add_user(factory, email: str, role: str = "user") -> User:
    user = User(email=email, display_name=email.split("@")[0], password_hash=hash_password(PASSWORD), role=role, status="active")
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def login(client, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    token = response.json()["csrf_token"]
    assert client.cookies.get("avtorinok_session")
    assert client.cookies.get("avtorinok_csrf") == token
    assert client.get("/api/v1/me").json()["csrf_token"] == token
    return token


def test_retention_archived_published_listing_returns_gone(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"retained-public-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = uuid.uuid4()
    with factory() as db:
        db.add(Listing(
            id=listing_id,
            owner_id=owner.id,
            slug=f"retained-public-{uuid.uuid4().hex}",
            status="archived",
            revision=3,
            title="Previously published listing",
            description="Synthetic listing retained after sale",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
        ))
        db.add_all([
            ListingStatusEvent(
                listing_id=listing_id,
                actor_id=owner.id,
                from_status="pending_review",
                to_status="active",
                revision=2,
            ),
            ListingStatusEvent(
                listing_id=listing_id,
                actor_id=None,
                actor_kind="system",
                from_status="sold",
                to_status="archived",
                revision=3,
                reason="sold_retention_expired",
            ),
        ])
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{listing_id}")

    assert response.status_code == 410, response.text


def test_retention_archived_never_published_listing_stays_hidden(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"retained-private-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = uuid.uuid4()
    with factory() as db:
        db.add(Listing(
            id=listing_id,
            owner_id=owner.id,
            slug=f"retained-private-{uuid.uuid4().hex}",
            status="archived",
            revision=2,
            title="Never published listing",
            description="Synthetic private listing",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
        ))
        db.add(ListingStatusEvent(
            listing_id=listing_id,
            actor_id=None,
            actor_kind="system",
            from_status="sold",
            to_status="archived",
            revision=2,
            reason="sold_retention_expired",
        ))
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{listing_id}")

    assert response.status_code == 404, response.text


def test_non_retention_archived_published_listing_returns_gone(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"archived-other-{uuid.uuid4().hex[:8]}@example.com")
    listing_id = uuid.uuid4()
    with factory() as db:
        db.add(Listing(
            id=listing_id,
            owner_id=owner.id,
            slug=f"archived-other-{uuid.uuid4().hex}",
            status="archived",
            revision=3,
            title="Removed listing",
            description="Synthetic listing archived for another reason",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
        ))
        db.add_all([
            ListingStatusEvent(
                listing_id=listing_id,
                actor_id=owner.id,
                from_status="pending_review",
                to_status="active",
                revision=2,
            ),
            ListingStatusEvent(
                listing_id=listing_id,
                actor_id=owner.id,
                from_status="active",
                to_status="archived",
                revision=3,
                reason="seller_removed",
            ),
        ])
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{listing_id}")

    assert response.status_code == 410, response.text
    assert response.json()["code"] == "gone"


def test_listing_search_uses_a_bounded_number_of_relation_queries(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"search-batch-{uuid.uuid4().hex[:8]}@example.com")
    listings = [
        Listing(
            owner_id=owner.id,
            slug=f"search-batch-{uuid.uuid4().hex}",
            status="active",
            category_code="trucks",
            title=f"Synthetic truck {index}",
            description="Synthetic load test listing",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
        )
        for index in range(25)
    ]
    listings[0].category_details = ListingCategoryDetails(
        category_code="trucks",
        details={"vehicle_type": "truck", "payload_kg": 18_500},
    )
    with factory() as db:
        db.add_all(listings)
        db.commit()
        category_details_listing_id = str(listings[0].id)

    client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    statements = []

    def record_select(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)

    engine = integration["engine"]
    event.listen(engine, "before_cursor_execute", record_select)
    try:
        response = client.get("/api/v1/listings", params={"category_code": "trucks", "page_size": 25})
    finally:
        event.remove(engine, "before_cursor_execute", record_select)

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 25
    details_listing = next(
        item for item in response.json()["items"] if item["id"] == category_details_listing_id
    )
    assert details_listing["category_details"] == {"vehicle_type": "truck", "payload_kg": 18_500}
    category_details_relation_selects = [
        statement
        for statement in statements
        if "from listing_category_details" in statement.casefold()
    ]
    assert category_details_relation_selects == [], (
        "listing search must not lazy-load category details once per result; "
        f"observed {len(category_details_relation_selects)} relation SELECTs"
    )
    assert len(statements) <= 6


def test_login_csrf_draft_idempotency_and_ownership(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"seller-{uuid.uuid4().hex[:8]}@example.com")
    other = add_user(factory, f"other-{uuid.uuid4().hex[:8]}@example.com")
    client = integration["client"]
    client.cookies.clear()
    assert client.get("/api/v1/me").status_code == 401
    assert client.post("/api/v1/listings/drafts", json={}).status_code == 401

    csrf = login(client, owner.email)
    payload = {"seller_type": "private", "year": 2019, "price": {"amount": "12345.67", "currency": "USD"}}
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "draft-create-1"}
    assert client.post("/api/v1/listings/drafts", json=payload, headers={"Idempotency-Key": "missing-csrf"}).status_code == 403
    first = client.post("/api/v1/listings/drafts", json=payload, headers=headers)
    assert first.status_code == 200, first.text
    listing = first.json()["listing"]
    assert listing["status"] == "draft"
    assert listing["price"]["amount"] == "12345.67"
    duplicate = client.post("/api/v1/listings/drafts", json=payload, headers=headers)
    assert duplicate.json()["listing"]["id"] == listing["id"]

    outsider_client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    login(outsider_client, other.email)
    hidden = outsider_client.get(f"/api/v1/listings/{listing['id']}")
    assert hidden.status_code == 404
    assert client.get("/api/v1/me/listings").json()["items"][0]["id"] == listing["id"]


def test_photo_queue_revision_moderation_search_and_contact(integration, tmp_path):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"seller-flow-{uuid.uuid4().hex[:8]}@example.com")
    moderator = add_user(factory, f"moderator-{uuid.uuid4().hex[:8]}@example.com", role="moderator")
    visitor = add_user(factory, f"visitor-{uuid.uuid4().hex[:8]}@example.com")
    with factory() as db:
        make = CatalogMake(slug=f"make-{uuid.uuid4().hex[:8]}", name="BMW", aliases=["БМВ"], external_id=None)
        region = LocationRegion(slug=f"region-{uuid.uuid4().hex[:8]}", name="Minsk region")
        db.add_all([make, region])
        db.flush()
        model = CatalogModel(make_id=make.id, slug=f"model-{uuid.uuid4().hex[:8]}", name="3 Series", aliases=["3er"])
        body = CatalogBodyType(slug=f"sedan-{uuid.uuid4().hex[:8]}", name="Sedan")
        db.add_all([model, body])
        db.flush()
        city = LocationCity(region_id=region.id, slug=f"city-{uuid.uuid4().hex[:8]}", name="Minsk")
        db.add(city)
        db.commit()
        make_id, model_id, body_id, region_id, city_id = make.id, model.id, body.id, region.id, city.id

    client = integration["client"]
    csrf = login(client, owner.email)
    listing_payload = {
        "seller_type": "private", "make_id": str(make_id), "model_id": str(model_id), "body_type_id": str(body_id),
        "year": 2020, "mileage_km": 44000, "fuel": "petrol", "transmission": "automatic", "drive": "all",
        "condition": "used", "damaged": False, "parts_only": False,
        "price": {"amount": "19000.50", "currency": "BYN"},
        "region_id": str(region_id), "city_id": str(city_id), "description": "Clean pilot listing",
        "contact_phone": "+375291234567", "vin": "1HGCM82633A004352",
    }
    response = client.post("/api/v1/listings/drafts", json=listing_payload, headers={"X-CSRF-Token": csrf, "Idempotency-Key": "full-draft"})
    assert response.status_code == 200, response.text
    listing = response.json()["listing"]
    listing_id = listing["id"]

    image_stream = io.BytesIO()
    Image.new("RGB", (48, 32), (22, 70, 100)).save(image_stream, format="JPEG")
    uploaded = client.post(
        f"/api/v1/listings/{listing_id}/photos",
        files={"file": ("car.jpg", image_stream.getvalue(), "image/jpeg")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "photo-upload-1"},
    )
    assert uploaded.status_code == 200, uploaded.text
    photo_id = uploaded.json()["id"]
    assert client.get(f"/api/v1/listings/{listing_id}/photos").json()["items"][0]["status"] == "processing"

    expected_job = assert_photo_job_is_due(factory, photo_id)
    job_id = _claim_one("integration-worker")
    assert job_id == expected_job.id
    with factory() as db:
        job = db.get(WorkerJob, job_id)
        job.lease_until = job.created_at
        db.commit()
    recovered = _claim_one("integration-worker")
    assert recovered == job_id
    _run_job(job_id, "integration-worker")
    with factory() as db:
        photo = db.get(ListingPhoto, uuid.UUID(photo_id))
        assert photo.status == "ready"
        assert (integration["media_root"] / photo.storage_name / "768.webp").is_file()
    status_list = client.get(f"/api/v1/listings/{listing_id}/photos").json()["items"]
    assert status_list[0]["status"] == "ready"

    submit = client.post(
        f"/api/v1/listings/{listing_id}/submit", json={"expected_revision": listing["revision"] + 1},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "submit-1"},
    )
    assert submit.status_code == 200, submit.text
    pending = submit.json()["listing"]
    assert pending["status"] == "pending_review"
    mod_client = integration["client"].__class__(client.app, base_url="http://testserver")
    mod_csrf = login(mod_client, moderator.email)
    pending_queue = mod_client.get("/api/v1/moderation/listings")
    assert pending_queue.status_code == 200, pending_queue.text
    assert listing_id in [item["id"] for item in pending_queue.json()["items"]]
    active_before_approval = mod_client.get("/api/v1/moderation/listings", params={"status": "active"})
    assert listing_id not in [item["id"] for item in active_before_approval.json()["items"]]
    rejected_status = mod_client.get("/api/v1/moderation/listings", params={"status": "rejected"})
    assert rejected_status.status_code == 422
    stale = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve", json={"expected_revision": pending["revision"] - 1},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert stale.status_code == 409
    approved = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve", json={"expected_revision": pending["revision"]},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert approved.status_code == 200, approved.text
    active_revision = approved.json()["listing"]["revision"]
    pending_after_approval = mod_client.get("/api/v1/moderation/listings")
    assert listing_id not in [item["id"] for item in pending_after_approval.json()["items"]]
    active_queue = mod_client.get("/api/v1/moderation/listings", params={"status": "active"})
    assert listing_id in [item["id"] for item in active_queue.json()["items"]]
    approval_of_active = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve",
        json={"expected_revision": active_revision},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert approval_of_active.status_code == 409
    rejection_of_active = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/reject",
        json={"expected_revision": active_revision, "reason": "Not pending"},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert rejection_of_active.status_code == 409
    detail = client.get(f"/api/v1/listings/{listing_id}").json()["listing"]
    assert detail["status"] == "active"
    assert detail["body_type"] == "Sedan"
    assert "vin" not in detail
    assert "phone" not in detail
    rate_date = datetime.now(timezone.utc).date().isoformat()
    fetched_at = datetime.now(timezone.utc)
    with factory() as db:
        rate = db.scalar(select(ExchangeRate).where(
            ExchangeRate.currency == "USD", ExchangeRate.rate_date == rate_date,
        ))
        if rate is None:
            rate = ExchangeRate(currency="USD", rate_date=rate_date)
            db.add(rate)
        rate.official_rate = Decimal("3.000000")
        rate.scale = 1
        rate.source = "test"
        rate.fetched_at = fetched_at
        db.commit()
    result = client.get("/api/v1/listings", params={"q": "BMW", "currency": "BYN", "price_min": "18000"})
    assert result.status_code == 200, result.text
    assert [item["id"] for item in result.json()["items"]] == [listing_id]
    aliases = client.get("/api/v1/catalog/makes", params={"q": "БМВ"})
    assert [item["id"] for item in aliases.json()["items"]] == [str(make_id)]

    visitor_client = integration["client"].__class__(client.app, base_url="http://testserver")
    visitor_csrf = login(visitor_client, visitor.email)
    phone = visitor_client.post(f"/api/v1/listings/{listing_id}/phone-reveal", headers={"X-CSRF-Token": visitor_csrf})
    assert phone.status_code == 200
    assert phone.json()["phone"] == "+375291234567"

    stale_block = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/block",
        json={"expected_revision": active_revision - 1, "reason": "Fraudulent listing"},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert stale_block.status_code == 409
    missing_revision = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/block",
        json={"reason": "Fraudulent listing"},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert missing_revision.status_code == 422
    missing_reason = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/block",
        json={"expected_revision": active_revision},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert missing_reason.status_code == 422
    assert missing_reason.json()["code"] == "reason_required"

    reason = "Verified prohibited vehicle listing"
    blocked = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/block",
        json={"expected_revision": active_revision, "reason": f"  {reason}  "},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["listing"]["status"] == "blocked"
    assert blocked.json()["listing"]["revision"] == active_revision + 1
    assert blocked.json()["listing"]["moderation_reason"] == reason
    assert client.get(f"/api/v1/listings/{listing_id}").status_code == 404
    blocked_phone = visitor_client.post(
        f"/api/v1/listings/{listing_id}/phone-reveal", headers={"X-CSRF-Token": visitor_csrf}
    )
    assert blocked_phone.status_code == 404
    blocked_photo = visitor_client.get(f"/api/v1/photos/{photo_id}/768")
    assert blocked_photo.status_code == 404
    active_after_block = mod_client.get("/api/v1/moderation/listings", params={"status": "active"})
    assert listing_id not in [item["id"] for item in active_after_block.json()["items"]]
    with factory() as db:
        status_event = db.scalar(select(ListingStatusEvent).where(
            ListingStatusEvent.listing_id == uuid.UUID(listing_id), ListingStatusEvent.to_status == "blocked"
        ))
        audit_event = db.scalar(select(AuditEvent).where(
            AuditEvent.entity_type == "listing", AuditEvent.entity_id == uuid.UUID(listing_id), AuditEvent.action == "blocked"
        ))
        assert status_event is not None
        assert status_event.actor_id == moderator.id
        assert status_event.from_status == "active"
        assert status_event.revision == active_revision + 1
        assert status_event.reason == reason
        assert audit_event is not None
        assert audit_event.actor_id == moderator.id
        assert audit_event.details == {"reason": reason, "revision": active_revision}


def test_company_review_ownership_and_session_selected_seller(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"dealer-owner-{uuid.uuid4().hex[:8]}@example.com")
    other = add_user(factory, f"dealer-other-{uuid.uuid4().hex[:8]}@example.com")
    moderator = add_user(factory, f"dealer-mod-{uuid.uuid4().hex[:8]}@example.com", role="moderator")
    admin = add_user(factory, f"dealer-admin-{uuid.uuid4().hex[:8]}@example.com", role="admin")
    client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    owner_csrf = login(client, owner.email)
    created = client.post(
        "/api/v1/companies", json={"name": "North Motors", "unp": "123456789", "address": "Minsk, Main street 1", "phone": "+375291111111"},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert created.status_code == 200, created.text
    company = created.json()["company"]
    assert company["status"] == "pending"
    public_client = integration["client"].__class__(client.app, base_url="http://testserver")
    assert all(item["slug"] != company["slug"] for item in public_client.get("/api/v1/dealers", params={"page_size": 50}).json()["items"])
    assert public_client.get(f"/api/v1/dealers/{company['slug']}").status_code == 404
    assert client.post(
        "/api/v1/listings/drafts", json={"seller_type": "company", "company_id": str(uuid.uuid4())},
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "pending-company-draft"},
    ).status_code == 403

    mod_client = integration["client"].__class__(client.app, base_url="http://testserver")
    mod_csrf = login(mod_client, moderator.email)
    moderator_approval = mod_client.post(
        f"/api/v1/moderation/companies/{company['id']}/approve",
        json={"expected_revision": company["revision"]}, headers={"X-CSRF-Token": mod_csrf}
    )
    assert moderator_approval.status_code == 403
    with factory() as db:
        assert db.scalar(select(Company).where(Company.id == uuid.UUID(company["id"]))).status == "pending"

    admin_client = integration["client"].__class__(client.app, base_url="http://testserver")
    admin_csrf = login(admin_client, admin.email)
    approved = admin_client.post(
        f"/api/v1/moderation/companies/{company['id']}/approve",
        json={"expected_revision": company["revision"]}, headers={"X-CSRF-Token": admin_csrf}
    )
    assert approved.status_code == 200, approved.text
    dealer_directory = public_client.get("/api/v1/dealers", params={"page_size": 50})
    assert dealer_directory.status_code == 200, dealer_directory.text
    public_company = next(item for item in dealer_directory.json()["items"] if item["slug"] == company["slug"])
    assert public_company["name"] == company["name"]
    assert "unp" not in public_company
    assert "phone" not in public_company
    approved_dealer = public_client.get(f"/api/v1/dealers/{company['slug']}")
    assert approved_dealer.status_code == 200, approved_dealer.text
    assert approved_dealer.json()["listings"]["items"] == []
    assert approved_dealer.json()["listings"]["pagination"] == {
        "page": 1, "page_size": 25, "total": 0, "pages": 0,
    }

    with factory() as db:
        region = LocationRegion(slug=f"dealer-region-{uuid.uuid4().hex[:8]}", name="Minsk region")
        db.add(region)
        db.commit()
        region_id = region.id
    selected = client.post(
        "/api/v1/listings/drafts",
        json={
            "seller_type": "company", "manual_make": "Toyota", "manual_model": "Corolla", "year": 2021,
            "mileage_km": 42000, "fuel": "petrol", "transmission": "automatic", "drive": "front",
            "condition": "used", "damaged": False, "parts_only": False,
            "price": {"amount": "14500.00", "currency": "BYN"}, "region_id": str(region_id),
            "manual_city": "Minsk", "description": "Company seller workflow integration listing",
            "contact_phone": "+375291111111",
        },
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "approved-company-draft"},
    )
    assert selected.status_code == 200, selected.text
    listing = selected.json()["listing"]
    listing_id = listing["id"]
    assert listing["seller"]["id"] == company["id"]
    assert listing["seller"]["type"] == "company"

    image_stream = io.BytesIO()
    Image.new("RGB", (48, 32), (22, 70, 100)).save(image_stream, format="JPEG")
    uploaded = client.post(
        f"/api/v1/listings/{listing_id}/photos",
        files={"file": ("dealer-car.jpg", image_stream.getvalue(), "image/jpeg")},
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "approved-company-photo"},
    )
    assert uploaded.status_code == 200, uploaded.text
    photo_id = uploaded.json()["id"]
    expected_job = assert_photo_job_is_due(factory, photo_id)
    job_id = _claim_one("company-workflow-integration")
    assert job_id == expected_job.id
    _run_job(job_id, "company-workflow-integration")
    assert client.get(f"/api/v1/listings/{listing_id}/photos").json()["items"][0]["status"] == "ready"

    submitted = client.post(
        f"/api/v1/listings/{listing_id}/submit", json={"expected_revision": listing["revision"] + 1},
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "approved-company-submit"},
    )
    assert submitted.status_code == 200, submitted.text
    pending_listing = submitted.json()["listing"]
    assert pending_listing["status"] == "pending_review"
    assert public_client.get(f"/api/v1/dealers/{company['slug']}").json()["listings"]["items"] == []
    published = mod_client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve",
        json={"expected_revision": pending_listing["revision"]},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert published.status_code == 200, published.text
    assert published.json()["listing"]["status"] == "active"
    dealer_page = public_client.get(f"/api/v1/dealers/{company['slug']}")
    assert dealer_page.status_code == 200, dealer_page.text
    dealer_listings = dealer_page.json()["listings"]["items"]
    assert [item["id"] for item in dealer_listings] == [listing_id]
    assert dealer_page.json()["listings"]["pagination"] == {
        "page": 1, "page_size": 25, "total": 1, "pages": 1,
    }
    assert dealer_listings[0]["seller"] == {
        "type": "company", "id": company["id"], "name": company["name"], "slug": company["slug"],
    }
    assert "modification" not in dealer_listings[0]
    assert "make_id" not in dealer_listings[0]["make"]

    other_client = integration["client"].__class__(client.app, base_url="http://testserver")
    other_csrf = login(other_client, other.email)
    wrong_owner_listing = other_client.post(
        "/api/v1/listings/drafts", json={"seller_type": "company", "company_id": company["id"]},
        headers={"X-CSRF-Token": other_csrf, "Idempotency-Key": "other-owner-company-draft"},
    )
    assert wrong_owner_listing.status_code == 403
    denied = other_client.patch(
        f"/api/v1/companies/{company['id']}", json={"name": "Changed Name", "unp": "987654321", "address": "Minsk, Another 5", "phone": "+375292222222", "expected_revision": company["revision"]},
        headers={"X-CSRF-Token": other_csrf},
    )
    assert denied.status_code == 404

    blocked = mod_client.post(
        f"/api/v1/moderation/companies/{company['id']}/block",
        json={"expected_revision": company["revision"] + 1, "reason": "Dealer review revoked"},
        headers={"X-CSRF-Token": mod_csrf},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["company"]["status"] == "blocked"


def test_dealer_detail_paginates_active_listings(integration):
    factory = integration["SessionLocal"]
    suffix = uuid.uuid4().hex[:10]
    owner = add_user(factory, f"dealer-page-{suffix}@example.com")
    with factory() as db:
        company = Company(
            owner_id=owner.id,
            name=f"Paged Motors {suffix}",
            slug=f"paged-motors-{suffix}",
            unp=suffix[:9],
            address="Minsk, Test street 1",
            phone="+375291234567",
            status="approved",
        )
        db.add(company)
        db.flush()
        listings = [
            Listing(
                owner_id=owner.id,
                company_id=company.id,
                slug=f"paged-listing-{suffix}-{index}",
                status="active",
                title=f"Paged car {index}",
                description="Synthetic dealer listing",
                contact_phone="+375291234567",
                damaged=False,
                parts_only=False,
            )
            for index in range(2)
        ]
        db.add_all(listings)
        db.commit()
        listing_ids = {str(listing.id) for listing in listings}

    client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    first_page = client.get(f"/api/v1/dealers/{company.slug}", params={"page": 1, "page_size": 1})
    second_page = client.get(f"/api/v1/dealers/{company.slug}", params={"page": 2, "page_size": 1})

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    first_listings = first_page.json()["listings"]
    second_listings = second_page.json()["listings"]
    assert len(first_listings["items"]) == 1
    assert len(second_listings["items"]) == 1
    assert first_listings["items"][0]["id"] != second_listings["items"][0]["id"]
    assert {first_listings["items"][0]["id"], second_listings["items"][0]["id"]} == listing_ids
    assert first_listings["pagination"] == {"page": 1, "page_size": 1, "total": 2, "pages": 2}
    assert second_listings["pagination"] == {"page": 2, "page_size": 1, "total": 2, "pages": 2}


def test_pending_listing_can_be_blocked(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"pending-block-owner-{uuid.uuid4().hex[:8]}@example.com")
    moderator = add_user(factory, f"pending-block-mod-{uuid.uuid4().hex[:8]}@example.com", role="moderator")
    listing = Listing(
        owner_id=owner.id,
        slug=f"pending-block-{uuid.uuid4().hex}",
        status="pending_review",
        revision=7,
        submitted_revision=7,
        title="Pending moderation listing",
        manual_make="Test Make",
        manual_model="Test Model",
        year=2018,
        mileage_km=80000,
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        description="Test listing",
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        listing_id = listing.id

    moderator_client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    csrf = login(moderator_client, moderator.email)
    blocked = moderator_client.post(
        f"/api/v1/moderation/listings/{listing_id}/block",
        json={"expected_revision": 7, "reason": "Pending listing violates policy"},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["listing"]["status"] == "blocked"
    assert blocked.json()["listing"]["revision"] == 8


def test_blocked_company_hides_active_listing_contacts_and_photos(integration):
    factory = integration["SessionLocal"]
    app = integration["client"].app
    suffix = uuid.uuid4().hex[:8]
    owner = add_user(factory, f"published-dealer-owner-{suffix}@example.com")
    moderator = add_user(factory, f"published-dealer-mod-{suffix}@example.com", role="moderator")
    visitor = add_user(factory, f"published-dealer-visitor-{suffix}@example.com")
    company_slug = f"published-motors-{suffix}"
    company = Company(
        owner_id=owner.id,
        name=f"Published Motors {suffix}",
        slug=company_slug,
        unp=f"{uuid.uuid4().int % 1_000_000_000:09d}",
        address="Minsk, Market street 4",
        phone="+375291111111",
        status="approved",
    )

    storage_name = f"company-photo-{suffix}"
    variant_dir = integration["media_root"] / storage_name
    variant_dir.mkdir(parents=True)
    image_path = variant_dir / "768.webp"
    Image.new("RGB", (64, 48), (32, 96, 128)).save(image_path, format="WEBP")
    with factory() as db:
        db.add(company)
        db.flush()
        listing = Listing(
            owner_id=owner.id,
            company_id=company.id,
            slug=f"published-company-listing-{suffix}",
            status="active",
            revision=2,
            submitted_revision=1,
            title="Published company vehicle",
            manual_make="Test Make",
            manual_model="Test Model",
            year=2020,
            mileage_km=44000,
            condition="used",
            contact_phone="+375293333333",
            damaged=False,
            parts_only=False,
            description="A published listing for company-block access coverage.",
        )
        db.add(listing)
        db.flush()
        photo = ListingPhoto(
            listing_id=listing.id,
            storage_name=storage_name,
            original_name=f"{suffix}.jpg",
            status="ready",
            position=0,
            is_cover=True,
            width=64,
            height=48,
        )
        db.add(photo)
        db.commit()
        company_id = company.id
        listing_id = listing.id
        photo_id = photo.id

    public_client = integration["client"].__class__(app, base_url="http://testserver")
    visitor_client = integration["client"].__class__(app, base_url="http://testserver")
    visitor_csrf = login(visitor_client, visitor.email)
    dealer_before = public_client.get(f"/api/v1/dealers/{company_slug}")
    assert dealer_before.status_code == 200, dealer_before.text
    assert [item["id"] for item in dealer_before.json()["listings"]["items"]] == [str(listing_id)]
    listing_before = public_client.get(f"/api/v1/listings/{listing_id}")
    assert listing_before.status_code == 200, listing_before.text
    phone_before = visitor_client.post(
        f"/api/v1/listings/{listing_id}/phone-reveal", headers={"X-CSRF-Token": visitor_csrf}
    )
    assert phone_before.status_code == 200, phone_before.text
    assert phone_before.json()["phone"] == "+375293333333"
    photo_before = public_client.get(f"/api/v1/photos/{photo_id}/768")
    assert photo_before.status_code == 200, photo_before.text
    assert photo_before.content == image_path.read_bytes()

    moderator_client = integration["client"].__class__(app, base_url="http://testserver")
    moderator_csrf = login(moderator_client, moderator.email)
    blocked = moderator_client.post(
        f"/api/v1/moderation/companies/{company_id}/block",
        json={"expected_revision": 1, "reason": "Published company review revoked"},
        headers={"X-CSRF-Token": moderator_csrf},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["company"]["status"] == "blocked"

    assert public_client.get(f"/api/v1/dealers/{company_slug}").status_code == 404
    assert public_client.get(f"/api/v1/listings/{listing_id}").status_code == 404
    assert visitor_client.post(
        f"/api/v1/listings/{listing_id}/phone-reveal", headers={"X-CSRF-Token": visitor_csrf}
    ).status_code == 404
    assert public_client.get(f"/api/v1/photos/{photo_id}/768").status_code == 404


def test_heif_upload_worker_moderation_and_public_photo_delivery(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"heif-owner-{uuid.uuid4().hex[:8]}@example.com")
    moderator = add_user(factory, f"heif-mod-{uuid.uuid4().hex[:8]}@example.com", role="moderator")
    with factory() as db:
        suffix = uuid.uuid4().hex[:8]
        make = CatalogMake(slug=f"heif-make-{suffix}", name="BMW", aliases=[], external_id=None)
        region = LocationRegion(slug=f"heif-region-{suffix}", name="Minsk region")
        db.add_all([make, region])
        db.flush()
        model = CatalogModel(make_id=make.id, slug=f"heif-model-{suffix}", name="3 Series", aliases=[])
        body = CatalogBodyType(slug=f"heif-sedan-{suffix}", name="Sedan")
        db.add_all([model, body])
        db.flush()
        city = LocationCity(region_id=region.id, slug=f"heif-city-{suffix}", name="Minsk")
        db.add(city)
        db.commit()
        make_id, model_id, body_id, region_id, city_id = make.id, model.id, body.id, region.id, city.id

    client = integration["client"].__class__(integration["client"].app, base_url="http://testserver")
    csrf = login(client, owner.email)
    draft_response = client.post(
        "/api/v1/listings/drafts",
        json={
            "seller_type": "private", "make_id": str(make_id), "model_id": str(model_id),
            "body_type_id": str(body_id), "year": 2020, "mileage_km": 44000,
            "fuel": "petrol", "transmission": "automatic", "drive": "all",
            "condition": "used", "damaged": False, "parts_only": False,
            "price": {"amount": "19000.50", "currency": "BYN"},
            "region_id": str(region_id), "city_id": str(city_id),
            "description": "HEIF photo acceptance listing", "contact_phone": "+375291234567",
        },
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "heif-listing-draft"},
    )
    assert draft_response.status_code == 200, draft_response.text
    listing = draft_response.json()["listing"]
    listing_id = listing["id"]

    exif = Image.Exif()
    exif[274] = 6
    exif[306] = "2026:09:27 01:02:03"
    heif_stream = io.BytesIO()
    Image.new("RGB", (80, 40), (22, 70, 100)).save(heif_stream, format="HEIF", quality=100, exif=exif)
    uploaded = client.post(
        f"/api/v1/listings/{listing_id}/photos",
        files={"file": ("vehicle.heic", heif_stream.getvalue(), "image/heic")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "heif-photo-upload"},
    )
    assert uploaded.status_code == 200, uploaded.text
    photo_id = uploaded.json()["id"]
    assert client.get(f"/api/v1/listings/{listing_id}/photos").json()["items"][0]["status"] == "processing"

    expected_job = assert_photo_job_is_due(factory, photo_id)
    job_id = _claim_one("heif-acceptance-worker")
    assert job_id == expected_job.id
    _run_job(job_id, "heif-acceptance-worker")
    with factory() as db:
        photo = db.get(ListingPhoto, uuid.UUID(photo_id))
        assert photo.status == "ready"
        assert (integration["media_root"] / photo.storage_name / "768.webp").is_file()
    assert client.get(f"/api/v1/listings/{listing_id}/photos").json()["items"][0]["status"] == "ready"

    submitted = client.post(
        f"/api/v1/listings/{listing_id}/submit",
        json={"expected_revision": listing["revision"] + 1},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "heif-submit"},
    )
    assert submitted.status_code == 200, submitted.text
    pending = submitted.json()["listing"]
    assert pending["status"] == "pending_review"

    moderator_client = integration["client"].__class__(client.app, base_url="http://testserver")
    moderator_csrf = login(moderator_client, moderator.email)
    approved = moderator_client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve",
        json={"expected_revision": pending["revision"]},
        headers={"X-CSRF-Token": moderator_csrf},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["listing"]["status"] == "active"

    public_client = integration["client"].__class__(client.app, base_url="http://testserver")
    delivered = public_client.get(f"/api/v1/photos/{photo_id}/768")
    assert delivered.status_code == 200, delivered.text
    assert delivered.headers["content-type"].startswith("image/webp")
    with Image.open(io.BytesIO(delivered.content)) as public_image:
        assert public_image.format == "WEBP"
        assert not public_image.getexif()
        assert public_image.size == (40, 80)


def test_catalog_import_dry_run_idempotency_and_manual_override(integration, tmp_path):
    factory = integration["SessionLocal"]
    suffix = uuid.uuid4().hex[:8]
    document = {
        "schema_version": 1,
        "source": {"name": "Wikidata", "license": "CC0 1.0", "retrieved_at": "2026-09-27T00:00:00Z", "query_url": "https://query.wikidata.org/"},
        "makes": [{
            "qid": f"Q{suffix}", "name": "Test Make", "slug": f"test-make-{suffix}", "aliases": ["TM"],
            "models": [{"qid": f"Q{suffix}1", "name": "Test Model", "slug": f"test-model-{suffix}", "aliases": [],
                        "generations": [{"qid": f"Q{suffix}2", "name": "Gen 1", "year_from": 2001, "year_to": None, "body_variants": []}]}],
        }],
        "body_types": [{"name": "Sedan", "slug": f"sedan-{suffix}"}],
        "regions": [{"name": "Test Region", "slug": f"test-region-{suffix}", "cities": [{"name": "Test City", "slug": f"test-city-{suffix}"}]}],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with factory() as db:
        dry = import_catalog(db, path, dry_run=True)
        assert dry["status"] == "dry_run"
        assert db.scalar(select(CatalogMake).where(CatalogMake.slug == f"test-make-{suffix}")) is None
        applied = import_catalog(db, path)
        make = db.scalar(select(CatalogMake).where(CatalogMake.slug == f"test-make-{suffix}"))
        assert applied["status"] == "imported"
        assert make is not None and make.external_id == f"wikidata:Q{suffix}"
        make.manual_override = True
        make.name = "Operator correction"
        db.commit()

        changed = dict(document)
        changed["source"] = dict(document["source"], retrieved_at="2026-09-27T01:00:00Z")
        changed["makes"] = [dict(document["makes"][0], name="Source changed name")]
        path.write_text(json.dumps(changed), encoding="utf-8")
        updated_import = import_catalog(db, path)
        assert updated_import["status"] == "imported"
        assert db.scalar(select(CatalogMake).where(CatalogMake.slug == f"test-make-{suffix}")).name == "Operator correction"
        assert db.scalar(select(CatalogImport.id).where(CatalogImport.checksum == updated_import["checksum"])) is not None
        assert import_catalog(db, path)["status"] == "unchanged"
