import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select

from app import models
from app.listing_schemas import ListingSearchFilters
from app.services import (
    build_public_listing_query,
    enqueue_saved_search_match,
    listing_matches_public_search,
)
from tests.test_saved_search_notifications import add_listing, add_user, run_job

NON_MATCHING_SEARCH_URLS = (
    "/cars?year_min=2022",
    "/cars?fuel=petrol",
    "/cars?category_code=trucks",
    "/cars?transmission=manual",
    "/cars?mileage_max=10000",
    "/cars?seller_type=company",
    f"/cars?region_id={uuid.uuid4()}",
    f"/cars?make_id={uuid.uuid4()}",
)
NON_MATCHING_COPIES = 5
# Fixed statements per job: job/listing/visibility/publication lookups, the
# chunked search load and the writes for the single matching search.
MAX_MATCH_JOB_SELECTS = 20


def _saved_search(user_id: uuid.UUID, search_url: str) -> models.SavedSearch:
    return models.SavedSearch(
        user_id=user_id,
        name=search_url,
        search_url=search_url,
        filters={},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="instant",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )


def test_saved_search_matching_uses_bounded_queries_for_many_searches(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"perf-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(
        factory, f"perf-subscriber-{uuid.uuid4().hex[:8]}@example.com"
    )
    listing = add_listing(factory, owner.id)
    with factory() as db:
        for _ in range(NON_MATCHING_COPIES):
            db.add_all(
                _saved_search(subscriber.id, url) for url in NON_MATCHING_SEARCH_URLS
            )
        matching = _saved_search(subscriber.id, "/cars?year_min=2019&fuel=diesel")
        db.add(matching)
        db.flush()
        enqueue_saved_search_match(db, listing)
        db.commit()
        matching_id = matching.id
        job_id = db.scalar(
            select(models.WorkerJob.id).where(
                models.WorkerJob.kind == "saved-search.match"
            )
        )

    selects: list[str] = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    engine = integration["engine"]
    event.listen(engine, "before_cursor_execute", record)
    try:
        run_job(factory, job_id)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    with factory() as db:
        notified = db.scalars(select(models.NotificationOutbox.saved_search_id)).all()
    assert notified == [matching_id]
    assert len(selects) <= MAX_MATCH_JOB_SELECTS, len(selects)


@pytest.mark.parametrize(
    "filters",
    [
        {},
        {"year_min": 2020, "year_max": 2020},
        {"year_min": 2021},
        {"year_max": 2019},
        {"mileage_min": 45000},
        {"mileage_max": 44999},
        {"power_min": 100},
        {"fuel": "diesel", "transmission": "automatic", "drive": "rear"},
        {"fuel": "Diesel"},
        {"condition": "new"},
        {"damaged": False, "parts_only": False},
        {"damaged": True},
        {"exchange": True},
        {"category_code": "trucks"},
        {"seller_type": "private"},
        {"seller_type": "company"},
        {"color": "black"},
        {"make_id": "MAKE"},
        {"make_id": str(uuid.UUID(int=1))},
        {"make_ids": "MAKE"},
        {"make_ids": f"{uuid.UUID(int=1)},MAKE"},
        {"make_ids": str(uuid.UUID(int=1))},
        {"make_id": "MAKE", "model_id": "MODEL"},
        {"make_id": "MAKE", "model_id": str(uuid.UUID(int=2))},
        {"region_id": str(uuid.UUID(int=3))},
        {"q": "bmw"},
        {"q": "honda"},
        {"has_vin": True},
        {"engine_volume_min": "1.6"},
    ],
)
def test_in_memory_prefilter_never_changes_the_public_query_result(
    integration, filters
):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"eq-owner-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id)
    with factory() as db:
        make = models.CatalogMake(slug=f"bmw-{uuid.uuid4().hex[:8]}", name="BMW")
        db.add(make)
        db.flush()
        model = models.CatalogModel(
            make_id=make.id, slug=f"3-{uuid.uuid4().hex[:8]}", name="3 Series"
        )
        db.add(model)
        db.flush()
        stored = db.get(models.Listing, listing.id)
        stored.make_id, stored.model_id = make.id, model.id
        db.commit()
        resolved = {
            key: value.replace("MAKE", str(make.id)).replace("MODEL", str(model.id))
            if isinstance(value, str)
            else value
            for key, value in filters.items()
        }
        stored = db.get(models.Listing, listing.id)

        parsed = ListingSearchFilters.model_validate(resolved)
        query, _ = build_public_listing_query(db, parsed, (None, False))
        reference = query.with_only_columns(models.Listing.id).where(models.Listing.id == stored.id)
        sql_result = db.scalar(reference) is not None

        assert listing_matches_public_search(db, resolved, stored) is sql_result
