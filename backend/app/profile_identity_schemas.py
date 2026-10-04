"""Request and response contracts for profile identity settings."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PhoneChangeRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=7, max_length=40)


class PhoneChangeConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    old_code: str = Field(pattern=r"^\d{6}$")
    new_code: str = Field(pattern=r"^\d{6}$")


class PhoneChangeAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: Literal[True]
    challenge_id: UUID
    old_phone_masked: str
    new_phone_masked: str
    expires_in_seconds: int = Field(ge=1)


class PhoneChangeConfirmedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changed: Literal[True]


class NotificationPreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_enabled: bool
    email_enabled: bool
    expected_revision: int = Field(ge=0)


class NotificationPreferencesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_enabled: bool
    email_enabled: bool
    revision: int = Field(ge=0)
    email_verified: bool


class NotificationPreferencesEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferences: NotificationPreferencesOut
