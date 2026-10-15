"""Validated moderator-managed evidence for public listing details."""

import re
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _safe_text(value: str) -> str:
    value = " ".join(value.split())
    if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", value, re.I):
        raise ValueError("Personal contact details are not allowed")
    if len(re.sub(r"\D", "", value)) >= 9:
        raise ValueError("Personal contact details are not allowed")
    if re.search(r"(?<![A-HJ-NPR-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-HJ-NPR-Z0-9])", value, re.I):
        raise ValueError("Identifiers are not allowed in public evidence")
    return value


class ListingTrustEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=240)
    checked_at: date
    scope: str = Field(min_length=1, max_length=240)

    @field_validator("label", "summary", "source", "scope")
    @classmethod
    def validate_public_text(cls, value: str) -> str:
        cleaned = _safe_text(value)
        if not cleaned:
            raise ValueError("Evidence text must not be empty")
        if re.search(r"\b(seller|продавец|продавца)\b|со слов", cleaned, re.I):
            raise ValueError("Seller statements cannot be recorded as independent verification")
        return cleaned


class ListingTrustEvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str
    summary: str
    source: str
    checked_at: date
    scope: str

