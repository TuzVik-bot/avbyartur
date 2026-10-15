from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def clean_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Text cannot be empty")
    return value


class DealerReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)

    _clean_text = field_validator("text")(clean_text)


class DealerReviewPatch(DealerReviewInput):
    expected_revision: int = Field(ge=1)


class DealerReviewReportInput(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    _clean_text = field_validator("reason")(clean_text)


class DealerReviewModerationInput(BaseModel):
    expected_revision: int = Field(ge=1)
    status: Literal["published", "rejected", "hidden"]
    reason: str = Field(min_length=1, max_length=1000)

    _clean_reason = field_validator("reason")(clean_text)


class DealerReviewModerationListOut(BaseModel):
    items: list[dict]


class DealerReviewMutationOut(BaseModel):
    review: dict


class DealerReviewReportOut(BaseModel):
    id: UUID
    status: Literal["open", "resolved"]
