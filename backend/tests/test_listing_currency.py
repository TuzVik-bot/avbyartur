from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    CatalogBodyType,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Company,
    ExchangeRate,
    Listing,
    ListingCategoryDetails,
    ListingPhoto,
    ListingStatusEvent,
    SavedSearch,
    User,
)


@pytest.fixture
def currency_api():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Company.__table__,
            Listing.__table__,
            ListingCategoryDetails.__table__,
            ListingPhoto.__table__,
            ExchangeRate.__table__,
            ListingStatusEvent.__table__,
        ],
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE catalog_body_variants ("
            "id CHAR(32) PRIMARY KEY, generation_id CHAR(32) NOT NULL, slug VARCHAR(120) NOT NULL, "
            "name VARCHAR(120) NOT NULL, external_id VARCHAR(100), source_name VARCHAR(100), "
            "source_metadata TEXT, manual_override BOOLEAN NOT NULL DEFAULT 0)"
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield {"client": client, "engine": engine, "SessionLocal": factory}
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override
        engine.dispose()


def add_listing(db, owner: User, amount: str, currency: str, *, year: int = 2020) -> Listing:
    listing = Listing(
        owner_id=owner.id,
        slug=f"listing-{uuid4().hex}",
        status="active",
        revision=1,
        title=f"{currency} {amount}",
        year=year,
        description="",
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        price_amount=Decimal(amount),
        currency=currency,
    )
    db.add(listing)
    db.flush()
    return listing


def add_owner(db) -> User:
    owner = User(
        email=f"seller-{uuid4().hex}@example.com",
        display_name="Seller",
        password_hash="unused",
        role="user",
        status="active",
    )
    db.add(owner)
    db.flush()
    return owner


def add_rate(db, *, rate_date: str, fetched_at: datetime) -> None:
    db.add(ExchangeRate(
        currency="USD",
        rate_date=rate_date,
        official_rate=Decimal("3.000000"),
        scale=1,
        source="test",
        fetched_at=fetched_at,
    ))
    db.flush()


def test_search_converts_mixed_currency_for_filter_sort_and_display(currency_api):
    factory = currency_api["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    with factory() as db:
        owner = add_owner(db)
        byn_18000 = add_listing(db, owner, "18000.00", "BYN")
        usd_5000 = add_listing(db, owner, "5000.00", "USD")
        add_listing(db, owner, "14000.00", "BYN")
        add_listing(db, owner, "7000.00", "USD")
        add_rate(db, rate_date=today, fetched_at=datetime.now(timezone.utc))
        byn_18000_id, usd_5000_id = str(byn_18000.id), str(usd_5000.id)
        db.commit()

    rate_queries = []

    def count_rate_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "from exchange_rates" in statement.lower():
            rate_queries.append(statement)

    event.listen(currency_api["engine"], "before_cursor_execute", count_rate_query)
    try:
        response = currency_api["client"].get(
            "/api/v1/listings",
            params={"currency": "BYN", "price_min": "15000", "price_max": "20000", "sort": "price_asc"},
        )
    finally:
        event.remove(currency_api["engine"], "before_cursor_execute", count_rate_query)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [usd_5000_id, byn_18000_id]
    assert [item["price"]["display_amount"] for item in payload["items"]] == ["15000.00", "18000.00"]
    assert [item["price"]["display_currency"] for item in payload["items"]] == ["BYN", "BYN"]
    assert [(item["price"]["amount"], item["price"]["currency"]) for item in payload["items"]] == [
        ("5000.00", "USD"), ("18000.00", "BYN"),
    ]
    assert payload["fx"]["rate_date"] == today
    assert len(rate_queries) == 1

    usd_response = currency_api["client"].get(
        "/api/v1/listings", params={"currency": "USD", "sort": "price_asc"},
    )
    assert usd_response.status_code == 200, usd_response.text
    usd_items = usd_response.json()["items"]
    assert [item["price"]["display_amount"] for item in usd_items] == [
        "4666.67", "5000.00", "6000.00", "7000.00",
    ]
    assert [item["price"]["display_currency"] for item in usd_items] == ["USD"] * 4


def test_count_endpoint_uses_search_filters_and_ignores_page_and_sort(integration):
    factory = integration["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    with factory() as db:
        owner = add_owner(db)
        add_listing(db, owner, "18000.00", "BYN", year=2020)
        add_listing(db, owner, "5000.00", "USD", year=2021)
        add_listing(db, owner, "14000.00", "BYN", year=2020)
        add_rate(db, rate_date=today, fetched_at=datetime.now(timezone.utc))
        db.commit()

    params = {
        "currency": "BYN", "price_min": "15000", "price_max": "20000",
        "year_min": "2020", "page": 99, "page_size": 1, "sort": "price_desc",
    }
    listing_response = integration["client"].get("/api/v1/listings", params=params)
    count_response = integration["client"].get("/api/v1/listings/count", params=params)

    assert listing_response.status_code == 200, listing_response.text
    assert count_response.status_code == 200, count_response.text
    assert count_response.json() == {"total": listing_response.json()["pagination"]["total"]}
    assert count_response.json() == {"total": 2}
    assert listing_response.json()["items"] == []


def test_shared_public_search_matcher_uses_catalog_alias_and_converted_price(integration):
    from app.notification_service import saved_search_matches
    from app.services import listing_matches_public_search

    factory = integration["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    alias = f"matcher-alias-{uuid4().hex}"
    with factory() as db:
        owner = add_owner(db)
        make = CatalogMake(
            slug=f"matcher-make-{uuid4().hex}", name="Matcher Make", aliases=[alias],
        )
        db.add(make)
        db.flush()
        listing = add_listing(db, owner, "5000.00", "USD")
        listing.make_id = make.id
        listing.make_name_snapshot = "Matcher Make"
        add_rate(db, rate_date=today, fetched_at=datetime.now(timezone.utc))
        db.commit()

        converted_byn_filters = {
            "q": alias,
            "currency": "BYN",
            "price_min": "14999.99",
            "price_max": "15000.01",
        }
        assert listing_matches_public_search(db, {"q": alias}, listing) is True
        assert listing_matches_public_search(db, converted_byn_filters, listing) is True
        saved_search = SavedSearch(
            user_id=owner.id,
            name="Alias at BYN price",
            search_url=(
                f"/cars?q={alias}&currency=BYN&price_min=14999.99&price_max=15000.01"
            ),
            filters={},
        )
        assert saved_search_matches(db, saved_search, listing) is True
        assert listing_matches_public_search(
            db, {**converted_byn_filters, "price_min": "15000.01"}, listing,
        ) is False


def test_year_and_mileage_sort_put_unknown_values_last(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        newer = add_listing(db, owner, "18000", "BYN", year=2022)
        older = add_listing(db, owner, "17000", "BYN", year=2018)
        unknown = add_listing(db, owner, "16000", "BYN", year=2020)
        newer.mileage_km = 120000
        older.mileage_km = 40000
        unknown.year = None
        unknown.mileage_km = None
        db.commit()

    year_response = integration["client"].get("/api/v1/listings", params={"sort": "year_desc"})
    mileage_response = integration["client"].get("/api/v1/listings", params={"sort": "mileage_asc"})

    assert year_response.status_code == 200, year_response.text
    assert mileage_response.status_code == 200, mileage_response.text
    year_ids = [item["id"] for item in year_response.json()["items"]]
    mileage_ids = [item["id"] for item in mileage_response.json()["items"]]
    assert year_ids == [str(newer.id), str(older.id), str(unknown.id)]
    assert mileage_ids == [str(older.id), str(newer.id), str(unknown.id)]


def test_newest_sort_uses_first_publication_and_creation_fallback(currency_api):
    factory = currency_api["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        long_draft = add_listing(db, owner, "18000", "BYN")
        published_newest = add_listing(db, owner, "17000", "BYN")
        recently_created = add_listing(db, owner, "16000", "BYN")
        legacy = add_listing(db, owner, "15000", "BYN")

        long_draft.created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
        published_newest.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
        recently_created.created_at = datetime(2026, 10, 2, tzinfo=timezone.utc)
        legacy.created_at = datetime(2026, 9, 30, tzinfo=timezone.utc)
        db.add_all([
            ListingStatusEvent(
                listing_id=published_newest.id, from_status="pending_review", to_status="active",
                revision=1, created_at=datetime(2026, 10, 4, tzinfo=timezone.utc),
            ),
            ListingStatusEvent(
                listing_id=long_draft.id, from_status="draft", to_status="active",
                revision=1, created_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
            ),
            ListingStatusEvent(
                listing_id=long_draft.id, from_status="active", to_status="archived",
                revision=2, created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            ),
            ListingStatusEvent(
                listing_id=long_draft.id, from_status="archived", to_status="active",
                revision=3, created_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
            ),
            ListingStatusEvent(
                listing_id=recently_created.id, from_status="pending_review", to_status="active",
                revision=1, created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
        ])
        expected_ids = [
            str(published_newest.id), str(long_draft.id), str(recently_created.id), str(legacy.id),
        ]
        db.commit()

    response = currency_api["client"].get("/api/v1/listings", params={"sort": "newest"})

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == expected_ids


def test_listing_exposes_first_publication_event_date(integration):
    factory = integration["SessionLocal"]
    published_at = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)
    with factory() as db:
        owner = add_owner(db)
        listing = add_listing(db, owner, "18000", "BYN")
        legacy_listing = add_listing(db, owner, "17000", "BYN")
        db.add_all([
            ListingStatusEvent(
                listing_id=listing.id, from_status="pending_review", to_status="active",
                revision=1, created_at=published_at,
            ),
            ListingStatusEvent(
                listing_id=listing.id, from_status="draft", to_status="active",
                revision=2, created_at=published_at + timedelta(days=2),
            ),
        ])
        listing_id = str(listing.id)
        db.commit()

    search = integration["client"].get("/api/v1/listings", params={"q": "BYN"})
    detail = integration["client"].get(f"/api/v1/listings/{listing_id}")

    assert search.status_code == 200, search.text
    assert detail.status_code == 200, detail.text
    result = next(item for item in search.json()["items"] if item["id"] == listing_id)
    legacy = next(item for item in search.json()["items"] if item["id"] == str(legacy_listing.id))
    assert datetime.fromisoformat(result["published_at"]) == published_at
    assert detail.json()["listing"]["published_at"] == result["published_at"]
    assert legacy["published_at"] is None
    assert search.json()["items"][0]["price"]["market_comparison"] is None


def _market_catalog(db):
    suffix = uuid4().hex
    make = CatalogMake(id=uuid4(), slug=f"market-make-{suffix}", name="Market Make", aliases=[])
    db.add(make)
    db.flush()
    model = CatalogModel(
        id=uuid4(), make_id=make.id, slug=f"market-model-{suffix}",
        name="Market Model", aliases=[],
    )
    db.add(model)
    db.flush()
    generation = CatalogGeneration(
        id=uuid4(), model_id=model.id, slug=f"market-generation-{suffix}",
        name="Market Generation", year_from=2018, year_to=2022,
    )
    body_type = CatalogBodyType(id=uuid4(), slug=f"market-body-{suffix}", name="Sedan")
    db.add_all([generation, body_type])
    db.flush()
    return make, model, generation, body_type


def _market_listing(db, owner, catalog, amount: str, *, year: int = 2020, mileage: int = 80000):
    make, model, generation, body_type = catalog
    listing = add_listing(db, owner, amount, "BYN", year=year)
    listing.category_code = "cars"
    listing.make_id = make.id
    listing.model_id = model.id
    listing.generation_id = generation.id
    listing.body_type_id = body_type.id
    listing.condition = "used"
    listing.fuel = "petrol"
    listing.transmission = "automatic"
    listing.mileage_km = mileage
    return listing


@pytest.mark.parametrize(
    ("target_price", "expected_label"),
    [("18000.00", "below_market"), ("22000.00", "above_market")],
)
def test_market_comparison_thresholds_match_between_list_and_detail(
    integration, target_price, expected_label,
):
    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _market_catalog(db)
        target_owner = add_owner(db)
        target = _market_listing(db, target_owner, catalog, target_price)
        target_id = str(target.id)
        for price in ("19900", "20000", "20100", "19800", "20200", "19700", "20300", "19600", "20400", "20000"):
            peer_owner = add_owner(db)
            _market_listing(db, peer_owner, catalog, price)
        db.commit()

    listing_response = integration["client"].get("/api/v1/listings", params={"q": "BYN"})
    assert listing_response.status_code == 200, listing_response.text
    summary = next(item for item in listing_response.json()["items"] if item["id"] == target_id)
    detail_response = integration["client"].get(f"/api/v1/listings/{target_id}")
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()["listing"]

    assert summary["price"]["market_comparison"] == detail["price"]["market_comparison"]
    assert summary["price"]["market_comparison"]["label"] == expected_label
    assert summary["price"]["market_comparison"]["median_byn"] == "20000.00"
    assert summary["price"]["market_comparison"]["sample_size"] == 10
    assert summary["price"]["market_comparison"]["seller_count"] == 10


def test_market_comparison_requires_ten_comparable_listings(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _market_catalog(db)
        target = _market_listing(db, add_owner(db), catalog, "18000")
        for price in ("19900", "20000", "20100", "19800", "20200", "19700", "20300", "19600", "20400"):
            _market_listing(db, add_owner(db), catalog, price)
        target_id = str(target.id)
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{target_id}")

    assert response.status_code == 200, response.text
    assert response.json()["listing"]["price"]["market_comparison"] is None


def test_market_comparison_excludes_same_seller_damage_parts_and_out_of_range_mileage(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _market_catalog(db)
        target_owner = add_owner(db)
        target = _market_listing(db, target_owner, catalog, "18000")
        for _ in range(10):
            _market_listing(db, add_owner(db), catalog, "20000")
        _market_listing(db, target_owner, catalog, "19000")
        far_mileage = _market_listing(db, add_owner(db), catalog, "19000", mileage=90000)
        far_mileage.mileage_km = 90000
        damaged = _market_listing(db, add_owner(db), catalog, "19000")
        damaged.damaged = True
        parts = _market_listing(db, add_owner(db), catalog, "19000")
        parts.parts_only = True
        outside_year = _market_listing(db, add_owner(db), catalog, "19000", year=2022)
        target_id = str(target.id)
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{target_id}")

    assert response.status_code == 200, response.text
    comparison = response.json()["listing"]["price"]["market_comparison"]
    assert comparison["sample_size"] == 10
    assert comparison["seller_count"] == 10


def test_market_comparison_converts_usd_analogs_with_fresh_rate(integration):
    factory = integration["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    with factory() as db:
        catalog = _market_catalog(db)
        target = _market_listing(db, add_owner(db), catalog, "18000")
        for _ in range(9):
            _market_listing(db, add_owner(db), catalog, "20000")
        usd_peer = _market_listing(db, add_owner(db), catalog, "6666.67")
        usd_peer.currency = "USD"
        add_rate(db, rate_date=today, fetched_at=datetime.now(timezone.utc))
        target_id = str(target.id)
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{target_id}")

    assert response.status_code == 200, response.text
    comparison = response.json()["listing"]["price"]["market_comparison"]
    assert comparison["median_byn"] == "20000.00"
    assert comparison["rate_date"] == today


def test_market_comparison_suppresses_mixed_currency_when_rate_is_stale(integration):
    factory = integration["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    with factory() as db:
        catalog = _market_catalog(db)
        target = _market_listing(db, add_owner(db), catalog, "18000")
        for _ in range(9):
            _market_listing(db, add_owner(db), catalog, "20000")
        usd_peer = _market_listing(db, add_owner(db), catalog, "6666.67")
        usd_peer.currency = "USD"
        add_rate(
            db, rate_date=today,
            fetched_at=datetime.now(timezone.utc) - timedelta(days=4),
        )
        target_id = str(target.id)
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{target_id}")

    assert response.status_code == 200, response.text
    assert response.json()["listing"]["price"]["market_comparison"] is None


def test_market_comparison_uses_one_analog_query_for_a_listing_page(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _market_catalog(db)
        for _ in range(10):
            _market_listing(db, add_owner(db), catalog, "20000")
        db.commit()

    listing_queries = []

    def record_listing_query(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = statement.casefold()
        if normalized.lstrip().startswith("select") and "from listings" in normalized:
            listing_queries.append(statement)

    event.listen(integration["engine"], "before_cursor_execute", record_listing_query)
    try:
        response = integration["client"].get("/api/v1/listings")
    finally:
        event.remove(integration["engine"], "before_cursor_execute", record_listing_query)

    assert response.status_code == 200, response.text
    analog_queries = [
        statement for statement in listing_queries
        if "listings.price_amount is not null" in statement.casefold()
        and "listings.currency in" in statement.casefold()
    ]
    assert len(analog_queries) == 1  # Analog matching stays batched for the page.


def test_market_comparison_uses_analogs_outside_the_current_page(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _market_catalog(db)
        targets = []
        for index in range(10):
            target = _market_listing(db, add_owner(db), catalog, "18000")
            target.title = f"Batch match target {index}"
            targets.append(target)
        for _ in range(10):
            _market_listing(db, add_owner(db), catalog, "20000")
        target_id = str(targets[0].id)
        db.commit()

    response = integration["client"].get(
        "/api/v1/listings",
        params={"q": "Batch match target", "page_size": 10},
    )

    assert response.status_code == 200, response.text
    result = next(item for item in response.json()["items"] if item["id"] == target_id)
    comparison = result["price"]["market_comparison"]
    assert comparison["label"] == "below_market"
    assert comparison["sample_size"] == 19
    assert comparison["seller_count"] == 19


def test_private_listing_serialization_skips_market_comparison(integration, monkeypatch):
    from app.api import listings as listings_api

    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _market_catalog(db)
        target = _market_listing(db, add_owner(db), catalog, "18000")
        db.commit()
        db.refresh(target)

        def unexpected_market_calculation(*_args, **_kwargs):
            raise AssertionError("private listing must not calculate market comparison")

        monkeypatch.setattr(listings_api, "build_market_comparisons", unexpected_market_calculation)
        result = listings_api._listed(db, [target], public=False)

    assert result[0]["price"]["market_comparison"] is None


def test_postgres_search_converts_mixed_currency(integration):
    factory = integration["SessionLocal"]
    today = datetime.now(timezone.utc).date()
    with factory() as db:
        owner = add_owner(db)
        byn_listing = add_listing(db, owner, "18000.00", "BYN")
        usd_listing = add_listing(db, owner, "5000.00", "USD")
        add_listing(db, owner, "14000.00", "BYN")
        add_rate(
            db,
            rate_date=(today - timedelta(days=1)).isoformat(),
            fetched_at=datetime.now(timezone.utc),
        )
        expected_ids = [str(usd_listing.id), str(byn_listing.id)]
        db.commit()

    response = integration["client"].get(
        "/api/v1/listings",
        params={"currency": "BYN", "price_min": "15000", "price_max": "20000", "sort": "price_asc"},
    )
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == expected_ids
    assert [item["price"]["display_amount"] for item in response.json()["items"]] == ["15000.00", "18000.00"]


def test_postgres_search_filters_exact_modification_with_safe_summary(integration):
    factory = integration["SessionLocal"]
    suffix = uuid4().hex
    source_marker = f"private-catalog-metadata-{suffix}"
    with factory() as db:
        owner = add_owner(db)
        make = CatalogMake(slug=f"search-make-{suffix}", name="Search Make", aliases=[])
        db.add(make)
        db.flush()
        model = CatalogModel(
            make_id=make.id,
            slug=f"search-model-{suffix}",
            name="Search Model",
            aliases=[],
        )
        db.add(model)
        db.flush()
        generation = CatalogGeneration(
            model_id=model.id,
            slug=f"search-generation-{suffix}",
            name="Search Generation",
            year_from=2018,
            year_to=2022,
        )
        db.add(generation)
        db.flush()
        selected_modification = CatalogModification(
            generation_id=generation.id,
            slug=f"selected-{suffix}",
            name="2.0 MT",
            source_name="Test catalog",
            source_metadata={"marker": source_marker},
            manual_override=False,
        )
        other_modification = CatalogModification(
            generation_id=generation.id,
            slug=f"other-{suffix}",
            name="1.6 AT",
            source_name="Test catalog",
            source_metadata={"marker": f"other-{suffix}"},
            manual_override=False,
        )
        db.add_all([selected_modification, other_modification])
        db.flush()

        matching = add_listing(db, owner, "10000.00", "BYN", year=2020)
        matching.make_id = make.id
        matching.model_id = model.id
        matching.generation_id = generation.id
        matching.modification_id = selected_modification.id
        other_trim = add_listing(db, owner, "11000.00", "BYN", year=2020)
        other_trim.make_id = make.id
        other_trim.model_id = model.id
        other_trim.generation_id = generation.id
        other_trim.modification_id = other_modification.id
        outside_year_filter = add_listing(db, owner, "12000.00", "BYN", year=2019)
        outside_year_filter.make_id = make.id
        outside_year_filter.model_id = model.id
        outside_year_filter.generation_id = generation.id
        outside_year_filter.modification_id = selected_modification.id
        add_listing(db, owner, "13000.00", "BYN", year=2020)
        matching_id = str(matching.id)
        selected_modification_id = str(selected_modification.id)
        db.commit()

    response = integration["client"].get(
        "/api/v1/listings",
        params={"modification_id": selected_modification_id, "year_min": 2020},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [matching_id]
    assert payload["pagination"]["total"] == 1
    summary = payload["items"][0]
    assert "modification" not in summary
    assert "modification_id" not in summary
    assert "source_metadata" not in summary
    assert source_marker not in response.text


def test_search_filters_exact_modification_and_preserves_existing_filters(currency_api):
    factory = currency_api["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        selected_modification_id = uuid4()
        other_modification_id = uuid4()

        matching = add_listing(db, owner, "10000.00", "BYN", year=2020)
        matching.modification_id = selected_modification_id
        different_modification = add_listing(db, owner, "11000.00", "BYN", year=2020)
        different_modification.modification_id = other_modification_id
        outside_year_filter = add_listing(db, owner, "12000.00", "BYN", year=2019)
        outside_year_filter.modification_id = selected_modification_id
        add_listing(db, owner, "13000.00", "BYN", year=2020)
        matching_id = str(matching.id)
        db.commit()

    response = currency_api["client"].get(
        "/api/v1/listings",
        params={"modification_id": str(selected_modification_id), "year_min": 2020},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [matching_id]
    assert payload["pagination"]["total"] == 1
    summary = payload["items"][0]
    assert "modification" not in summary
    assert "modification_id" not in summary
    assert "source_metadata" not in summary


def test_search_rejects_invalid_modification_uuid_using_validation_contract(currency_api):
    response = currency_api["client"].get(
        "/api/v1/listings", params={"modification_id": "not-a-uuid"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "modification_id" in response.json()["field_errors"]


def test_search_filters_exact_body_variant_and_preserves_existing_filters(currency_api):
    factory = currency_api["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        selected_variant_id = uuid4()
        other_variant_id = uuid4()

        matching = add_listing(db, owner, "10000.00", "BYN", year=2020)
        matching.body_variant_id = selected_variant_id
        different_variant = add_listing(db, owner, "11000.00", "BYN", year=2020)
        different_variant.body_variant_id = other_variant_id
        outside_year_filter = add_listing(db, owner, "12000.00", "BYN", year=2019)
        outside_year_filter.body_variant_id = selected_variant_id
        add_listing(db, owner, "13000.00", "BYN", year=2020)
        matching_id = str(matching.id)
        db.commit()

    response = currency_api["client"].get(
        "/api/v1/listings",
        params={"body_variant_id": str(selected_variant_id), "year_min": 2020},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [matching_id]
    assert payload["pagination"]["total"] == 1


def test_search_rejects_invalid_body_variant_uuid_using_validation_contract(currency_api):
    response = currency_api["client"].get(
        "/api/v1/listings", params={"body_variant_id": "not-a-uuid"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "body_variant_id" in response.json()["field_errors"]


def test_search_returns_empty_for_unknown_body_variant_uuid(currency_api):
    factory = currency_api["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        other_variant_listing = add_listing(db, owner, "10000.00", "BYN")
        other_variant_listing.body_variant_id = uuid4()
        db.commit()

    response = currency_api["client"].get(
        "/api/v1/listings", params={"body_variant_id": str(uuid4())},
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["pagination"]["total"] == 0


def test_detail_displays_fresh_byn_equivalent_and_preserves_original_price(currency_api):
    factory = currency_api["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    with factory() as db:
        owner = add_owner(db)
        usd_id = str(add_listing(db, owner, "5000.00", "USD").id)
        byn_id = str(add_listing(db, owner, "18000.00", "BYN").id)
        add_rate(db, rate_date=today, fetched_at=datetime.now(timezone.utc))
        db.commit()

    for listing_id, original, displayed in (
        (usd_id, ("5000.00", "USD"), "15000.00"),
        (byn_id, ("18000.00", "BYN"), "18000.00"),
    ):
        response = currency_api["client"].get(f"/api/v1/listings/{listing_id}")
        assert response.status_code == 200, response.text
        price = response.json()["listing"]["price"]
        assert (price["amount"], price["currency"]) == original
        assert price["display_amount"] == displayed
        assert price["display_currency"] == "BYN"
        assert price["display_byn"] == displayed
        assert price["rate_date"] == today


def test_postgres_detail_displays_fresh_byn_equivalent(integration):
    factory = integration["SessionLocal"]
    today = datetime.now(timezone.utc).date().isoformat()
    with factory() as db:
        owner = add_owner(db)
        listing_id = str(add_listing(db, owner, "5000.00", "USD").id)
        add_rate(db, rate_date=today, fetched_at=datetime.now(timezone.utc))
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{listing_id}")
    assert response.status_code == 200, response.text
    assert response.json()["listing"]["price"] == {
        "amount": "5000.00",
        "currency": "USD",
        "display_byn": "15000.00",
        "rate_date": today,
        "display_amount": "15000.00",
        "display_currency": "BYN",
        "market_comparison": None,
    }


@pytest.mark.parametrize("rate_state", ["missing", "stale", "future"])
def test_detail_keeps_original_usd_price_without_fresh_rate(currency_api, rate_state):
    factory = currency_api["SessionLocal"]
    today = datetime.now(timezone.utc).date()
    with factory() as db:
        owner = add_owner(db)
        listing_id = str(add_listing(db, owner, "5000.00", "USD").id)
        if rate_state == "stale":
            add_rate(db, rate_date=today.isoformat(), fetched_at=datetime.now(timezone.utc) - timedelta(hours=73))
        elif rate_state == "future":
            add_rate(db, rate_date=(today + timedelta(days=1)).isoformat(), fetched_at=datetime.now(timezone.utc))
        db.commit()

    response = currency_api["client"].get(f"/api/v1/listings/{listing_id}")
    assert response.status_code == 200, response.text
    price = response.json()["listing"]["price"]
    assert (price["amount"], price["currency"]) == ("5000.00", "USD")
    assert "display_amount" not in price
    assert "display_currency" not in price
    assert price["display_byn"] is None
    assert price["rate_date"] is None


@pytest.mark.parametrize("rate_state", ["missing", "stale", "future"])
def test_unusable_rate_disables_price_operations_but_keeps_other_filters(currency_api, rate_state):
    factory = currency_api["SessionLocal"]
    today = datetime.now(timezone.utc).date()
    with factory() as db:
        owner = add_owner(db)
        add_listing(db, owner, "18000.00", "BYN", year=2020)
        add_listing(db, owner, "5000.00", "USD", year=2019)
        if rate_state == "stale":
            add_rate(db, rate_date=today.isoformat(), fetched_at=datetime.now(timezone.utc) - timedelta(hours=73))
        elif rate_state == "future":
            add_rate(db, rate_date=(today + timedelta(days=1)).isoformat(), fetched_at=datetime.now(timezone.utc))
        db.commit()

    for params in (
        {"currency": "BYN", "price_min": "10000"},
        {"currency": "BYN", "sort": "price_desc"},
    ):
        response = currency_api["client"].get("/api/v1/listings", params=params)
        assert response.status_code == 422
        assert response.json()["code"] == "exchange_rate_unavailable"

    filtered = currency_api["client"].get(
        "/api/v1/listings", params={"currency": "BYN", "year_min": "2020"},
    )
    assert filtered.status_code == 200, filtered.text
    assert len(filtered.json()["items"]) == 1
    assert "fx" not in filtered.json()
    assert filtered.json()["items"][0]["price"]["amount"] == "18000.00"
    assert filtered.json()["items"][0]["price"]["currency"] == "BYN"
    assert "display_amount" not in filtered.json()["items"][0]["price"]
    assert "display_currency" not in filtered.json()["items"][0]["price"]
