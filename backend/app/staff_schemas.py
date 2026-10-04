from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.listing_change_audit import ListingChangeHistoryItemOut

from app.listing_schemas import ListingPaginationOut, ListingPublicOut
from app.schemas import UserOut


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserOut
    csrf_token: str


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]


class ModerationRiskSignalOut(BaseModel):
    """Sanitized, advisory evidence shown to moderators."""

    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "duplicate_vin",
        "similar_photo",
        "repeated_phone",
        "repeated_description",
        "external_link",
        "contact_token",
        "unusually_low_price",
        "high_submission_velocity",
        "configured_stop_word",
        "suspicious_city_change",
        "suspicious_seller_change",
    ]
    severity: Literal["low", "medium", "high"]
    summary: str = Field(min_length=1, max_length=240)
    related_count: int | None = Field(default=None, ge=1)


class ModerationListingOut(ListingPublicOut):
    vin: str | None
    moderation_reason: str | None
    risk_signals: list[ModerationRiskSignalOut] = Field(default_factory=list)


class ModerationListingQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModerationListingOut]
    pagination: ListingPaginationOut


class ModerationListingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing: ModerationListingOut


class ModerationListingHistoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingChangeHistoryItemOut]


class ModerationCompanyQueueItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    slug: str
    unp: str
    address: str
    phone: str
    status: str
    revision: int


class ModerationCompanyActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    slug: str
    status: str
    revision: int
    moderation_reason: str | None


class ModerationCompanyQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModerationCompanyQueueItemOut]


class ModerationCompanyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: ModerationCompanyActionOut


class ModerationReportQueueItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    listing_id: UUID
    category: Literal["fraud", "incorrect_info", "prohibited", "duplicate", "other"]
    comment: str
    status: Literal["open", "resolved"]
    revision: int
    created_at: datetime


class ModerationReportActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal["open", "resolved"]
    revision: int
    resolution: str | None


class ModerationReportQueueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ModerationReportQueueItemOut]


class ModerationReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report: ModerationReportActionOut
