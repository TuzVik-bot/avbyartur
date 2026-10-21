import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Favorite, Listing, ListingStatusEvent, Report, User, WorkerJob
from app.security import hash_password
from app.services import enqueue_job
from app.worker import _claim_one, _run_job

PASSWORD = "listing-lifecycle-test-password-123"


def _add_user(factory, *, role: str = "user") -> User:
    email = f"{role}-{uuid.uuid4().hex[:12]}@example.com"
    user = User(
        email=email,
        display_name=email.split("@")[0],
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


def _add_listing(factory, owner_id, *, status: str = "active", revision: int = 1) -> Listing:
    listing = Listing(
        owner_id=owner_id,
        slug=f"listing-lifecycle-{uuid.uuid4().hex}",
        status=status,
        revision=revision,
        title="Lifecycle acceptance listing",
        description="Listing created for lifecycle integration coverage.",
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        make_name_snapshot="Mazda",
        model_name_snapshot="3",
        year=2018,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _client(integration) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver")


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def test_favorites_are_user_scoped_idempotent_and_hide_nonpublic_listings(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    visitor = _add_user(factory)
    active = _add_listing(factory, owner.id)
    paused = _add_listing(factory, owner.id, status="paused")
    visitor_client = _client(integration)
    visitor_csrf = _login(visitor_client, visitor.email)
    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner.email)

    active_path = f"/api/v1/me/favorites/{active.id}"
    assert visitor_client.put(active_path).status_code == 403
    added = visitor_client.put(active_path, headers=_csrf(visitor_csrf))
    assert added.status_code == 200, added.text
    assert visitor_client.put(active_path, headers=_csrf(visitor_csrf)).status_code == 200

    favorites = visitor_client.get("/api/v1/me/favorites")
    assert favorites.status_code == 200, favorites.text
    assert [item["id"] for item in favorites.json()["items"]] == [str(active.id)]
    favorite = favorites.json()["items"][0]
    assert "modification" not in favorite
    assert "make_id" not in favorite["make"]
    assert owner_client.get("/api/v1/me/favorites").json()["items"] == []
    assert owner_client.delete(active_path, headers=_csrf(owner_csrf)).status_code == 200
    assert [item["id"] for item in visitor_client.get("/api/v1/me/favorites").json()["items"]] == [str(active.id)]

    paused_path = f"/api/v1/me/favorites/{paused.id}"
    hidden = visitor_client.put(paused_path, headers=_csrf(visitor_csrf))
    assert hidden.status_code == 404, hidden.text

    assert visitor_client.delete(active_path).status_code == 403
    removed = visitor_client.delete(active_path, headers=_csrf(visitor_csrf))
    assert removed.status_code == 200, removed.text
    assert visitor_client.get("/api/v1/me/favorites").json()["items"] == []
    with factory() as db:
        assert db.scalar(select(Favorite).where(Favorite.user_id == visitor.id, Favorite.listing_id == active.id)) is None


def test_favorite_keeps_sold_listing_visible_without_contact_until_retention(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    buyer = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    with factory() as db:
        db.add(ListingStatusEvent(
            listing_id=listing.id,
            actor_id=owner.id,
            from_status="pending_review",
            to_status="active",
            revision=listing.revision,
        ))
        db.commit()
    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner.email)
    buyer_client = _client(integration)
    buyer_csrf = _login(buyer_client, buyer.email)

    favorite_path = f"/api/v1/me/favorites/{listing.id}"
    assert buyer_client.put(favorite_path, headers=_csrf(buyer_csrf)).status_code == 200

    sold = owner_client.post(
        f"/api/v1/listings/{listing.id}/sold",
        json={"expected_revision": listing.revision},
        headers=_csrf(owner_csrf),
    )
    assert sold.status_code == 200, sold.text
    assert sold.json()["listing"]["status"] == "sold"

    detail = buyer_client.get(f"/api/v1/listings/{listing.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["listing"]["status"] == "sold"
    assert "contact_phone" not in detail.json()["listing"]
    assert buyer_client.post(
        f"/api/v1/listings/{listing.id}/phone-reveal",
        headers=_csrf(buyer_csrf),
    ).status_code == 404

    favorites = buyer_client.get("/api/v1/me/favorites")
    assert favorites.status_code == 200, favorites.text
    assert len(favorites.json()["items"]) == 1
    favorite = favorites.json()["items"][0]
    assert favorite["id"] == str(listing.id)
    assert favorite["status"] == "sold"
    assert "contact_phone" not in favorite

    with factory() as db:
        persisted = db.get(Listing, listing.id)
        assert persisted is not None
        persisted.sold_at = datetime.now(UTC) - timedelta(days=31)
        database_now = db.scalar(select(func.now()))
        assert database_now is not None
        retention_job = enqueue_job(
            db,
            "cleanup.retention",
            f"cleanup.retention:test:{uuid.uuid4().hex}",
            {},
            run_after=database_now - timedelta(seconds=1),
            max_attempts=4,
        )
        db.commit()

    worker_id = f"lifecycle-retention-test-{uuid.uuid4().hex[:8]}"
    claimed_job_id = _claim_one(worker_id)
    assert claimed_job_id == retention_job.id
    _run_job(claimed_job_id, worker_id)

    with factory() as db:
        completed_job = db.get(WorkerJob, retention_job.id)
        assert completed_job is not None
        assert completed_job.kind == "cleanup.retention"
        assert completed_job.status == "succeeded"
        assert completed_job.attempts == 1
        assert completed_job.locked_by is None
        assert completed_job.lease_until is None
        assert completed_job.last_error is None

        archived = db.get(Listing, listing.id)
        assert archived is not None
        assert archived.status == "archived"
        archive_event = db.scalar(
            select(ListingStatusEvent).where(
                ListingStatusEvent.listing_id == listing.id,
                ListingStatusEvent.to_status == "archived",
            )
        )
        assert archive_event is not None
        assert archive_event.reason == "sold_retention_expired"

    assert buyer_client.get(f"/api/v1/listings/{listing.id}").status_code == 410
    assert buyer_client.get("/api/v1/me/favorites").json()["items"] == []


def test_seller_listing_reads_restore_contact_phone_without_exposing_it_publicly(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    owner_client = _client(integration)
    _login(owner_client, owner.email)
    public_client = _client(integration)

    seller_listings = owner_client.get("/api/v1/me/listings")
    assert seller_listings.status_code == 200, seller_listings.text
    seller_listing = next(item for item in seller_listings.json()["items"] if item["id"] == str(listing.id))
    assert seller_listing["contact_phone"] == listing.contact_phone

    owner_detail = owner_client.get(f"/api/v1/listings/{listing.id}")
    assert owner_detail.status_code == 200, owner_detail.text
    assert owner_detail.json()["listing"]["contact_phone"] == listing.contact_phone

    public_listing = public_client.get(f"/api/v1/listings/{listing.id}")
    assert public_listing.status_code == 200, public_listing.text
    assert "contact_phone" not in public_listing.json()["listing"]
    assert "phone" not in public_listing.json()["listing"]


def test_listing_reports_require_csrf_and_moderator_can_resolve_them(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    reporter = _add_user(factory)
    moderator = _add_user(factory, role="moderator")
    listing = _add_listing(factory, owner.id)
    paused = _add_listing(factory, owner.id, status="paused")
    reporter_client = _client(integration)
    reporter_csrf = _login(reporter_client, reporter.email)
    moderator_client = _client(integration)
    moderator_csrf = _login(moderator_client, moderator.email)
    report_path = f"/api/v1/listings/{listing.id}/reports"
    payload = {"category": "incorrect_info", "comment": "The mileage does not match the photos."}

    assert reporter_client.post(report_path, json=payload).status_code == 403
    submitted = reporter_client.post(report_path, json=payload, headers=_csrf(reporter_csrf))
    assert submitted.status_code == 200, submitted.text
    report = submitted.json()
    assert report["status"] == "open"
    hidden_report = reporter_client.post(
        f"/api/v1/listings/{paused.id}/reports", json=payload, headers=_csrf(reporter_csrf)
    )
    assert hidden_report.status_code == 404, hidden_report.text

    queue = moderator_client.get("/api/v1/moderation/reports")
    assert queue.status_code == 200, queue.text
    assert any(item["id"] == report["id"] and item["listing_id"] == str(listing.id) for item in queue.json()["items"])

    resolve_path = f"/api/v1/moderation/reports/{report['id']}/resolve"
    resolution = {"expected_revision": report["revision"], "resolution": "Checked against the seller's submitted documents."}
    assert moderator_client.post(resolve_path, json=resolution).status_code == 403
    resolved = moderator_client.post(resolve_path, json=resolution, headers=_csrf(moderator_csrf))
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["report"] == {
        "id": report["id"],
        "status": "resolved",
        "revision": report["revision"] + 1,
        "resolution": resolution["resolution"],
    }
    with factory() as db:
        persisted = db.get(Report, uuid.UUID(report["id"]))
        assert persisted is not None
        assert persisted.reporter_id == reporter.id
        assert persisted.listing_id == listing.id
        assert persisted.status == "resolved"


def test_seller_listing_lifecycle_checks_owner_csrf_revision_and_public_visibility(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    other = _add_user(factory)
    listing = _add_listing(factory, owner.id)
    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner.email)
    other_client = _client(integration)
    other_csrf = _login(other_client, other.email)
    public_client = _client(integration)

    listing_path = f"/api/v1/listings/{listing.id}"
    pause_path = f"{listing_path}/pause"
    resume_path = f"{listing_path}/resume"
    sold_path = f"{listing_path}/sold"
    assert public_client.get(listing_path).json()["listing"]["status"] == "active"
    assert str(listing.id) in [item["id"] for item in public_client.get("/api/v1/listings").json()["items"]]

    assert other_client.post(pause_path, json={"expected_revision": 1}, headers=_csrf(other_csrf)).status_code == 404
    assert owner_client.post(pause_path, json={"expected_revision": 1}).status_code == 403
    stale_pause = owner_client.post(pause_path, json={"expected_revision": 2}, headers=_csrf(owner_csrf))
    assert stale_pause.status_code == 409, stale_pause.text

    paused = owner_client.post(pause_path, json={"expected_revision": 1}, headers=_csrf(owner_csrf))
    assert paused.status_code == 200, paused.text
    assert paused.json()["listing"]["status"] == "paused"
    assert paused.json()["listing"]["revision"] == 2
    assert owner_client.get(listing_path).json()["listing"]["status"] == "paused"
    assert public_client.get(listing_path).status_code == 404
    assert str(listing.id) not in [item["id"] for item in public_client.get("/api/v1/listings").json()["items"]]

    stale_resume = owner_client.post(resume_path, json={"expected_revision": 1}, headers=_csrf(owner_csrf))
    assert stale_resume.status_code == 409, stale_resume.text
    resumed = owner_client.post(resume_path, json={"expected_revision": 2}, headers=_csrf(owner_csrf))
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["listing"]["status"] == "active"
    assert resumed.json()["listing"]["revision"] == 3
    assert public_client.get(listing_path).json()["listing"]["status"] == "active"
    assert str(listing.id) in [item["id"] for item in public_client.get("/api/v1/listings").json()["items"]]

    stale_sold = owner_client.post(sold_path, json={"expected_revision": 2}, headers=_csrf(owner_csrf))
    assert stale_sold.status_code == 409, stale_sold.text
    sold = owner_client.post(sold_path, json={"expected_revision": 3}, headers=_csrf(owner_csrf))
    assert sold.status_code == 200, sold.text
    assert sold.json()["listing"]["status"] == "sold"
    assert sold.json()["listing"]["revision"] == 4
    assert public_client.get(listing_path).json()["listing"]["status"] == "sold"
    assert str(listing.id) not in [item["id"] for item in public_client.get("/api/v1/listings").json()["items"]]
    assert owner_client.post(sold_path, json={"expected_revision": 4}, headers=_csrf(owner_csrf)).status_code == 409

    with factory() as db:
        persisted = db.get(Listing, listing.id)
        assert persisted is not None
        assert persisted.status == "sold"
        assert persisted.revision == 4
        assert persisted.sold_at is not None
        events = db.scalars(
            select(ListingStatusEvent)
            .where(ListingStatusEvent.listing_id == listing.id)
            .order_by(ListingStatusEvent.revision)
        ).all()
        assert [(event.from_status, event.to_status, event.revision) for event in events] == [
            ("active", "paused", 2),
            ("paused", "active", 3),
            ("active", "sold", 4),
        ]
