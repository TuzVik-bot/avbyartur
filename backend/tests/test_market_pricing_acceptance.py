from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

from app.market_pricing import MAXIMUM_ANALOGS_PER_TARGET, build_market_comparisons, build_market_estimate
from app.listing_schemas import ListingMarketEstimateIn
from app.models import (
    CatalogBodyType,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    Company,
    Listing,
    User,
)


def _listing(**overrides):
    values = {
        "id": uuid.uuid4(),
        "owner_id": uuid.uuid4(),
        "company_id": None,
        "status": "active",
        "category_code": "cars",
        "make_id": uuid.UUID(int=1001),
        "model_id": uuid.UUID(int=1002),
        "generation_id": None,
        "year": 2020,
        "mileage_km": 80_000,
        "condition": "used",
        "fuel": "petrol",
        "transmission": "manual",
        "body_type_id": uuid.UUID(int=1003),
        "price_amount": Decimal("18000"),
        "currency": "BYN",
        "damaged": False,
        "parts_only": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeSession:
    def __init__(self, listings):
        self.listings = listings
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        rows = []
        ordered_listings = sorted(self.listings, key=lambda listing: listing.id)
        for branch in getattr(statement, "selects", (statement,)):
            target_id = branch.selected_columns["target_id"].element.value
            for listing in ordered_listings[: MAXIMUM_ANALOGS_PER_TARGET + 1]:
                rows.append(
                    {
                        "target_id": target_id,
                        "candidate_id": listing.id,
                        "candidate_owner_id": listing.owner_id,
                        "candidate_company_id": listing.company_id,
                        "candidate_category_code": listing.category_code,
                        "candidate_make_id": listing.make_id,
                        "candidate_model_id": listing.model_id,
                        "candidate_generation_id": listing.generation_id,
                        "candidate_year": listing.year,
                        "candidate_mileage_km": listing.mileage_km,
                        "candidate_condition": listing.condition,
                        "candidate_fuel": listing.fuel,
                        "candidate_transmission": listing.transmission,
                        "candidate_body_type_id": listing.body_type_id,
                        "candidate_price_amount": listing.price_amount,
                        "candidate_currency": listing.currency,
                        "candidate_status": listing.status,
                        "candidate_damaged": listing.damaged,
                        "candidate_parts_only": listing.parts_only,
                    }
                )
        return SimpleNamespace(all=lambda: rows)


class CountingSession:
    def __init__(self, session):
        self.session = session
        self.statements = []
        self.returned_row_counts = []

    def execute(self, statement):
        self.statements.append(statement)
        rows = self.session.execute(statement).all()
        self.returned_row_counts.append(len(rows))
        return SimpleNamespace(all=lambda: rows)


def _compare(target, candidates):
    return build_market_comparisons(FakeSession(candidates), [target], (None, False))[
        target.id
    ]


def _db_market_catalog(db):
    suffix = uuid.uuid4().hex
    make = CatalogMake(slug=f"market-make-{suffix}", name="Market Make", aliases=[])
    db.add(make)
    db.flush()
    model = CatalogModel(
        make_id=make.id,
        slug=f"market-model-{suffix}",
        name="Market Model",
        aliases=[],
    )
    db.add(model)
    db.flush()
    generation = CatalogGeneration(
        model_id=model.id,
        slug=f"market-generation-{suffix}",
        name="Market Generation",
        year_from=2018,
        year_to=2022,
    )
    body_type = CatalogBodyType(slug=f"market-body-{suffix}", name="Sedan")
    db.add_all([generation, body_type])
    db.flush()
    return make, model, generation, body_type


def _db_market_owner(db, *, status="active"):
    owner = User(
        email=f"market-{uuid.uuid4().hex}@example.com",
        display_name="Market Seller",
        password_hash="unused",
        role="user",
        status=status,
    )
    db.add(owner)
    db.flush()
    return owner


def _db_market_company(db, owner, *, status="pending"):
    company = Company(
        owner_id=owner.id,
        name="Pending Market Company",
        slug=f"pending-market-{uuid.uuid4().hex}",
        unp=f"{uuid.uuid4().int % 999_999_999 + 1:09d}",
        address="Test address",
        phone="+375291234567",
        status=status,
    )
    db.add(company)
    db.flush()
    return company


def _db_market_listing(
    db,
    owner,
    catalog,
    amount,
    *,
    status="active",
    category_code="cars",
    company=None,
):
    make, model, generation, body_type = catalog
    listing = Listing(
        owner_id=owner.id,
        company_id=company.id if company else None,
        slug=f"market-listing-{uuid.uuid4().hex}",
        status=status,
        category_code=category_code,
        revision=1,
        title="Market Make Market Model",
        make_id=make.id,
        model_id=model.id,
        generation_id=generation.id,
        body_type_id=body_type.id,
        year=2020,
        mileage_km=80_000,
        condition="used",
        fuel="petrol",
        transmission="automatic",
        damaged=False,
        parts_only=False,
        price_amount=Decimal(amount),
        currency="BYN",
        description="",
        contact_phone="+375291234567",
    )
    db.add(listing)
    db.flush()
    return listing


def test_market_comparison_hides_ten_listings_from_fewer_than_five_sellers():
    target = _listing(owner_id=uuid.UUID(int=1000))
    candidates = [
        _listing(
            owner_id=uuid.UUID(int=(index % 4) + 1),
            price_amount=Decimal("20000"),
        )
        for index in range(10)
    ]

    assert _compare(target, candidates) is None


def test_market_comparison_requires_ten_listings_and_five_sellers_at_the_threshold():
    target = _listing(owner_id=uuid.UUID(int=1000))
    nine_candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(9)
    ]
    assert _compare(target, nine_candidates) is None

    ten_candidates = [
        _listing(
            owner_id=uuid.UUID(int=(index % 5) + 1),
            price_amount=Decimal("20000"),
        )
        for index in range(10)
    ]
    comparison = _compare(target, ten_candidates)

    assert comparison is not None
    assert comparison["label"] == "below_market"
    assert comparison["sample_size"] == 10
    assert comparison["seller_count"] == 5


def test_market_estimate_returns_only_aggregate_median_and_excludes_own_seller():
    target = _listing(owner_id=uuid.UUID(int=1000), price_amount=None, currency=None)
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(10)
    ] + [_listing(owner_id=target.owner_id, price_amount=Decimal("1000"))]

    result = build_market_estimate(FakeSession(candidates), target, (None, False))

    assert result is not None
    assert result["median_byn"] == "20000.00"
    assert result["sample_size"] == 10
    assert result["seller_count"] == 10
    assert set(result) == {"median_byn", "sample_size", "seller_count", "as_of", "rate_date"}


def test_market_estimate_hides_insufficient_samples():
    target = _listing(owner_id=uuid.UUID(int=1000), price_amount=None, currency=None)
    candidates = [_listing(owner_id=uuid.UUID(int=index + 1)) for index in range(9)]

    assert build_market_estimate(FakeSession(candidates), target, (None, False)) is None


def test_market_estimate_request_rejects_vin_and_plate_fields():
    payload = {
        "seller_type": "private", "make_id": str(uuid.uuid4()), "model_id": str(uuid.uuid4()),
        "body_type_id": str(uuid.uuid4()), "year": 2020, "mileage_km": 80000,
        "condition": "used", "fuel": "petrol", "transmission": "manual", "vin": "WVWZZZ",
    }

    with pytest.raises(Exception):
        ListingMarketEstimateIn.model_validate(payload)


def test_market_comparison_hides_sample_with_iqr_over_half_the_median():
    target = _listing(owner_id=uuid.UUID(int=1000))
    prices = [Decimal("10000")] * 6 + [Decimal("30000")] * 4
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=price)
        for index, price in enumerate(prices)
    ]

    assert _compare(target, candidates) is None


def test_market_comparison_excludes_the_target_listing_and_seller():
    target_seller = uuid.UUID(int=1000)
    target = _listing(owner_id=target_seller)
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(10)
    ]
    candidates.extend(
        _listing(owner_id=target_seller, price_amount=Decimal("1000"))
        for _ in range(3)
    )
    candidates.append(
        _listing(
            id=target.id,
            owner_id=target_seller,
            price_amount=Decimal("1000"),
        )
    )

    comparison = _compare(target, candidates)

    assert comparison is not None
    assert comparison["sample_size"] == 10
    assert comparison["seller_count"] == 10
    assert comparison["median_byn"] == "20000.00"


def test_market_comparison_hides_many_listings_from_one_dealer():
    target = _listing(owner_id=uuid.UUID(int=1000))
    company_id = uuid.UUID(int=2000)
    candidates = [
        _listing(
            owner_id=uuid.UUID(int=index + 1),
            company_id=company_id,
            price_amount=Decimal("20000"),
        )
        for index in range(10)
    ]

    assert _compare(target, candidates) is None


def test_market_comparison_converts_usd_analogs_with_a_fresh_rate():
    target = _listing(owner_id=uuid.UUID(int=1000))
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(9)
    ]
    candidates.append(
        _listing(
            owner_id=uuid.UUID(int=10),
            price_amount=Decimal("6666.67"),
            currency="USD",
        )
    )
    rate = SimpleNamespace(
        official_rate=Decimal("3"), scale=1, rate_date="2026-10-14"
    )

    comparison = build_market_comparisons(
        FakeSession(candidates), [target], (rate, True)
    )[target.id]

    assert comparison is not None
    assert comparison["median_byn"] == "20000.00"
    assert comparison["rate_date"] == "2026-10-14"


def test_market_comparison_hides_mixed_currencies_when_the_rate_is_stale():
    target = _listing(owner_id=uuid.UUID(int=1000))
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(9)
    ]
    candidates.append(
        _listing(
            owner_id=uuid.UUID(int=10),
            price_amount=Decimal("6666.67"),
            currency="USD",
        )
    )

    assert build_market_comparisons(FakeSession(candidates), [target], (None, False))[target.id] is None


def test_market_comparison_batches_twenty_five_targets_and_queries_only_car_analogs():
    targets = [
        _listing(owner_id=uuid.UUID(int=10_000 + index))
        for index in range(25)
    ]
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(10)
    ]
    session = FakeSession(candidates)

    comparisons = build_market_comparisons(session, targets, (None, False))

    assert len(session.statements) == 1
    assert len(session.statements[0].selects) == 25
    assert all(comparisons[target.id] is not None for target in targets)
    query = str(session.statements[0])
    assert "listings.category_code =" in query
    assert "listings.status =" in query
    assert "users.status =" in query
    assert "companies.status =" in query
    assert query.upper().count("LIMIT") == 25


def test_database_query_uses_only_active_public_car_analogs_and_excludes_target_seller(
    integration,
):
    factory = integration["SessionLocal"]
    with factory() as db:
        catalog = _db_market_catalog(db)
        target_owner = _db_market_owner(db)
        target = _db_market_listing(db, target_owner, catalog, "18000")
        for _ in range(10):
            _db_market_listing(db, _db_market_owner(db), catalog, "20000")

        # These rows match the car cohort but must not affect the comparison.
        _db_market_listing(db, target_owner, catalog, "1000")
        _db_market_listing(
            db,
            _db_market_owner(db),
            catalog,
            "1000",
            category_code="trucks",
        )
        _db_market_listing(
            db,
            _db_market_owner(db),
            catalog,
            "1000",
            status="paused",
        )
        _db_market_listing(
            db,
            _db_market_owner(db, status="inactive"),
            catalog,
            "1000",
        )
        pending_company_owner = _db_market_owner(db)
        pending_company = _db_market_company(db, pending_company_owner)
        _db_market_listing(
            db,
            pending_company_owner,
            catalog,
            "1000",
            company=pending_company,
        )
        db.flush()

        session = CountingSession(db)
        comparison = build_market_comparisons(session, [target], (None, False))[target.id]

    assert comparison is not None
    assert comparison["label"] == "below_market"
    assert comparison["median_byn"] == "20000.00"
    assert comparison["sample_size"] == 10
    assert comparison["seller_count"] == 10
    assert len(session.statements) == 1
    assert session.returned_row_counts == [10]


def test_database_market_comparison_caps_each_target_and_hides_overflow(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        targets_by_count = {}
        for candidate_count in (99, 100, MAXIMUM_ANALOGS_PER_TARGET + 1):
            catalog = _db_market_catalog(db)
            target_owner = _db_market_owner(db)
            target = _db_market_listing(db, target_owner, catalog, "18000")
            targets_by_count[candidate_count] = target
            for _ in range(candidate_count):
                _db_market_listing(db, _db_market_owner(db), catalog, "20000")

        session = CountingSession(db)
        comparisons = build_market_comparisons(
            session, list(targets_by_count.values()), (None, False)
        )

    assert len(session.statements) == 1
    assert session.returned_row_counts == [99 + 100 + 101]
    assert comparisons[targets_by_count[99].id]["sample_size"] == 99
    assert comparisons[targets_by_count[100].id]["sample_size"] == 100
    assert comparisons[targets_by_count[101].id] is None


def test_database_market_comparison_batches_a_page_of_twenty_five_targets(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        targets = []
        for _ in range(25):
            catalog = _db_market_catalog(db)
            target = _db_market_listing(
                db, _db_market_owner(db), catalog, "18000"
            )
            targets.append(target)
            for _ in range(10):
                _db_market_listing(
                    db, _db_market_owner(db), catalog, "20000"
                )

        session = CountingSession(db)
        comparisons = build_market_comparisons(session, targets, (None, False))

    assert len(session.statements) == 1
    assert session.returned_row_counts == [250]
    assert all(comparisons[target.id]["sample_size"] == 10 for target in targets)


@pytest.mark.parametrize(
    ("field", "different_value"),
    [
        pytest.param("condition", "new", id="condition"),
        pytest.param("fuel", "diesel", id="fuel"),
        pytest.param("transmission", "automatic", id="transmission"),
        pytest.param("body_type_id", uuid.UUID(int=2003), id="body-type"),
    ],
)
def test_market_comparison_requires_the_plan_cohort_categories_to_match(
    field, different_value
):
    target = _listing(owner_id=uuid.UUID(int=1000))
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(9)
    ]
    candidates.append(
        _listing(
            owner_id=uuid.UUID(int=10),
            price_amount=Decimal("20000"),
            **{field: different_value},
        )
    )

    assert _compare(target, candidates) is None
