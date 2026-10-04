"""Typed API contracts for listing conversations and messages."""

import re
import unicodedata
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalise_message(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        raise ValueError("Message must not be blank")
    if re.search(r"</?[A-Za-z][^>]*>", value):
        raise ValueError("Message must be plain text")
    if any(unicodedata.category(char) == "Cc" and char not in "\n\t" for char in value):
        raise ValueError("Message contains a control character")
    return value


class ConversationCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: UUID
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = _normalise_message(value)
        if len(value) > 2000:
            raise ValueError("Message must contain at most 2000 characters")
        return value


class ConversationMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = _normalise_message(value)
        if len(value) > 2000:
            raise ValueError("Message must contain at most 2000 characters")
        return value


class ConversationParticipantOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    display_name: str


class ConversationListingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    slug: str


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    body: str
    created_at: datetime
    read_at: datetime | None


class ConversationSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    listing: ConversationListingOut
    buyer_id: UUID
    seller_id: UUID
    participants: list[ConversationParticipantOut]
    last_message: ConversationMessageOut | None
    last_message_at: datetime
    unread_count: int
    blocked_by_me: bool
    is_blocked: bool


class ConversationListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ConversationSummaryOut]


class ConversationDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationSummaryOut
    messages: list[ConversationMessageOut]
    has_more: bool
    next_before_sequence: int | None


class ConversationCreateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationSummaryOut


class ConversationMessageResponseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: ConversationMessageOut


class ConversationActionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
