"""Strict request and response shapes for profile and account recovery."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ProfileContactOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    masked: str | None
    verified: bool


class ProfileContactsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: ProfileContactOut
    phone: ProfileContactOut


class ProfileOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    contacts: ProfileContactsOut


class ProfileEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: ProfileOut


class ProfilePatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=2, max_length=120)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_display_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ConsentItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["terms", "privacy"]
    version: str
    accepted_at: datetime
    source: str


class ConsentHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ConsentItemOut]


class EmailRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class TokenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=128)


class EmailVerifiedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: Literal[True]


class RecoveryConfirmInput(TokenInput):
    new_password: str = Field(min_length=12, max_length=256)


class RecoveryConfirmedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]


class AccountDeletionRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE"]


class AccountDeletionRequestedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["requested"]
    revoked_sessions: int = Field(ge=0)
    withdrawn_listings: int = Field(ge=0)
