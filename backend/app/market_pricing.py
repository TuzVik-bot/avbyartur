"""Comparable public listing prices calculated from current, visible listings."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import median, quantiles
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import and_, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.models import Company, ExchangeRate, Listing, User

MINIMUM_SAMPLE_SIZE = 10
MINIMUM_SELLER_COUNT = 5
MAXIMUM_IQR_RATIO = Decimal("0.5")
MAXIMUM_ANALOGS_PER_TARGET = 100


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


def _candidate_select(target: Listing):
    """Select a bounded, deterministic candidate batch for one target."""

    mileage_tolerance = max(5000, target.mileage_km * 0.10)
    if target.company_id is not None:
        other_seller = or_(
            Listing.company_id.is_(None),
            Listing.company_id != target.company_id,
        )
    else:
        other_seller = or_(
            Listing.company_id.is_not(None),
            Listing.owner_id != target.owner_id,
        )

    return (
        select(
            literal(target.id).label("target_id"),
            Listing.id.label("candidate_id"),
            Listing.owner_id.label("candidate_owner_id"),
            Listing.company_id.label("candidate_company_id"),
            Listing.category_code.label("candidate_category_code"),
            Listing.make_id.label("candidate_make_id"),
            Listing.model_id.label("candidate_model_id"),
            Listing.generation_id.label("candidate_generation_id"),
            Listing.year.label("candidate_year"),
            Listing.mileage_km.label("candidate_mileage_km"),
            Listing.condition.label("candidate_condition"),
            Listing.fuel.label("candidate_fuel"),
            Listing.transmission.label("candidate_transmission"),
            Listing.body_type_id.label("candidate_body_type_id"),
            Listing.price_amount.label("candidate_price_amount"),
            Listing.currency.label("candidate_currency"),
            Listing.status.label("candidate_status"),
            Listing.damaged.label("candidate_damaged"),
            Listing.parts_only.label("candidate_parts_only"),
        )
        .join(User, Listing.owner_id == User.id)
        .outerjoin(Company, Listing.company_id == Company.id)
        .where(
            Listing.category_code == "cars",
            Listing.status == "active",
            User.status == "active",
            or_(Listing.company_id.is_(None), Company.status == "approved"),
            Listing.price_amount.is_not(None),
            Listing.currency.in_({"BYN", "USD"}),
            Listing.mileage_km.is_not(None),
            Listing.damaged.is_(False),
            Listing.parts_only.is_(False),
            Listing.id != target.id,
            other_seller,
            _cohort_clause(target),
            Listing.mileage_km >= target.mileage_km - mileage_tolerance,
            Listing.mileage_km <= target.mileage_km + mileage_tolerance,
        )
        .order_by(Listing.id)
        .limit(MAXIMUM_ANALOGS_PER_TARGET + 1)
    )


def _candidate_from_row(row: Any) -> Any:
    values = row._mapping if hasattr(row, "_mapping") else row
    return SimpleNamespace(
        id=values["candidate_id"],
        owner_id=values["candidate_owner_id"],
        company_id=values["candidate_company_id"],
        category_code=values["candidate_category_code"],
        make_id=values["candidate_make_id"],
        model_id=values["candidate_model_id"],
        generation_id=values["candidate_generation_id"],
        year=values["candidate_year"],
        mileage_km=values["candidate_mileage_km"],
        condition=values["candidate_condition"],
        fuel=values["candidate_fuel"],
        transmission=values["candidate_transmission"],
        body_type_id=values["candidate_body_type_id"],
        price_amount=values["candidate_price_amount"],
        currency=values["candidate_currency"],
        status=values["candidate_status"],
        damaged=values["candidate_damaged"],
        parts_only=values["candidate_parts_only"],
    )


def _market_sample(target: Any, candidate_batch: list[Any], rate_info: tuple[ExchangeRate | None, bool]) -> dict[str, Any] | None:
    if len(candidate_batch) > MAXIMUM_ANALOGS_PER_TARGET:
        return None
    mileage_tolerance = max(5000, target.mileage_km * 0.10)
    target_seller = _seller_key(target)
    target_candidates = [
        candidate for candidate in candidate_batch
        if candidate.id != target.id
        and _seller_key(candidate) != target_seller
        and candidate.category_code == "cars"
        and candidate.status == "active"
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
        and candidate.price_amount is not None
        and candidate.currency in {"BYN", "USD"}
        and not candidate.damaged
        and not candidate.parts_only
    ]
    if len(target_candidates) < MINIMUM_SAMPLE_SIZE:
        return None

    seller_count = len({_seller_key(candidate) for candidate in target_candidates})
    if seller_count < MINIMUM_SELLER_COUNT:
        return None

    rate, rate_is_fresh = rate_info
    has_usd = any(candidate.currency == "USD" for candidate in target_candidates)
    if has_usd and (not rate_is_fresh or rate is None):
        return None

    prices_byn: list[Decimal] = []
    for candidate in target_candidates:
        amount = Decimal(candidate.price_amount)
        if candidate.currency == "USD":
            if not rate_is_fresh or rate is None:
                return None
            amount = _usd_to_byn(amount, rate)
        prices_byn.append(amount)

    median_byn = median(prices_byn)
    first_quartile, _, third_quartile = quantiles(prices_byn, n=4, method="inclusive")
    if median_byn <= 0 or (third_quartile - first_quartile) / median_byn > MAXIMUM_IQR_RATIO:
        return None

    calculation_date = datetime.now(timezone.utc).date()
    as_of = datetime.combine(calculation_date, datetime.min.time(), tzinfo=timezone.utc)
    return {
        "median_byn": median_byn,
        "sample_size": len(target_candidates),
        "seller_count": seller_count,
        "as_of": as_of,
        "rate_date": rate.rate_date if has_usd and rate is not None else None,
    }


def _has_estimate_fields(target: Any) -> bool:
    return bool(
        target.category_code == "cars"
        and target.make_id is not None
        and target.model_id is not None
        and target.year is not None
        and target.mileage_km is not None
        and target.condition in {"new", "used"}
        and target.fuel
        and target.transmission
        and target.body_type_id is not None
        and not target.damaged
        and not target.parts_only
    )


def build_market_comparisons(
    db: Session,
    listings: list[Listing],
    rate_info: tuple[ExchangeRate | None, bool],
) -> dict[UUID, dict[str, Any] | None]:
    """Return one comparison per supplied listing with a single analog query."""

    output: dict[UUID, dict[str, Any] | None] = {listing.id: None for listing in listings}
    targets = [listing for listing in listings if _has_comparison_fields(listing)]
    if not targets:
        return output

    rate, rate_is_fresh = rate_info
    candidate_query = union_all(*(_candidate_select(target) for target in targets))
    candidate_rows = db.execute(candidate_query).all()
    candidates_by_target: dict[UUID, list[Any]] = {target.id: [] for target in targets}
    for row in candidate_rows:
        values = row._mapping if hasattr(row, "_mapping") else row
        candidates_by_target[values["target_id"]].append(_candidate_from_row(values))

    for target in targets:
        stats = _market_sample(target, candidates_by_target[target.id], rate_info)
        if stats is None:
            continue
        if target.currency == "USD" and (not rate_is_fresh or rate is None):
            continue

        median_byn = stats["median_byn"]
        target_price_byn = Decimal(target.price_amount)
        if target.currency == "USD":
            assert rate is not None and rate_is_fresh
            target_price_byn = _usd_to_byn(target_price_byn, rate)
        if target_price_byn <= median_byn * Decimal("0.90"):
            label = "below_market"
        elif target_price_byn >= median_byn * Decimal("1.10"):
            label = "above_market"
        else:
            continue

        output[target.id] = {
            "label": label,
            "median_byn": str(median_byn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "sample_size": stats["sample_size"],
            "seller_count": stats["seller_count"],
            "as_of": stats["as_of"].isoformat(),
            "rate_date": stats["rate_date"],
        }
    return output


def build_market_estimate(
    db: Session,
    target: Any,
    rate_info: tuple[ExchangeRate | None, bool],
) -> dict[str, Any] | None:
    """Return only anonymous aggregate price data for an unpublished car draft."""
    if not _has_estimate_fields(target):
        return None
    rows = db.execute(_candidate_select(target)).all()
    candidates = [_candidate_from_row(row) for row in rows]
    stats = _market_sample(target, candidates, rate_info)
    if stats is None:
        return None
    return {
        "median_byn": str(stats["median_byn"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "sample_size": stats["sample_size"],
        "seller_count": stats["seller_count"],
        "as_of": stats["as_of"].isoformat(),
        "rate_date": stats["rate_date"],
    }
