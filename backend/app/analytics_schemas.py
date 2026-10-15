from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


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


class AnalyticsEventAccepted(BaseModel):
    accepted: bool
    recorded: bool = True
