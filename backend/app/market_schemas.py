from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MarketValuationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["none", "unsupported_rate", "low", "high"]
    median_byn: str | None
    p25_byn: str | None
    p75_byn: str | None
    sample_size: int
    seller_count: int
    as_of: datetime
    rate_date: str | None


class MarketPriceEstimateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seller_type: Literal["private", "company"]
    make_id: UUID
    model_id: UUID
    generation_id: UUID | None = None
    body_type_id: UUID
    year: int = Field(ge=1886, le=2100)
    mileage_km: int = Field(ge=0, le=3_000_000)
    condition: Literal["new", "used"]
    fuel: str = Field(min_length=1, max_length=20)
    transmission: str = Field(min_length=1, max_length=20)
    damaged: bool = False
    parts_only: bool = False


class MarketPriceEstimateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    median_byn: str | None
    sample_size: int
    seller_count: int
    as_of: datetime | None
    rate_date: str | None
