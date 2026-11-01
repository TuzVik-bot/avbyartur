from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


ServiceCode = Literal["bump", "highlight", "top", "dealer_package"]
CurrencyCode = Literal["BYN", "USD"]
OrderStatus = Literal["pending", "paid", "failed", "cancelled", "expired"]


class BillingTariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    service_code: ServiceCode
    name: str
    amount: Decimal
    currency: CurrencyCode
    duration_days: int
    listing_quota: int | None
    revision: int


class BillingOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tariff_id: UUID
    listing_id: UUID | None = None
    company_id: UUID | None = None

    @model_validator(mode="after")
    def one_target(self):
        if (self.listing_id is None) == (self.company_id is None):
            raise ValueError("Exactly one of listing_id or company_id is required")
        return self


class BillingOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    listing_id: UUID | None
    company_id: UUID | None
    service_code: ServiceCode
    tariff_code: str
    tariff_revision: int
    amount: Decimal
    currency: CurrencyCode
    duration_days: int
    listing_quota: int | None
    provider: str
    provider_reference: str | None
    status: OrderStatus
    expires_at: datetime
    paid_at: datetime | None
    created_at: datetime


class BillingCheckoutOut(BaseModel):
    order: BillingOrderOut
    checkout_url: str | None


class BillingOrderListOut(BaseModel):
    items: list[BillingOrderOut]
    total: int
    page: int
    page_size: int


class BillingCallbackOut(BaseModel):
    received: bool = True
    duplicate: bool
    order_id: UUID
    status: OrderStatus
