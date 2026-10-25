"""Public market value estimate built from current, visible listings.

Unlike ``market_pricing`` badges, which only appear when a listing sits
outside a +-10% band around the cohort median, this module returns the
estimate itself with an explicit confidence level so a seller can price a
car before creating an account or a listing. Small cohorts are reported as
``low`` confidence instead of being hidden; empty ones return ``none``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from statistics import median, quantiles
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import Company, ExchangeRate, Listing, User

HIGH_SAMPLE_SIZE = 10
HIGH_SELLER_COUNT = 5
LOW_SAMPLE_SIZE = 4
LOW_SELLER_COUNT = 3
MAXIMUM_IQR_RATIO = Decimal("0.5")


def _cohort_clause(
    *,
    make_id: UUID,
    model_id: UUID,
    generation_id: UUID | None,
    year: int,
    condition: str,
    fuel: str,
    transmission: str,
    body_type_id: UUID,
):
    predicates = [
        Listing.make_id == make_id,
        Listing.model_id == model_id,
        Listing.condition == condition,
        Listing.fuel == fuel,
        Listing.transmission == transmission,
        Listing.body_type_id == body_type_id,
    ]
    if generation_id is None:
        predicates.extend((Listing.generation_id.is_(None), Listing.year == year))
    else:
        predicates.extend(
            (
                Listing.generation_id == generation_id,
                Listing.year >= year - 1,
                Listing.year <= year + 1,
            )
        )
    return and_(*predicates)


def _usd_to_byn(amount: Decimal, rate: ExchangeRate) -> Decimal:
    return amount * rate.official_rate / Decimal(rate.scale)


def _quantized(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def estimate_market_value(
    db: Session,
    *,
    make_id: UUID,
    model_id: UUID,
    generation_id: UUID | None,
    year: int,
    mileage_km: int,
    condition: str,
    fuel: str,
    transmission: str,
    body_type_id: UUID,
    rate_info: tuple[ExchangeRate | None, bool],
) -> dict[str, Any]:
    rate, rate_is_fresh = rate_info
    as_of = datetime.now(UTC)
    mileage_tolerance = max(5000, mileage_km * Decimal("0.10"))

    candidates = db.scalars(
        select(Listing)
        .join(User, Listing.owner_id == User.id)
        .outerjoin(Company, Listing.company_id == Company.id)
        .where(
            Listing.status == "active",
            User.status == "active",
            or_(Listing.company_id.is_(None), Company.status == "approved"),
            Listing.category_code == "cars",
            Listing.price_amount.is_not(None),
            Listing.currency.in_({"BYN", "USD"}),
            Listing.mileage_km.is_not(None),
            Listing.damaged.is_(False),
            Listing.parts_only.is_(False),
            _cohort_clause(
                make_id=make_id,
                model_id=model_id,
                generation_id=generation_id,
                year=year,
                condition=condition,
                fuel=fuel,
                transmission=transmission,
                body_type_id=body_type_id,
            ),
        )
    ).all()

    mileage_tolerance_int = int(mileage_tolerance)
    candidates = [
        candidate
        for candidate in candidates
        if abs(int(candidate.mileage_km) - mileage_km) <= mileage_tolerance_int
    ]
    seller_count = len(
        {
            ("company", candidate.company_id)
            if candidate.company_id is not None
            else ("owner", candidate.owner_id)
            for candidate in candidates
        }
    )

    sample_size = len(candidates)
    result: dict[str, Any] = {
        "status": "none",
        "median_byn": None,
        "p25_byn": None,
        "p75_byn": None,
        "sample_size": sample_size,
        "seller_count": seller_count,
        "as_of": as_of.isoformat(),
        "rate_date": None,
    }
    if sample_size < LOW_SAMPLE_SIZE or seller_count < LOW_SELLER_COUNT:
        return result

    has_usd = any(candidate.currency == "USD" for candidate in candidates)
    if has_usd and (not rate_is_fresh or rate is None):
        result["status"] = "unsupported_rate"
        return result

    prices_byn: list[Decimal] = []
    for candidate in candidates:
        amount = Decimal(candidate.price_amount)
        if candidate.currency == "USD":
            amount = _usd_to_byn(amount, rate)
        prices_byn.append(amount)

    median_byn = median(prices_byn)
    first_quartile, _, third_quartile = quantiles(prices_byn, n=4, method="inclusive")
    if (
        median_byn <= 0
        or (third_quartile - first_quartile) / median_byn > MAXIMUM_IQR_RATIO
    ):
        return result

    if sample_size >= HIGH_SAMPLE_SIZE and seller_count >= HIGH_SELLER_COUNT:
        status = "high"
    else:
        status = "low"
    result.update(
        {
            "status": status,
            "median_byn": _quantized(median_byn),
            "p25_byn": _quantized(first_quartile),
            "p75_byn": _quantized(third_quartile),
            "rate_date": rate.rate_date if has_usd and rate is not None else None,
        }
    )
    return result
