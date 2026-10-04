from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


SupportedCurrency = Literal["EUR", "USD", "BYN", "RUB", "CNY"]
SupportedEngine = Literal["petrol", "diesel"]
AgeBand = Literal["up_to_3_years", "over_3_to_5_years", "over_5_years"]
_DECIMAL_TEXT_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")
InputDecimalText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=40, pattern=r"^\d+(?:\.\d+)?$"),
]
DecimalText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=80, pattern=r"^\d+(?:\.\d+)?$"),
]


class _CustomsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomsCalculationRequest(_CustomsModel):
    price_amount: InputDecimalText
    currency: SupportedCurrency
    manufacture_date: date
    engine_type: SupportedEngine
    engine_volume_cc: int = Field(ge=1, le=100_000, strict=True)
    personal_use: Literal[True]
    origin_outside_eaeu: Literal[True]

    @field_validator("price_amount")
    @classmethod
    def validate_positive_decimal_text(cls, value: str) -> str:
        if not _DECIMAL_TEXT_PATTERN.fullmatch(value):
            raise ValueError("Enter a finite positive decimal amount")
        try:
            amount = Decimal(value)
        except InvalidOperation:
            raise ValueError("Enter a finite positive decimal amount") from None
        if not amount.is_finite() or amount <= 0 or amount > Decimal("1e18"):
            raise ValueError("Price amount must be positive and no greater than 1000000000000000000")
        return value


class CustomsRateUsed(_CustomsModel):
    currency: SupportedCurrency
    official_rate: DecimalText
    scale: int = Field(ge=1)
    byn_per_unit: DecimalText


class CustomsMetaResponse(_CustomsModel):
    scenario: Literal["private_m1_personal_use_outside_eaeu"]
    supported_currencies: list[SupportedCurrency]
    supported_engines: list[SupportedEngine]
    calculation_available: bool
    unavailable_reason: str | None
    rules_version: str | None
    verified_on: date | None
    sources: list[str]
    scope_notes: list[str]


class CustomsCalculationResponse(_CustomsModel):
    calculation_date: date
    rules_version: str
    age_band: AgeBand
    customs_value_eur: DecimalText
    duty_eur: DecimalText
    duty_byn: DecimalText
    recycling_fee_byn: DecimalText
    customs_fee_byn: DecimalText
    total_byn: DecimalText
    rate_date: date
    rates_used: list[CustomsRateUsed]
    sources: list[str]
    warnings: list[str]
