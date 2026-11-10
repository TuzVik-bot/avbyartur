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

    def execute(self, _statement):
        # Analog rows are tagged with the index of the single compared target.
        return [SimpleNamespace(target_index=0, **vars(listing)) for listing in self.listings]


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


def _stable_market_candidates():
    return [
        _listing(owner_id=uuid.UUID(int=index + 1), price_amount=Decimal("20000"))
        for index in range(10)
    ]


def test_market_comparison_hides_a_price_within_ten_percent_by_default():
    target = _listing(owner_id=uuid.UUID(int=1000), price_amount=Decimal("20500"))

    assert _compare(target, _stable_market_candidates()) is None


def test_market_comparison_labels_a_price_within_ten_percent_in_market_when_opted_in():
    target = _listing(owner_id=uuid.UUID(int=1000), price_amount=Decimal("20500"))

    comparison = build_market_comparisons(
        FakeSession(_stable_market_candidates()),
        [target],
        (None, False),
        include_in_market=True,
    )[target.id]

    assert comparison is not None
    assert comparison["label"] == "in_market"
    assert comparison["median_byn"] == "20000.00"
    assert comparison["sample_size"] == 10
