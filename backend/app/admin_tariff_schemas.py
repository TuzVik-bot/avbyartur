"""Owner-managed commerce tariff input and response contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictInt, field_validator, model_validator

ServiceCode = Literal["bump", "highlight", "top", "dealer_package"]
CurrencyCode = Literal["BYN", "USD"]
TariffStatus = Literal["active", "disabled"]


class AdminTariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    code: str
    service_code: ServiceCode
    name: str
    amount: Decimal
    currency: CurrencyCode
    duration_days: int
    listing_quota: int | None
    status: TariffStatus
    revision: int
    created_at: datetime
    updated_at: datetime


class AdminTariffListOut(BaseModel):
    items: list[AdminTariffOut]
    total: int
    page: int
    page_size: int


class AdminTariffCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
    service_code: ServiceCode
    name: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    currency: CurrencyCode
    duration_days: StrictInt = Field(ge=1, le=365)
    listing_quota: StrictInt | None = Field(default=None, ge=1, le=10000)
    status: TariffStatus = "disabled"
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["CREATE_TARIFF"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("amount", mode="before")
    @classmethod
    def exact_decimal_input(cls, value: object) -> object:
        if isinstance(value, float) or isinstance(value, bool):
            raise ValueError("Amount must be an exact decimal string")
        return value

    @field_validator("name", "reason")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A non-empty value is required")
        return value

    @model_validator(mode="after")
    def validate_quota_for_service(self):
        if self.service_code != "dealer_package" and self.listing_quota is not None:
            raise ValueError("Listing quota is only available for dealer packages")
        if self.service_code == "dealer_package" and self.status == "active" and self.listing_quota is None:
            raise ValueError("An active dealer package requires a listing quota")
        return self


class AdminTariffUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    amount: Decimal = Field(gt=Decimal("0"), max_digits=12, decimal_places=2)
    currency: CurrencyCode
    duration_days: StrictInt = Field(ge=1, le=365)
    listing_quota: StrictInt | None = Field(ge=1, le=10000)
    status: TariffStatus
    expected_revision: StrictInt = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["UPDATE_TARIFF"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("amount", mode="before")
    @classmethod
    def exact_decimal_input(cls, value: object) -> object:
        if isinstance(value, float) or isinstance(value, bool):
            raise ValueError("Amount must be an exact decimal string")
        return value

    @field_validator("name", "reason")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A non-empty value is required")
        return value


class AdminTariffDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: StrictInt = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["DELETE_TARIFF"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A non-empty reason is required")
        return value


class AdminTariffChangeOut(BaseModel):
    tariff: AdminTariffOut
    changed: bool = True


class AdminTariffDeleteOut(BaseModel):
    deleted: Literal[True]
