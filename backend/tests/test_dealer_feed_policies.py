from datetime import datetime, timedelta, timezone
import csv
import io
import json
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.models import (
    Company,
    DealerExternalListingKey,
    DealerFeed,
    DealerTeamMember,
    Favorite,
    FeedImportRun,
    Listing,
    ListingPriceEvent,
    ListingStatusEvent,
    NotificationOutbox,
    User,
)
from app.security import hash_password
from app.feed_services import listing_state_digest


PASSWORD = "dealer-feed-policy-test-password-123"


def _add_user(factory, *, label: str, role: str = "user") -> tuple[uuid.UUID, str]:
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


def _add_company(factory, owner_id: uuid.UUID) -> uuid.UUID:
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
        db.commit()
        db.refresh(company)
        return company.id


def _add_member(factory, company_id: uuid.UUID, user_id: uuid.UUID, role: str, *, granted_by: uuid.UUID) -> None:
    with factory() as db:
        db.add(DealerTeamMember(
            company_id=company_id,
            user_id=user_id,
            role=role,
            status="active",
            revision=1,
            granted_by=granted_by,
        ))
        db.commit()


def _login(integration, email: str) -> tuple[TestClient, str]:
    client = TestClient(integration["client"].app, base_url="http://testserver")
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def _upload_csv(
    client: TestClient,
    *,
    feed_id: uuid.UUID | str,
    csrf: str,
    key: str,
    content: bytes,
    dry_run: bool = False,
    complete_snapshot: bool = False,
):
    return client.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports?dry_run={str(dry_run).lower()}&complete_snapshot={str(complete_snapshot).lower()}",
        files={"file": ("inventory.csv", content, "text/csv")},
        headers={**_csrf(csrf), "Idempotency-Key": key},
    )


def _import_rows(
    client: TestClient,
    *,
    feed_id: uuid.UUID | str,
    feed_format: str,
    csrf: str,
    key: str,
    rows: list[dict],
    api_token: str | None = None,
):
    if feed_format == "csv":
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        return _upload_csv(
            client,
            feed_id=feed_id,
            csrf=csrf,
            key=key,
            content=buffer.getvalue().encode("utf-8"),
        )
    assert api_token is not None
    return client.post(
        f"/api/v1/dealer/feeds/{feed_id}/api-imports",
        json={"items": rows, "dry_run": False},
        headers={"Authorization": f"Bearer {api_token}", "Idempotency-Key": key},
    )


def _make_candidate(factory, *, owner_id: uuid.UUID, company_id: uuid.UUID, feed_id: uuid.UUID):
    external_id = "STOCK-100"
    snapshot_digest = "a" * 64
    missing_since = datetime.now(timezone.utc) - timedelta(hours=2)
    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            company_id=company_id,
            slug=f"feed-policy-{uuid.uuid4().hex}",
            title="Dealer feed candidate",
            description="Test listing for feed policy coverage",
            contact_phone="+375291234567",
            status="active",
            revision=3,
        )
        db.add(listing)
        db.flush()
        link = DealerExternalListingKey(
            feed_id=feed_id,
            company_id=company_id,
            dealer_external_id=external_id,
            listing_id=listing.id,
            last_applied_hash="b" * 64,
            source_fields=["title"],
            last_applied_revision=3,
            last_applied_listing_digest="c" * 64,
            missing_since=missing_since,
            missing_snapshot_digest=snapshot_digest,
            missing_listing_revision=3,
        )
        db.add(link)
        db.commit()
        return listing.id, external_id, snapshot_digest


def test_import_history_is_persisted_company_scoped_and_cursor_paginated(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="history-owner")
    _add_company(factory, owner_id)
    other_owner_id, other_email = _add_user(factory, label="history-other-owner")
    _add_company(factory, other_owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    other_owner, other_csrf = _login(integration, other_email)

    owner_feed = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Persistent stock history", "format": "csv"},
        headers=_csrf(owner_csrf),
    )
    other_feed = other_owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Other company stock", "format": "csv"},
        headers=_csrf(other_csrf),
    )
    assert owner_feed.status_code == 200, owner_feed.text
    assert other_feed.status_code == 200, other_feed.text

    owner_run_ids = set()
    contents = [
        b"dealer_external_id,manual_make,manual_model,title\nHISTORY-1,Toyota,Camry,History one\n",
        b"dealer_external_id,manual_make,manual_model,title,year\nHISTORY-BAD,Toyota,Camry,Invalid row,1700\n",
        b"dealer_external_id,manual_make,manual_model,title\nHISTORY-2,Honda,Civic,History two\n",
    ]
    for index, content in enumerate(contents, start=1):
        imported = _upload_csv(
            owner,
            feed_id=owner_feed.json()["feed"]["id"],
            csrf=owner_csrf,
            key=f"history-import-{index}",
            content=content,
        )
        assert imported.status_code == 200, imported.text
        owner_run_ids.add(imported.json()["run"]["id"])

    other_import = _upload_csv(
        other_owner,
        feed_id=other_feed.json()["feed"]["id"],
        csrf=other_csrf,
        key="other-company-history-import",
        content=b"dealer_external_id,manual_make,manual_model,title\nOTHER-1,Subaru,Forester,Other company\n",
    )
    assert other_import.status_code == 200, other_import.text

    first_page = owner.get("/api/v1/dealer/feed-imports?limit=2")
    assert first_page.status_code == 200, first_page.text
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["next_cursor"] is not None
    assert all(item["feed_name"] == "Persistent stock history" for item in first_page.json()["items"])

    cursor = first_page.json()["next_cursor"]
    second_page = owner.get(f"/api/v1/dealer/feed-imports?limit=2&cursor={cursor}")
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["next_cursor"] is None
    visible_run_ids = {item["run"]["id"] for item in first_page.json()["items"] + second_page.json()["items"]}
    assert visible_run_ids == owner_run_ids
    assert other_import.json()["run"]["id"] not in visible_run_ids

    outsider = owner.get(
        f"/api/v1/dealer/feed-imports?limit=2&cursor={other_import.json()['run']['id']}"
    )
    assert outsider.status_code == 422


def test_feed_list_reports_latest_applied_result_and_success_age_per_company(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="freshness-owner")
    owner_company_id = _add_company(factory, owner_id)
    other_owner_id, other_owner_email = _add_user(factory, label="freshness-other-owner")
    other_company_id = _add_company(factory, other_owner_id)
    def create_feed(client: TestClient, csrf: str, label: str) -> uuid.UUID:
        response = client.post(
            "/api/v1/dealer/feeds",
            json={"name": label, "format": "csv"},
            headers=_csrf(csrf),
        )
        assert response.status_code == 200, response.text
        return uuid.UUID(response.json()["feed"]["id"])

    owner, owner_csrf = _login(integration, owner_email)
    other_owner, other_owner_csrf = _login(integration, other_owner_email)
    feed_id = create_feed(owner, owner_csrf, "Primary inventory")
    empty_feed_id = create_feed(owner, owner_csrf, "New inventory")
    other_feed_id = create_feed(other_owner, other_owner_csrf, "Other company inventory")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    success_at = now - timedelta(hours=3)

    def run(
        *,
        source_feed_id: uuid.UUID,
        company_id: uuid.UUID,
        initiated_by: uuid.UUID,
        key: str,
        source_filename: str,
        status: str,
        created_at: datetime,
        dry_run: bool = False,
        total_rows: int = 1,
        applied_rows: int = 0,
        rejected_rows: int = 0,
    ) -> FeedImportRun:
        return FeedImportRun(
            feed_id=source_feed_id,
            company_id=company_id,
            initiated_by=initiated_by,
            idempotency_key=key,
            payload_digest="a" * 64,
            dry_run=dry_run,
            status=status,
            source_filename=source_filename,
            total_rows=total_rows,
            applied_rows=applied_rows,
            rejected_rows=rejected_rows,
            created_at=created_at,
            completed_at=created_at + timedelta(seconds=4),
        )

    successful_run = run(
        source_feed_id=feed_id,
        company_id=owner_company_id,
        initiated_by=owner_id,
        key="successful-import",
        source_filename="successful.csv",
        status="succeeded",
        created_at=success_at,
        applied_rows=1,
    )
    runs = [
        successful_run,
        run(
            source_feed_id=feed_id,
            company_id=owner_company_id,
            initiated_by=owner_id,
            key="partial-import",
            source_filename="partial.csv",
            status="partial",
            created_at=now - timedelta(hours=1),
            total_rows=2,
            applied_rows=1,
            rejected_rows=1,
        ),
        run(
            source_feed_id=feed_id,
            company_id=owner_company_id,
            initiated_by=owner_id,
            key="failed-import",
            source_filename="failed.csv",
            status="failed",
            created_at=now - timedelta(minutes=20),
            applied_rows=0,
            rejected_rows=1,
        ),
        run(
            source_feed_id=feed_id,
            company_id=owner_company_id,
            initiated_by=owner_id,
            key="preview-import",
            source_filename="preview.csv",
            status="preview",
            created_at=now - timedelta(minutes=5),
            dry_run=True,
        ),
        run(
            source_feed_id=feed_id,
            company_id=owner_company_id,
            initiated_by=owner_id,
            key="missing-confirmation",
            source_filename="missing-confirmation",
            status="succeeded",
            created_at=now - timedelta(minutes=1),
            applied_rows=1,
        ),
        run(
            source_feed_id=other_feed_id,
            company_id=other_company_id,
            initiated_by=other_owner_id,
            key="other-company-import",
            source_filename="other-company.csv",
            status="succeeded",
            created_at=now - timedelta(days=2),
            applied_rows=1,
        ),
    ]
    with factory() as db:
        db.add_all(runs)
        db.commit()

    owner_feeds = owner.get("/api/v1/dealer/feeds")
    assert owner_feeds.status_code == 200, owner_feeds.text
    owner_items = {item["id"]: item for item in owner_feeds.json()["items"]}
    assert set(owner_items) == {str(feed_id), str(empty_feed_id)}
    primary = owner_items[str(feed_id)]
    assert primary["latest_import"]["status"] == "failed"
    assert primary["latest_import"]["source_filename"] == "failed.csv"
    assert primary["latest_import"]["dry_run"] is False
    assert datetime.fromisoformat(primary["last_successful_import_at"].replace("Z", "+00:00")) == success_at + timedelta(seconds=4)
    assert 3 * 60 * 60 - 5 <= primary["last_successful_import_age_seconds"] < 3 * 60 * 60 + 60

    empty = owner_items[str(empty_feed_id)]
    assert empty["latest_import"] is None
    assert empty["last_successful_import_at"] is None
    assert empty["last_successful_import_age_seconds"] is None

    other_feeds = other_owner.get("/api/v1/dealer/feeds")
    assert other_feeds.status_code == 200, other_feeds.text
    assert [item["id"] for item in other_feeds.json()["items"]] == [str(other_feed_id)]
    assert other_feeds.json()["items"][0]["latest_import"]["source_filename"] == "other-company.csv"


def test_feed_samples_schema_and_candidates_are_company_scoped_read_routes(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="policy-owner")
    seller_id, seller_email = _add_user(factory, label="policy-seller")
    viewer_id, viewer_email = _add_user(factory, label="policy-viewer")
    outsider_id, outsider_email = _add_user(factory, label="policy-outsider")
    company_id = _add_company(factory, owner_id)
    _add_member(factory, company_id, seller_id, "seller", granted_by=owner_id)
    _add_member(factory, company_id, viewer_id, "viewer", granted_by=owner_id)
    _add_company(factory, outsider_id)
    owner, owner_csrf = _login(integration, owner_email)
    seller, seller_csrf = _login(integration, seller_email)
    viewer, viewer_csrf = _login(integration, viewer_email)
    outsider, _outsider_csrf = _login(integration, outsider_email)

    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Policy test feed", "format": "csv", "missing_retirement_enabled": True},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = uuid.UUID(created.json()["feed"]["id"])

    seller_import = _upload_csv(
        seller,
        feed_id=feed_id,
        csrf=seller_csrf,
        key="seller-can-import",
        content=b"dealer_external_id,manual_make,manual_model,title\nSELLER-IMPORT-1,Example Auto,Demo Model,Seller import\n",
    )
    assert seller_import.status_code == 200, seller_import.text
    assert seller_import.json()["run"]["status"] == "succeeded"
    viewer_import = _upload_csv(
        viewer,
        feed_id=feed_id,
        csrf=viewer_csrf,
        key="viewer-cannot-import",
        content=b"dealer_external_id,manual_make,manual_model,title\nVIEWER-IMPORT-1,Example Auto,Demo Model,Viewer import\n",
    )
    assert viewer_import.status_code == 403, viewer_import.text

    listing_id, _external_id, _snapshot_digest = _make_candidate(
        factory, owner_id=owner_id, company_id=company_id, feed_id=feed_id,
    )

    assert integration["client"].get("/api/v1/dealer/feeds/schema").status_code == 401
    schema = viewer.get("/api/v1/dealer/feeds/schema")
    assert schema.status_code == 200, schema.text
    assert schema.json()["stable_key"] == "dealer_external_id"

    anonymous_sample = integration["client"].get("/api/v1/dealer/feeds/samples/api")
    assert anonymous_sample.status_code == 401
    sample = viewer.get("/api/v1/dealer/feeds/samples/api")
    assert sample.status_code == 200, sample.text
    assert sample.headers["cache-control"] == "private, no-store"
    sample_item = json.loads(sample.content)["items"][0]
    assert sample_item["dealer_external_id"] == "DEMO-CAR-001"
    assert sample_item["description"] == "Synthetic sample only"

    candidates = viewer.get(f"/api/v1/dealer/feeds/{feed_id}/missing-candidates")
    assert candidates.status_code == 200, candidates.text
    assert [item["listing_id"] for item in candidates.json()["items"]] == [str(listing_id)]
    assert outsider.get("/api/v1/dealer/feeds/schema").status_code == 200
    assert outsider.get(f"/api/v1/dealer/feeds/{feed_id}/missing-candidates").status_code == 404
    assert integration["client"].get(f"/api/v1/dealer/feeds/{feed_id}/missing-candidates").status_code == 401


def test_missing_candidate_pause_requires_manager_and_replays_idempotently(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="pause-owner")
    admin_id, admin_email = _add_user(factory, label="pause-admin")
    seller_id, seller_email = _add_user(factory, label="pause-seller")
    company_id = _add_company(factory, owner_id)
    _add_member(factory, company_id, admin_id, "admin", granted_by=owner_id)
    _add_member(factory, company_id, seller_id, "seller", granted_by=owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    admin, admin_csrf = _login(integration, admin_email)
    seller, seller_csrf = _login(integration, seller_email)

    created = owner.post(
        "/api/v1/dealer/feeds",
        json={
            "name": "Retirement test feed",
            "format": "csv",
            "missing_retirement_enabled": True,
            "missing_retirement_delay_hours": 1,
        },
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = uuid.UUID(created.json()["feed"]["id"])
    listing_id, external_id, snapshot_digest = _make_candidate(
        factory, owner_id=owner_id, company_id=company_id, feed_id=feed_id,
    )
    body = {
        "items": [{
            "dealer_external_id": external_id,
            "expected_listing_revision": 3,
            "snapshot_digest": snapshot_digest,
        }],
    }
    pause_url = f"/api/v1/dealer/feeds/{feed_id}/missing-candidates/pause"

    seller_denied = seller.post(pause_url, json=body, headers=_csrf(seller_csrf))
    assert seller_denied.status_code == 403, seller_denied.text
    assert owner.post(pause_url, json=body, headers=_csrf(owner_csrf)).status_code == 422

    confirmation_headers = {**_csrf(admin_csrf), "Idempotency-Key": "pause-candidate-once"}
    confirmed = admin.post(pause_url, json=body, headers=confirmation_headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["paused_external_ids"] == [external_id]
    replay = admin.post(pause_url, json=body, headers=confirmation_headers)
    assert replay.status_code == 200, replay.text
    assert replay.json() == confirmed.json()

    with factory() as db:
        listing = db.get(Listing, listing_id)
        assert (listing.status, listing.revision) == ("paused", 4)
        events = db.scalars(select(ListingStatusEvent).where(ListingStatusEvent.listing_id == listing_id)).all()
        assert [(event.from_status, event.to_status, event.reason) for event in events] == [
            ("active", "paused", "feed_missing_confirmed"),
        ]
        runs = db.scalars(select(FeedImportRun).where(
            FeedImportRun.feed_id == feed_id,
            FeedImportRun.idempotency_key == "pause-candidate-once",
        )).all()
        assert len(runs) == 1


def test_missing_candidate_confirmation_rejects_stale_revision_without_mutation(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="stale-owner")
    company_id = _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={
            "name": "Stale candidate feed",
            "format": "csv",
            "missing_retirement_enabled": True,
            "missing_retirement_delay_hours": 1,
        },
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = uuid.UUID(created.json()["feed"]["id"])
    listing_id, external_id, snapshot_digest = _make_candidate(
        factory, owner_id=owner_id, company_id=company_id, feed_id=feed_id,
    )
    with factory() as db:
        db.get(Listing, listing_id).revision = 4
        db.commit()

    response = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/missing-candidates/pause",
        json={"items": [{
            "dealer_external_id": external_id,
            "expected_listing_revision": 3,
            "snapshot_digest": snapshot_digest,
        }]},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "pause-stale-candidate"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "missing_candidate_stale"
    with factory() as db:
        assert db.get(Listing, listing_id).status == "active"
        assert db.scalar(select(FeedImportRun).where(
            FeedImportRun.feed_id == feed_id,
            FeedImportRun.idempotency_key == "pause-stale-candidate",
        )) is None


@pytest.mark.parametrize("protected_status", ["paused", "sold", "blocked"])
def test_feed_updates_do_not_reactivate_protected_listings(integration, protected_status: str):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label=f"protected-{protected_status}")
    company_id = _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": f"{protected_status} feed", "format": "csv", "manual_conflict_policy": "feed_wins"},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = uuid.UUID(created.json()["feed"]["id"])

    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            company_id=company_id,
            slug=f"protected-{uuid.uuid4().hex}",
            title="Original protected listing",
            description="Original description",
            contact_phone="+375291234567",
            status=protected_status,
            revision=7,
        )
        db.add(listing)
        db.flush()
        db.add(DealerExternalListingKey(
            feed_id=feed_id,
            company_id=company_id,
            dealer_external_id="STOCK-100",
            listing_id=listing.id,
            last_applied_hash="0" * 64,
            source_fields=["title"],
            last_applied_revision=6,
            last_applied_listing_digest="1" * 64,
        ))
        db.commit()
        listing_id = listing.id

    response = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports?dry_run=false",
        files={
            "file": (
                "inventory.csv",
                b"dealer_external_id,manual_make,manual_model,title\nSTOCK-100,Example Auto,Demo Model,Changed title\n",
                "text/csv",
            ),
        },
        headers={**_csrf(owner_csrf), "Idempotency-Key": f"protected-{protected_status}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "failed"
    run_id = response.json()["run"]["id"]
    rows = owner.get(f"/api/v1/dealer/feed-imports/{run_id}/rows")
    assert rows.status_code == 200, rows.text
    assert rows.json()["items"][0]["error_code"] == "listing_not_editable"

    with factory() as db:
        listing = db.get(Listing, listing_id)
        assert (listing.status, listing.revision, listing.title) == (
            protected_status,
            7,
            "Original protected listing",
        )


@pytest.mark.parametrize("feed_format", ["csv", "api"])
def test_manual_conflict_preserves_owner_edit_until_feed_wins_is_selected(integration, feed_format: str):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="conflict-owner")
    _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Conflict feed", "format": feed_format},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]
    api_token = created.json().get("api_token")

    initial_record = {
        "dealer_external_id": "STOCK-200",
        "manual_make": "Example Auto",
        "manual_model": "Demo Model",
        "title": "Initial feed title",
        "year": 2020,
        "mileage_km": 45000,
        "price_amount": "14500.00",
        "currency": "BYN",
    }
    initial = _import_rows(
        owner,
        feed_id=feed_id,
        feed_format=feed_format,
        csrf=owner_csrf,
        key="conflict-initial",
        rows=[initial_record],
        api_token=api_token,
    )
    assert initial.status_code == 200, initial.text
    initial_run_id = initial.json()["run"]["id"]
    initial_rows = owner.get(f"/api/v1/dealer/feed-imports/{initial_run_id}/rows")
    listing_id = uuid.UUID(initial_rows.json()["items"][0]["listing_id"])
    with factory() as db:
        revision = db.get(Listing, listing_id).revision

    manual_edit = owner.patch(
        f"/api/v1/listings/{listing_id}",
        json={"expected_revision": revision, "title": "Owner edited title"},
        headers=_csrf(owner_csrf),
    )
    assert manual_edit.status_code == 200, manual_edit.text
    assert manual_edit.json()["listing"]["title"] == "Owner edited title"

    updated_record = {**initial_record, "title": "Vendor update title"}
    review = _import_rows(
        owner, feed_id=feed_id, feed_format=feed_format, csrf=owner_csrf,
        key="conflict-review", rows=[updated_record], api_token=api_token,
    )
    assert review.status_code == 200, review.text
    assert review.json()["run"]["status"] == "failed"
    review_rows = owner.get(f"/api/v1/dealer/feed-imports/{review.json()['run']['id']}/rows")
    assert review_rows.json()["items"][0]["error_code"] == "manual_edit_conflict"
    with factory() as db:
        listing = db.get(Listing, listing_id)
        assert listing.title == "Owner edited title"
        assert listing.revision == manual_edit.json()["listing"]["revision"]

    policy = owner.patch(
        f"/api/v1/dealer/feeds/{feed_id}",
        json={"manual_conflict_policy": "feed_wins"},
        headers=_csrf(owner_csrf),
    )
    assert policy.status_code == 200, policy.text
    assert policy.json()["feed"]["manual_conflict_policy"] == "feed_wins"
    feed_wins = _import_rows(
        owner, feed_id=feed_id, feed_format=feed_format, csrf=owner_csrf,
        key="conflict-feed-wins", rows=[updated_record], api_token=api_token,
    )
    assert feed_wins.status_code == 200, feed_wins.text
    assert feed_wins.json()["run"]["status"] == "succeeded"
    applied_rows = owner.get(f"/api/v1/dealer/feed-imports/{feed_wins.json()['run']['id']}/rows")
    assert applied_rows.json()["items"][0]["action"] == "overrode_manual"
    with factory() as db:
        assert db.get(Listing, listing_id).title == "Vendor update title"


def test_feed_update_records_legacy_active_price_baseline_before_demotion(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="legacy-feed-baseline-owner")
    _moderator_id, moderator_email = _add_user(factory, label="legacy-feed-baseline-moderator", role="moderator")
    buyer_id, _ = _add_user(factory, label="legacy-feed-baseline-buyer")
    company_id = _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Legacy baseline feed", "format": "csv", "manual_conflict_policy": "feed_wins"},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]

    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            company_id=company_id,
            slug=f"legacy-feed-price-{uuid.uuid4().hex}",
            status="active",
            revision=3,
            title="Legacy dealer listing",
            description="A legacy active listing without recorded price history.",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
            make_name_snapshot="Example Auto",
            model_name_snapshot="Demo Model",
            year=2020,
            mileage_km=45000,
            price_amount="15000.00",
            currency="USD",
        )
        db.add(listing)
        db.flush()
        db.add(DealerExternalListingKey(
            feed_id=uuid.UUID(feed_id),
            company_id=company_id,
            dealer_external_id="LEGACY-PRICE-1",
            listing_id=listing.id,
            last_applied_hash="b" * 64,
            source_fields=["title", "price_amount", "currency"],
            last_applied_revision=listing.revision,
            last_applied_listing_digest=listing_state_digest(db, listing),
        ))
        db.add(Favorite(user_id=buyer_id, listing_id=listing.id, price_drop_notifications_enabled=True))
        listing_id = listing.id
        db.commit()

    content = (
        b"dealer_external_id,manual_make,manual_model,title,year,mileage_km,price_amount,currency\n"
        b"LEGACY-PRICE-1,Example Auto,Demo Model,Legacy feed update,2020,45000,13000.00,USD\n"
    )
    imported = _upload_csv(owner, feed_id=feed_id, csrf=owner_csrf, key="legacy-price-feed-update", content=content)
    assert imported.status_code == 200, imported.text
    assert imported.json()["run"]["status"] == "succeeded"

    with factory() as db:
        listing = db.get(Listing, listing_id)
        assert listing.status == "draft"
        assert str(listing.price_amount) == "13000.00"
        events = db.scalars(
            select(ListingPriceEvent)
            .where(ListingPriceEvent.listing_id == listing_id)
            .order_by(ListingPriceEvent.revision)
        ).all()
        assert [(event.event_type, str(event.price_amount), event.currency, event.previous_price_amount) for event in events] == [
            ("baseline", "15000.00", "USD", None)
        ]
        assert db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.listing_id == listing_id)) is None

        listing.status = "pending_review"
        listing.submitted_revision = listing.revision
        review_revision = listing.revision
        db.commit()

    moderator, moderator_csrf = _login(integration, moderator_email)
    approved = moderator.post(
        f"/api/v1/moderation/listings/{listing_id}/approve",
        json={"expected_revision": review_revision},
        headers=_csrf(moderator_csrf),
    )
    assert approved.status_code == 200, approved.text
    with factory() as db:
        events = db.scalars(
            select(ListingPriceEvent)
            .where(ListingPriceEvent.listing_id == listing_id)
            .order_by(ListingPriceEvent.revision)
        ).all()
        assert [event.event_type for event in events] == ["baseline", "changed"]
        assert str(events[1].previous_price_amount) == "15000.00"
        assert str(events[1].price_amount) == "13000.00"
        outboxes = db.scalars(select(NotificationOutbox).where(NotificationOutbox.listing_id == listing_id)).all()
        assert len(outboxes) == 1
        assert outboxes[0].user_id == buyer_id
        assert outboxes[0].price_event_id == events[1].id


def test_complete_snapshot_is_all_or_nothing_tracks_delay_and_clears_reappearing_candidates(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="snapshot-owner")
    _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={
            "name": "Complete snapshot feed",
            "format": "csv",
            "missing_retirement_enabled": True,
            "missing_retirement_delay_hours": 1,
        },
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]
    both = b"dealer_external_id,manual_make,manual_model,title,year,mileage_km,price_amount,currency\nSTOCK-A,Example Auto,Model A,Vehicle A,2020,45000,14500.00,BYN\nSTOCK-B,Example Auto,Model B,Vehicle B,2021,30000,18000.00,BYN\n"

    first_snapshot = _upload_csv(owner, feed_id=feed_id, csrf=owner_csrf, key="snapshot-both", content=both, complete_snapshot=True)
    assert first_snapshot.status_code == 200, first_snapshot.text
    assert first_snapshot.json()["run"]["status"] == "succeeded"
    first_rows = owner.get(f"/api/v1/dealer/feed-imports/{first_snapshot.json()['run']['id']}/rows")
    listing_b_id = uuid.UUID(next(row["listing_id"] for row in first_rows.json()["items"] if row["dealer_external_id"] == "STOCK-B"))

    # Seed the publication lifecycle state that a moderator-approved listing has in production.
    with factory() as db:
        listing_b = db.get(Listing, listing_b_id)
        listing_b.status = "active"
        listing_b.revision += 1
        link_b = db.scalar(select(DealerExternalListingKey).where(
            DealerExternalListingKey.feed_id == uuid.UUID(feed_id),
            DealerExternalListingKey.dealer_external_id == "STOCK-B",
        ))
        link_b.last_applied_revision = listing_b.revision
        link_b.last_applied_listing_digest = listing_state_digest(db, listing_b)
        db.commit()

    only_a = b"dealer_external_id,manual_make,manual_model,title,year,mileage_km,price_amount,currency\nSTOCK-A,Example Auto,Model A,Vehicle A,2020,45000,14500.00,BYN\n"
    missing_snapshot = _upload_csv(owner, feed_id=feed_id, csrf=owner_csrf, key="snapshot-a-only", content=only_a, complete_snapshot=True)
    assert missing_snapshot.status_code == 200, missing_snapshot.text
    assert missing_snapshot.json()["run"]["status"] == "succeeded"
    candidates = owner.get(f"/api/v1/dealer/feeds/{feed_id}/missing-candidates")
    assert candidates.status_code == 200, candidates.text
    candidate = next(item for item in candidates.json()["items"] if item["dealer_external_id"] == "STOCK-B")
    assert candidate["reason"] == "confirmation_delay"
    assert candidate["eligible"] is False
    assert candidate["expected_listing_revision"] == candidate["listing_revision"]

    old_since = datetime.now(timezone.utc) - timedelta(hours=2)
    with factory() as db:
        link_b = db.scalar(select(DealerExternalListingKey).where(
            DealerExternalListingKey.feed_id == uuid.UUID(feed_id),
            DealerExternalListingKey.dealer_external_id == "STOCK-B",
        ))
        link_b.missing_since = old_since
        db.commit()

    invalid_snapshot = b"dealer_external_id,manual_make,manual_model,title,year,mileage_km,price_amount,currency\nSTOCK-A,Example Auto,Model A,Vehicle A,2020,45000,14500.00,BYN\nSTOCK-INVALID,Example Auto,Model X,Bad year,1700,0,1000.00,BYN\n"
    rejected = _upload_csv(owner, feed_id=feed_id, csrf=owner_csrf, key="snapshot-rejected", content=invalid_snapshot, complete_snapshot=True)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["run"]["status"] == "failed"
    after_rejection = owner.get(f"/api/v1/dealer/feeds/{feed_id}/missing-candidates")
    unchanged = next(item for item in after_rejection.json()["items"] if item["dealer_external_id"] == "STOCK-B")
    assert unchanged["missing_since"] == old_since.isoformat().replace("+00:00", "Z") or datetime.fromisoformat(unchanged["missing_since"].replace("Z", "+00:00")) == old_since
    assert unchanged["snapshot_digest"] == candidate["snapshot_digest"]
    assert unchanged["eligible"] is True

    confirmation = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/missing-candidates/pause",
        json={"items": [{
            "dealer_external_id": "STOCK-B",
            "expected_listing_revision": unchanged["expected_listing_revision"],
            "snapshot_digest": unchanged["snapshot_digest"],
        }]},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "pause-real-missing-row"},
    )
    assert confirmation.status_code == 200, confirmation.text
    with factory() as db:
        assert db.get(Listing, listing_b_id).status == "paused"

    reappeared = _upload_csv(owner, feed_id=feed_id, csrf=owner_csrf, key="snapshot-reappeared", content=both, complete_snapshot=True)
    assert reappeared.status_code == 200, reappeared.text
    # A valid reappearance clears the candidate, but it does not resume its paused listing.
    assert reappeared.json()["run"]["status"] == "succeeded"
    remaining = owner.get(f"/api/v1/dealer/feeds/{feed_id}/missing-candidates")
    assert all(item["dealer_external_id"] != "STOCK-B" for item in remaining.json()["items"])
    with factory() as db:
        assert db.get(Listing, listing_b_id).status == "paused"
