from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


Breadcrumb = Literal[
    "listing_detail_loaded",
    "contact_click",
    "contact_reveal_success",
    "internal_chat_opened",
    "api_request_failed",
]
FrontendErrorType = Literal[
    "Error", "TypeError", "RangeError", "ReferenceError", "SyntaxError",
    "NetworkError", "ApiClientError", "ChunkLoadError",
]


class ContactClickEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: UUID
    channel: Literal["phone", "telegram", "viber", "internal_chat"]
    occurred_at: datetime
    dedup_id: UUID

    @field_validator("occurred_at")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class FrontendErrorReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: FrontendErrorType
    release_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
    breadcrumbs: list[Breadcrumb] = Field(default_factory=list, max_length=10)


class AnalyticsEventAccepted(BaseModel):
    accepted: bool
    recorded: bool = True
