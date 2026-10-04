from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import io
import threading
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select

from app.feed_services import listing_state_digest
from app.models import (
    Company,
    DealerExternalListingKey,
    DealerFeed,
    FeedImportRun,
    Listing,
    User,
)
from app.security import hash_password


PASSWORD = "feed-review-regression-password-123"
CSV_FIELDS = [
    "dealer_external_id",
    "manual_make",
    "manual_model",
    "title",
    "year",
    "mileage_km",
    "price_amount",
    "currency",
]


def _add_user(factory, label: str) -> tuple[uuid.UUID, str]:
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
            name=f"Regression Dealer {suffix}",
            slug=f"regression-dealer-{suffix}",
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


def _login(integration, email: str) -> tuple[TestClient, str]:
    client = TestClient(integration["client"].app, base_url="http://testserver")
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _csv(rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(CSV_FIELDS)
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _row(external_id: str, *, year: str = "2021", title: str | None = None) -> list[str]:
    return [external_id, "Toyota", "Camry", title or f"Vehicle {external_id}", year, "30000", "18000.00", "BYN"]


def _upload(client: TestClient, feed_id: str, csrf: str, *, key: str, rows: list[list[str]], dry_run: bool = False, complete_snapshot: bool = False):
    return client.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports?dry_run={str(dry_run).lower()}&complete_snapshot={str(complete_snapshot).lower()}",
        files={"file": ("inventory.csv", _csv(rows), "text/csv")},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
    )


def _create_csv_candidate(integration, external_id: str = "REAPPEARING-1"):
    factory = integration["SessionLocal"]
    owner_id, email = _add_user(factory, "feed-review-owner")
    company_id = _add_company(factory, owner_id)
    owner, csrf = _login(integration, email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Candidate regression feed", "format": "csv", "missing_retirement_enabled": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]

    anchor_id = "PRESENT-ANCHOR-1"
    imported = _upload(owner, feed_id, csrf, key="seed-listing", rows=[_row(external_id), _row(anchor_id)])
    assert imported.status_code == 200, imported.text
    assert imported.json()["run"]["status"] == "succeeded"
    rows = owner.get(f"/api/v1/dealer/feed-imports/{imported.json()['run']['id']}/rows").json()["items"]
    listing_id = uuid.UUID(next(row["listing_id"] for row in rows if row["dealer_external_id"] == external_id))
    with factory() as db:
        for row in rows:
            listing = db.get(Listing, uuid.UUID(row["listing_id"]))
            listing.status = "active"
            listing.revision += 1
            link = db.scalar(select(DealerExternalListingKey).where(
                DealerExternalListingKey.feed_id == uuid.UUID(feed_id),
                DealerExternalListingKey.dealer_external_id == row["dealer_external_id"],
            ))
            link.last_applied_revision = listing.revision
            link.last_applied_listing_digest = listing_state_digest(db, listing)
        db.commit()

    omitted = _upload(owner, feed_id, csrf, key="mark-missing", rows=[_row(anchor_id)], complete_snapshot=True)
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["run"]["status"] == "succeeded"
    with factory() as db:
        link = db.scalar(select(DealerExternalListingKey).where(
            DealerExternalListingKey.feed_id == uuid.UUID(feed_id),
            DealerExternalListingKey.dealer_external_id == external_id,
        ))
        assert link.missing_since is not None
        assert link.missing_snapshot_digest is not None
        candidate_state = (link.missing_since, link.missing_snapshot_digest, link.missing_listing_revision)
    return factory, owner, csrf, owner_id, company_id, feed_id, external_id, listing_id, candidate_state


def test_partial_csv_import_clears_only_successfully_reappearing_candidate(integration):
    factory, owner, csrf, _owner_id, _company_id, feed_id, external_id, _listing_id, _state = _create_csv_candidate(integration)

    partial = _upload(
        owner,
        feed_id,
        csrf,
        key="partial-reappearance",
        rows=[_row(external_id), _row("NEW-VALID-1"), _row("INVALID-YEAR-1", year="1700")],
    )

    assert partial.status_code == 200, partial.text
    assert partial.json()["run"]["status"] == "partial"
    assert partial.json()["run"]["applied_rows"] == 1
    assert partial.json()["run"]["rejected_rows"] == 1
    with factory() as db:
        link = db.scalar(select(DealerExternalListingKey).where(
            DealerExternalListingKey.feed_id == uuid.UUID(feed_id),
            DealerExternalListingKey.dealer_external_id == external_id,
        ))
        assert link.missing_since is None
        assert link.missing_snapshot_digest is None
        assert link.missing_listing_revision is None


def test_malformed_rows_invalid_complete_snapshot_and_dry_run_do_not_clear_candidates(integration):
    factory, owner, csrf, _owner_id, _company_id, feed_id, external_id, _listing_id, initial_state = _create_csv_candidate(integration)

    rejected_snapshot = _upload(
        owner,
        feed_id,
        csrf,
        key="invalid-complete-reappearance",
        rows=[_row(external_id), _row("INVALID-COMPLETE-1", year="1700")],
        complete_snapshot=True,
    )
    assert rejected_snapshot.status_code == 200, rejected_snapshot.text
    assert rejected_snapshot.json()["run"]["status"] == "failed"

    preview = _upload(
        owner,
        feed_id,
        csrf,
        key="dry-run-reappearance",
        rows=[_row(external_id)],
        dry_run=True,
        complete_snapshot=True,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["run"]["status"] == "preview"

    malformed = _upload(
        owner,
        feed_id,
        csrf,
        key="malformed-reappearance",
        rows=[[*_row(external_id), "overflow-value"], _row("NEW-VALID-2")],
    )
    assert malformed.status_code == 200, malformed.text
    assert malformed.json()["run"]["status"] == "partial"
    assert malformed.json()["run"]["applied_rows"] == 1
    assert malformed.json()["run"]["rejected_rows"] == 1

    with factory() as db:
        link = db.scalar(select(DealerExternalListingKey).where(
            DealerExternalListingKey.feed_id == uuid.UUID(feed_id),
            DealerExternalListingKey.dealer_external_id == external_id,
        ))
        assert (link.missing_since, link.missing_snapshot_digest, link.missing_listing_revision) == initial_state


def test_api_import_waits_for_owner_before_locking_feed_and_rechecks_feed_state(integration):
    factory = integration["SessionLocal"]
    owner_id, email = _add_user(factory, "api-lock-owner")
    _add_company(factory, owner_id)
    owner, csrf = _login(integration, email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "API lock-order feed", "format": "api"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text
    feed_id = uuid.UUID(created.json()["feed"]["id"])
    token = created.json()["api_token"]

    owner_blocker = factory()
    owner_blocker.execute(select(User).where(User.id == owner_id).with_for_update())
    api_owner_lock_attempted = threading.Event()
    api_feed_lock_started = threading.Event()
    main_thread_id = threading.get_ident()

    def observe_api_locks(_connection, _cursor, statement, _parameters, _context, _executemany):
        if threading.get_ident() == main_thread_id:
            return
        if not _connection.info.get("feed_review_lock_timeout"):
            _cursor.execute("SET LOCAL lock_timeout = '3s'")
            _connection.info["feed_review_lock_timeout"] = True
        normalized = statement.casefold()
        if "for update" not in normalized:
            return
        if "users.id in" in normalized or "users.id =" in normalized:
            api_owner_lock_attempted.set()
        if "dealer_feeds" in normalized:
            api_feed_lock_started.set()

    event.listen(integration["engine"], "before_cursor_execute", observe_api_locks)
    response = None
    feed_was_locked_before_owner = False
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="feed-review") as pool:
            future = pool.submit(
                owner.post,
                f"/api/v1/dealer/feeds/{feed_id}/api-imports",
                json={"items": [{"dealer_external_id": "LOCKED-1", "manual_make": "Toyota"}]},
                headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "blocked-api-import"},
            )
            try:
                assert api_owner_lock_attempted.wait(5), "API import did not reach the owner lock"
                feed_was_locked_before_owner = api_feed_lock_started.wait(0.25)
                if feed_was_locked_before_owner:
                    # Release the simulated PATCH owner lock so the baseline defect
                    # produces a clean assertion failure rather than a DB deadlock.
                    owner_blocker.rollback()
                else:
                    # Match PATCH's owner -> company -> feed order while API import
                    # is blocked on the owner row.
                    company = owner_blocker.scalar(select(Company).where(Company.owner_id == owner_id).with_for_update())
                    assert company is not None
                    feed = owner_blocker.scalar(select(DealerFeed).where(DealerFeed.id == feed_id).with_for_update())
                    assert feed is not None
                    feed.status = "disabled"
                    owner_blocker.commit()
            finally:
                # Always release the blocking row before the executor joins its
                # worker, including timeout and assertion paths.
                if owner_blocker.in_transaction():
                    owner_blocker.rollback()
                response = future.result(timeout=10)
    finally:
        event.remove(integration["engine"], "before_cursor_execute", observe_api_locks)
        owner_blocker.close()

    assert not feed_was_locked_before_owner, "API import locked DealerFeed before waiting for the owner row"
    assert response is not None
    assert response.status_code == 401, response.text
    with factory() as db:
        assert db.scalar(select(FeedImportRun).where(FeedImportRun.feed_id == feed_id)) is None
