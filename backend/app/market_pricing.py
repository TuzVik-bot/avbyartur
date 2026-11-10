"""Comparable public listing prices calculated from current, visible listings."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from statistics import median, quantiles
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import Company, ExchangeRate, Listing, User

MINIMUM_SAMPLE_SIZE = 10
MINIMUM_SELLER_COUNT = 5
MAXIMUM_IQR_RATIO = Decimal("0.5")
# Only the most recently created analogs are compared, so popular models
# cannot turn one listing page into thousands of loaded rows.
MAXIMUM_ANALOGS_PER_LISTING = 500
# Columns read from analog rows; full ORM entities are never loaded.
_ANALOG_COLUMNS = (
    Listing.id,
    Listing.owner_id,
    Listing.company_id,
    Listing.category_code,
    Listing.make_id,
    Listing.model_id,
    Listing.generation_id,
    Listing.body_type_id,
    Listing.condition,
    Listing.fuel,
    Listing.transmission,
    Listing.year,
    Listing.mileage_km,
    Listing.price_amount,
    Listing.currency,
)


def _seller_key(listing: Any) -> tuple[str, UUID]:
    if listing.company_id is not None:
        return "company", listing.company_id
    return "owner", listing.owner_id


def _has_comparison_fields(listing: Listing) -> bool:
    return bool(
        listing.status == "active"
        and listing.category_code == "cars"
        and listing.make_id is not None
        and listing.model_id is not None
        and listing.year is not None
        and listing.mileage_km is not None
        and listing.condition in {"new", "used"}
        and listing.fuel
        and listing.transmission
        and listing.body_type_id is not None
        and listing.price_amount is not None
        and listing.currency in {"BYN", "USD"}
        and not listing.damaged
        and not listing.parts_only
    )


def _cohort_clause(listing: Listing):
    predicates = [
        Listing.make_id == listing.make_id,
        Listing.model_id == listing.model_id,
        Listing.condition == listing.condition,
        Listing.fuel == listing.fuel,
        Listing.transmission == listing.transmission,
        Listing.body_type_id == listing.body_type_id,
    ]
    if listing.generation_id is None:
        predicates.extend((Listing.generation_id.is_(None), Listing.year == listing.year))
    else:
        predicates.extend((
            Listing.generation_id == listing.generation_id,
            Listing.year >= listing.year - 1,
            Listing.year <= listing.year + 1,
        ))
    return and_(*predicates)


def _usd_to_byn(amount: Decimal, rate: ExchangeRate) -> Decimal:
    return amount * rate.official_rate / Decimal(rate.scale)


def _analog_query(index: int, target: Listing):
    mileage_tolerance = max(5000, target.mileage_km * 0.10)
    return (
        select(literal(index).label("target_index"), *_ANALOG_COLUMNS)
        .join(User, Listing.owner_id == User.id)
        .outerjoin(Company, Listing.company_id == Company.id)
        .where(
            Listing.status == "active",
            User.status == "active",
            or_(Listing.company_id.is_(None), Company.status == "approved"),
            Listing.price_amount.is_not(None),
            Listing.currency.in_({"BYN", "USD"}),
            Listing.mileage_km.is_not(None),
            Listing.damaged.is_(False),
            Listing.parts_only.is_(False),
            Listing.id != target.id,
            func.abs(Listing.mileage_km - target.mileage_km) <= mileage_tolerance,
            _cohort_clause(target),
        )
        .order_by(Listing.created_at.desc(), Listing.id.desc())
        .limit(MAXIMUM_ANALOGS_PER_LISTING)
    )


def _load_analogs(db: Session, targets: list[Listing]) -> dict[int, list[Any]]:
    """Load capped analog rows for every target in one UNION ALL statement."""
    queries = [_analog_query(index, target) for index, target in enumerate(targets)]
    statement = queries[0] if len(queries) == 1 else union_all(*queries)
    grouped: dict[int, list[Any]] = {}
    for row in db.execute(statement):
        grouped.setdefault(row.target_index, []).append(row)
    return grouped


def build_market_comparisons(
    db: Session,
    listings: list[Listing],
    rate_info: tuple[ExchangeRate | None, bool],
    *,
    include_in_market: bool = False,
) -> dict[UUID, dict[str, Any] | None]:
    """Return one comparison per supplied listing with a single analog query.

    A price within the +/-10% band is reported as ``in_market`` only when
    ``include_in_market`` is set (owner views); public views omit it.
    """

    output: dict[UUID, dict[str, Any] | None] = {listing.id: None for listing in listings}
    targets = [listing for listing in listings if _has_comparison_fields(listing)]
    if not targets:
        return output

    rate, rate_is_fresh = rate_info
    candidates_by_target = _load_analogs(db, targets)

    calculation_date = datetime.now(timezone.utc).date()
    as_of = datetime.combine(calculation_date, datetime.min.time(), tzinfo=timezone.utc)
    for index, target in enumerate(targets):
        mileage_tolerance = max(5000, target.mileage_km * 0.10)
        target_seller = _seller_key(target)
        target_candidates = [
            candidate for candidate in candidates_by_target.get(index, ())
            if candidate.id != target.id
            and _seller_key(candidate) != target_seller
            and candidate.category_code == "cars"
            and candidate.make_id == target.make_id
            and candidate.model_id == target.model_id
            and candidate.condition == target.condition
            and candidate.fuel == target.fuel
            and candidate.transmission == target.transmission
            and candidate.body_type_id == target.body_type_id
            and candidate.mileage_km is not None
            and (
                (
                    target.generation_id is None
                    and candidate.generation_id is None
                    and candidate.year == target.year
                )
                or (
                    target.generation_id is not None
                    and candidate.generation_id == target.generation_id
                    and abs(candidate.year - target.year) <= 1
                )
            )
            and abs(candidate.mileage_km - target.mileage_km) <= mileage_tolerance
        ]
        if len(target_candidates) < MINIMUM_SAMPLE_SIZE:
            continue

        seller_count = len({_seller_key(candidate) for candidate in target_candidates})
        if seller_count < MINIMUM_SELLER_COUNT:
            continue

        has_usd = target.currency == "USD" or any(
            candidate.currency == "USD" for candidate in target_candidates
        )
        if has_usd and (not rate_is_fresh or rate is None):
            continue

        prices_byn: list[Decimal] = []
        for candidate in target_candidates:
            amount = Decimal(candidate.price_amount)
            if candidate.currency == "USD":
                if not rate_is_fresh or rate is None:
                    prices_byn = []
                    break
                amount = _usd_to_byn(amount, rate)
            prices_byn.append(amount)
        if not prices_byn:
            continue

        median_byn = median(prices_byn)
        first_quartile, _, third_quartile = quantiles(prices_byn, n=4, method="inclusive")
        if median_byn <= 0 or (third_quartile - first_quartile) / median_byn > MAXIMUM_IQR_RATIO:
            continue

        target_price_byn = Decimal(target.price_amount)
        if target.currency == "USD":
            assert rate is not None and rate_is_fresh
            target_price_byn = _usd_to_byn(target_price_byn, rate)
        if target_price_byn <= median_byn * Decimal("0.90"):
            label = "below_market"
        elif target_price_byn >= median_byn * Decimal("1.10"):
            label = "above_market"
        elif include_in_market:
            label = "in_market"
        else:
            continue

        output[target.id] = {
            "label": label,
            "median_byn": str(median_byn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "sample_size": len(target_candidates),
            "seller_count": seller_count,
            "as_of": as_of.isoformat(),
            "rate_date": rate.rate_date if has_usd and rate is not None else None,
        }
    return output
