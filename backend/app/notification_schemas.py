from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationListingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    url: str


class UserNotificationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    saved_search_id: UUID | None
    conversation_id: UUID | None
    listing_id: UUID | None
    title: str
    body: str
    url: str
    listings: list[NotificationListingOut]
    total_count: int
    read_at: datetime | None
    created_at: datetime


class UserNotificationListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UserNotificationOut]
    unread_count: int


class UserNotificationReadOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
