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
        self.query_count = 0

    def scalars(self, _statement):
        self.query_count += 1
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


def test_market_comparison_hides_sample_with_iqr_over_half_the_median():
    target = _listing(owner_id=uuid.UUID(int=1000))
    prices = [Decimal("10000")] * 6 + [Decimal("30000")] * 4
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=price)
        for index, price in enumerate(prices)
    ]

    assert _compare(target, candidates) is None


def test_market_comparison_reports_robust_above_market_median_in_one_batch_query():
    target = _listing(
        owner_id=uuid.UUID(int=1000), price_amount=Decimal("24000")
    )
    candidates = [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(10)
    ]
    candidates.append(
        _listing(owner_id=uuid.UUID(int=11), year=None, price_amount=Decimal("20000"))
    )
    session = FakeSession(candidates)

    result = build_market_comparisons(session, [target], (None, False))[target.id]

    assert result is not None
    assert result["label"] == "above_market"
    assert result["median_byn"] == "20000.00"
    assert result["sample_size"] == 10
    assert result["seller_count"] == 10
    assert result["rate_date"] is None
    assert session.query_count == 1


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
