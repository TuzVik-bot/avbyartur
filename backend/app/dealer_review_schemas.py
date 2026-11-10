from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

DealerReviewStatus = Literal["pending", "published", "rejected", "hidden"]
DealerReviewReportStatus = Literal["open", "resolved"]


def _clean_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Text cannot be empty")
    return value


class DealerReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)

    _clean_text = field_validator("text")(_clean_text)


class DealerReviewPatch(DealerReviewInput):
    expected_revision: int = Field(ge=1)


class DealerReviewReportInput(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    _clean_reason = field_validator("reason")(_clean_text)


class DealerReviewModerationInput(BaseModel):
    expected_revision: int = Field(ge=1)
    status: Literal["published", "rejected", "hidden"]
    reason: str = Field(min_length=1, max_length=1000)

    _clean_reason = field_validator("reason")(_clean_text)


class DealerReviewReportResolutionInput(BaseModel):
    resolution: str = Field(min_length=1, max_length=1000)

    _clean_resolution = field_validator("resolution")(_clean_text)


class DealerReviewOut(BaseModel):
    id: UUID
    rating: int
    text: str
    created_at: datetime


class DealerReviewPrivateOut(DealerReviewOut):
    status: DealerReviewStatus
    revision: int
    moderation_reason: str | None


class ModerationDealerReviewOut(DealerReviewPrivateOut):
    company_id: UUID
    author_id: UUID


class DealerReviewsOut(BaseModel):
    items: list[DealerReviewOut]
    count: int
    average_rating: float | None


class DealerReviewResponse(BaseModel):
    review: DealerReviewPrivateOut


class MyDealerReviewResponse(BaseModel):
    review: DealerReviewPrivateOut | None


class ModerationDealerReviewListOut(BaseModel):
    items: list[ModerationDealerReviewOut]


class DealerReviewReportOut(BaseModel):
    id: UUID
    status: DealerReviewReportStatus


class DealerReviewReportQueueItemOut(BaseModel):
    id: UUID
    review_id: UUID
    company_name: str
    review_rating: int
    review_text: str
    reason: str
    status: DealerReviewReportStatus
    created_at: datetime


class DealerReviewReportQueueOut(BaseModel):
    items: list[DealerReviewReportQueueItemOut]


class DealerReviewReportResolutionOut(BaseModel):
    id: UUID
    status: DealerReviewReportStatus
    resolution: str


class DealerReviewReportResolutionResponse(BaseModel):
    report: DealerReviewReportResolutionOut
