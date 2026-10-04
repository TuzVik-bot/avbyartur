from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OtpCsrfResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csrf_token: str


class OtpAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: Literal[True]


class OtpRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=7, max_length=40)


class OtpRegistrationRequestInput(OtpRequestInput):
    display_name: str = Field(min_length=2, max_length=120)
    accept_terms: Literal[True]
    accept_privacy: Literal[True]
    # Optional at the transport boundary so the API can return a stable
    # consent-version error instead of silently accepting an omitted version.
    terms_version: str | None = Field(default=None, max_length=80)
    privacy_version: str | None = Field(default=None, max_length=80)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_display_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class OtpVerifyInput(OtpRequestInput):
    code: str = Field(pattern=r"^\d{6}$")


class AuthCapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sms_login: bool
    sms_registration: bool
    email_notifications: bool
    email_verification: bool
    password_recovery: bool
