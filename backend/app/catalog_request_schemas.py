"""Typed API contracts for catalog intake requests and moderation suggestions."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.catalog_schemas import (
    CatalogModificationSourceOut,
    CatalogModificationSpecsOut,
)


class CatalogRequestCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_listing_revision: int = Field(ge=1)
    manual_modification_name: str | None = Field(default=None, max_length=180)
    note: str | None = Field(default=None, max_length=1200)

    @field_validator("manual_modification_name", "note", mode="before")
    @classmethod
    def trim_optional_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        normalized = " ".join(value.split())
        return normalized or None


class CatalogRequestReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    decision: Literal["resolve", "reject"]
    reason: str = Field(min_length=5, max_length=2000)
    resolved_modification_id: UUID | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: Any) -> Any:
        return " ".join(value.split()) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_decision_fields(self):
        if self.decision == "resolve" and self.resolved_modification_id is None:
            raise ValueError("A matching existing modification is required to resolve a request")
        if self.decision == "reject" and self.resolved_modification_id is not None:
            raise ValueError("A rejected request cannot link a catalog modification")
        return self


class CatalogRequestCatalogNodeOut(BaseModel):
    id: UUID
    name: str
    year_from: int | None = None
    year_to: int | None = None


class CatalogRequestManualParametersOut(BaseModel):
    year: int | None = None
    mileage_km: int | None = None
    engine_volume_l: str | None = None
    power_hp: int | None = None
    fuel: str | None = None
    transmission: str | None = None
    drive: str | None = None


class CatalogRequestSnapshotOut(BaseModel):
    catalog: dict[str, CatalogRequestCatalogNodeOut | None]
    manual_identity: dict[str, str | None]
    manual_parameters: CatalogRequestManualParametersOut


class CatalogRequestCatalogMatchOut(BaseModel):
    id: UUID
    slug: str
    name: str
    make: CatalogRequestCatalogNodeOut
    model: CatalogRequestCatalogNodeOut
    generation: CatalogRequestCatalogNodeOut
    source: CatalogModificationSourceOut | None = None
    specs: CatalogModificationSpecsOut | None = None


class CatalogRequestOut(BaseModel):
    id: UUID
    listing_id: UUID
    listing_revision: int
    status: Literal["pending", "resolved", "rejected"]
    revision: int
    snapshot: CatalogRequestSnapshotOut
    manual_modification_name: str | None
    note: str | None
    resolved_modification: CatalogRequestCatalogMatchOut | None = None
    review_reason: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class CatalogRequestListOut(BaseModel):
    items: list[CatalogRequestOut]


class CatalogRequestPageOut(CatalogRequestListOut):
    total: int
    page: int
    page_size: int


class CatalogRequestEnvelopeOut(BaseModel):
    request: CatalogRequestOut


class CatalogRequestMatchesOut(BaseModel):
    items: list[CatalogRequestCatalogMatchOut]


class CatalogRequestReviewOut(CatalogRequestEnvelopeOut):
    pass


class CatalogRequestStatusQuery(BaseModel):
    status: Literal["pending", "resolved", "rejected"] | None = None
