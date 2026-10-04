from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import CompanyBusinessHours


class PrivateCompanyOut(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    revision: int
    address: str
    business_hours: CompanyBusinessHours | None
    moderation_reason: str | None
    unp: str
    phone: str


class PublicCompanyOut(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    revision: int
    address: str
    business_hours: CompanyBusinessHours | None


class MyCompanyResponse(BaseModel):
    company: PrivateCompanyOut | None


class CompanyMutationResponse(BaseModel):
    company: PrivateCompanyOut


class CompanyPaginationOut(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class DealerDirectoryResponse(BaseModel):
    items: list[PublicCompanyOut]
    pagination: CompanyPaginationOut


class DealerCatalogItemOut(BaseModel):
    id: UUID
    slug: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    make_id: UUID | None = None
    model_id: UUID | None = None
    generation_id: UUID | None = None
    year_from: int | None = None
    year_to: int | None = None


class DealerPriceOut(BaseModel):
    amount: str
    currency: str | None
    display_byn: str | None
    rate_date: str | None


class DealerListingSellerOut(BaseModel):
    type: Literal["company"]
    id: UUID
    name: str
    slug: str


class DealerListingPhotoOut(BaseModel):
    id: UUID
    url: str | None
    status: str
    position: int
    is_cover: bool


class DealerListingSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slug: str
    title: str
    status: Literal["active"]
    revision: int
    category_code: str
    category_details: dict[str, object]
    make: DealerCatalogItemOut | None
    model: DealerCatalogItemOut | None
    generation: DealerCatalogItemOut | None
    year: int | None
    mileage_km: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    body_type: str | None
    body_variant_id: UUID | None
    body_variant: DealerCatalogItemOut | None
    price: DealerPriceOut | None
    region: DealerCatalogItemOut | None
    city: DealerCatalogItemOut | None
    manual_city: str | None
    seller: DealerListingSellerOut
    created_at: datetime
    updated_at: datetime
    damaged: bool
    parts_only: bool
    description: str
    engine_volume_l: str | None
    power_hp: int | None
    condition: str | None
    color: Literal[
        "black", "white", "gray", "silver", "red", "blue", "green", "yellow", "brown", "beige", "orange", "purple", "other",
    ] | None = None
    customs_status: Literal["cleared_rb", "eaeu_import", "uncleared", "unknown"] | None = None
    technical_condition: Literal["good", "needs_repair", "non_operational"] | None = None
    body_condition: Literal["good", "minor_damage", "significant_damage", "repaired"] | None = None
    exchange: bool | None = None
    bargaining: bool | None = None
    credit: bool | None = None
    leasing: bool | None = None
    equipment: list[str] = Field(default_factory=list)
    district: str | None = None
    call_hours: str | None = None
    promotion_badges: list[Literal["bump", "highlight", "top"]] = Field(default_factory=list)
    photo_urls: list[str]
    photos: list[DealerListingPhotoOut]


class DealerListingsPageOut(BaseModel):
    items: list[DealerListingSummaryOut]
    pagination: CompanyPaginationOut


class DealerDetailResponse(BaseModel):
    company: PublicCompanyOut
    listings: DealerListingsPageOut
