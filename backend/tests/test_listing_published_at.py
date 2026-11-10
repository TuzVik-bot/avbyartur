from datetime import datetime, timedelta, timezone

from sqlalchemy import event, select

from app.models import Listing, ListingStatusEvent
from tests.test_listing_currency import add_listing, add_owner


def _status_event(
    listing: Listing, to_status: str, created_at: datetime, revision: int = 1
):
    return ListingStatusEvent(
        listing_id=listing.id,
        from_status="pending_review",
        to_status=to_status,
        revision=revision,
        created_at=created_at,
    )


def test_first_active_status_event_sets_published_at(integration):
    factory = integration["SessionLocal"]
    first = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
    with factory() as db:
        listing = add_listing(db, add_owner(db), "18000", "BYN")
        untouched = add_listing(db, add_owner(db), "17000", "BYN")
        db.add(_status_event(listing, "active", first))
        db.flush()
        assert listing.published_at == first
        db.add_all(
            [
                _status_event(listing, "archived", first + timedelta(days=1), 2),
                _status_event(listing, "active", first + timedelta(days=3), 3),
            ]
        )
        db.commit()
        listing_id, untouched_id = listing.id, untouched.id

    with factory() as db:
        assert (
            db.scalar(select(Listing.published_at).where(Listing.id == listing_id))
            == first
        )
        assert (
            db.scalar(select(Listing.published_at).where(Listing.id == untouched_id))
            is None
        )


def test_backdated_active_event_lowers_published_at_to_first_publication(integration):
    factory = integration["SessionLocal"]
    later = datetime(2026, 9, 10, tzinfo=timezone.utc)
    earlier = datetime(2026, 9, 2, tzinfo=timezone.utc)
    with factory() as db:
        listing = add_listing(db, add_owner(db), "18000", "BYN")
        db.add(_status_event(listing, "active", later))
        db.commit()
        db.add(_status_event(listing, "active", earlier, 2))
        db.commit()
        listing_id = listing.id

    with factory() as db:
        assert (
            db.scalar(select(Listing.published_at).where(Listing.id == listing_id))
            == earlier
        )


def test_server_default_event_time_is_copied_to_published_at(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        listing = add_listing(db, add_owner(db), "18000", "BYN")
        db.add(
            ListingStatusEvent(
                listing_id=listing.id,
                from_status="pending_review",
                to_status="active",
                revision=1,
            )
        )
        db.commit()
        event_time = db.scalar(
            select(ListingStatusEvent.created_at).where(
                ListingStatusEvent.listing_id == listing.id
            )
        )
        published_at = db.scalar(
            select(Listing.published_at).where(Listing.id == listing.id)
        )

    assert event_time is not None
    assert published_at == event_time


def test_publication_sorts_do_not_aggregate_status_history(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        older = add_listing(db, owner, "18000", "BYN")
        newer = add_listing(db, owner, "17000", "BYN")
        db.add_all(
            [
                _status_event(
                    older, "active", datetime(2026, 9, 1, tzinfo=timezone.utc)
                ),
                _status_event(
                    newer, "active", datetime(2026, 9, 5, tzinfo=timezone.utc)
                ),
            ]
        )
        db.commit()
        older_id, newer_id = str(older.id), str(newer.id)

    statements: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    engine = integration["engine"]
    event.listen(engine, "before_cursor_execute", record)
    try:
        responses = {
            sort: integration["client"].get("/api/v1/listings", params={"sort": sort})
            for sort in ("newest", "published_desc", "oldest")
        }
    finally:
        event.remove(engine, "before_cursor_execute", record)

    for response in responses.values():
        assert response.status_code == 200, response.text
    assert [item["id"] for item in responses["newest"].json()["items"]] == [
        newer_id,
        older_id,
    ]
    assert [item["id"] for item in responses["published_desc"].json()["items"]] == [
        newer_id,
        older_id,
    ]
    assert [item["id"] for item in responses["oldest"].json()["items"]] == [
        older_id,
        newer_id,
    ]
    newest_items = responses["newest"].json()["items"]
    assert datetime.fromisoformat(newest_items[0]["published_at"]) == datetime(
        2026, 9, 5, tzinfo=timezone.utc
    )
    search_statements = [
        statement
        for statement in statements
        if "FROM listings" in statement and "ORDER BY" in statement
    ]
    assert search_statements
    assert not any(
        "listing_status_events" in statement for statement in search_statements
    )
