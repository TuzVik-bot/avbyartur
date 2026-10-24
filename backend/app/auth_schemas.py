from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    is_current: bool


class UserSessionListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UserSessionOut]


class UserSessionRevokedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]


class UserSessionsRevokedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revoked_count: int


class EmailRegistrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(min_length=2, max_length=120)
    accept_terms: Literal[True]
    accept_privacy: Literal[True]
    terms_version: str = Field(min_length=1, max_length=80)
    privacy_version: str = Field(min_length=1, max_length=80)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value):
        if not value.strip():
            raise ValueError("Password must not be blank")
        return value
