from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

from app.market_pricing import build_market_comparisons


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

    def scalars(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(all=lambda: self.listings)


def _compare(target, candidates):
    return build_market_comparisons(FakeSession(candidates), [target], (None, False))[
        target.id
    ]


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
    assert all(comparisons[target.id] is not None for target in targets)
    query = str(session.statements[0])
    assert "listings.category_code =" in query
    assert "listings.status =" in query
    assert "users.status =" in query
    assert "companies.status =" in query


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
