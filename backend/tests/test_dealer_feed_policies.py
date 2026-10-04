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
    FeedImportRun,
    Listing,
    ListingStatusEvent,
    User,
)
from app.security import hash_password
from app.feed_services import listing_state_digest


PASSWORD = "dealer-feed-policy-test-password-123"


def _add_user(factory, *, label: str) -> tuple[uuid.UUID, str]:
    email = f"{label}-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name=label,
            password_hash=hash_password(PASSWORD),
            role="user",
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
