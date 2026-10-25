from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.market_schemas import MarketValuationOut
from app.services import latest_listing_exchange_rate
from app.valuation import estimate_market_value

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get(
    "/valuation", response_model=MarketValuationOut, response_model_exclude_unset=True
)
def market_valuation(
    db: Annotated[Session, Depends(get_db)],
    make_id: Annotated[UUID, Query()],
    model_id: Annotated[UUID, Query()],
    year: Annotated[int, Query(ge=1886, le=2100)],
    mileage_km: Annotated[int, Query(ge=0, le=3_000_000)],
    condition: Annotated[str, Query(pattern="^(new|used)$")],
    fuel: Annotated[str, Query(min_length=1, max_length=20)],
    transmission: Annotated[str, Query(min_length=1, max_length=20)],
    body_type_id: Annotated[UUID, Query()],
    generation_id: Annotated[UUID | None, Query()] = None,
) -> dict:
    """Public pre-listing estimate from currently visible car listings."""

    return estimate_market_value(
        db,
        make_id=make_id,
        model_id=model_id,
        generation_id=generation_id,
        year=year,
        mileage_km=mileage_km,
        condition=condition,
        fuel=fuel,
        transmission=transmission,
        body_type_id=body_type_id,
        rate_info=latest_listing_exchange_rate(db),
    )
