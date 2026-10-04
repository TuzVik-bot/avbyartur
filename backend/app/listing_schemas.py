from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ListingPublicCapabilitiesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guest_contact_reveal_enabled: bool


class ListingCatalogItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slug: str
    name: str
    aliases: list[str]
    make_id: UUID | None = None
    model_id: UUID | None = None
    generation_id: UUID | None = None
    year_from: int | None = None
    year_to: int | None = None


class ListingSellerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["private", "company"]
    id: str
    name: str
    slug: str | None = None


class ListingPriceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: str
    currency: Literal["BYN", "USD"]
    display_byn: str | None
    rate_date: str | None
    display_amount: str | None = None
    display_currency: Literal["BYN", "USD"] | None = None


class ListingPhotoOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    url: str | None
    status: str
    position: int
    is_cover: bool


class ListingModificationSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["Drom"]
    id: str | None
    url: str | None


class ListingModificationSpecsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_code: str | None
    frame_code: str | None
    engine_l: float | None
    power_hp: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    production_period_raw: str | None
    summary_raw: str | None


class ListingModificationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slug: str
    name: str
    aliases: list[str] | None = None
    source: ListingModificationSourceOut | None = None
    specs: ListingModificationSpecsOut | None = None


class ListingPublicOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slug: str
    title: str
    status: str
    revision: int
    category_code: str
    category_details: dict[str, object]
    make: ListingCatalogItemOut | None
    model: ListingCatalogItemOut | None
    generation: ListingCatalogItemOut | None
    year: int | None
    mileage_km: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    body_type: str | None
    body_variant_id: UUID | None
    body_variant: ListingCatalogItemOut | None
    price: ListingPriceOut | None
    region: ListingCatalogItemOut | None
    city: ListingCatalogItemOut | None
    manual_city: str | None
    seller: ListingSellerOut
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
    photos: list[ListingPhotoOut]
    modification: ListingModificationOut | None = None


class ListingOwnerOut(ListingPublicOut):
    vin: str | None = None
    moderation_reason: str | None = None
    contact_phone: str | None = None


class ListingPaginationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    page_size: int
    total: int
    pages: int


class ListingFxOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rate_date: str
    usd_rate: str
    scale: int


class ListingSearchOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingPublicOut]
    pagination: ListingPaginationOut
    fx: ListingFxOut | None = None


class ListingOwnerSearchOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingOwnerOut]
    pagination: ListingPaginationOut


class ListingFavoritesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingPublicOut]


class PhoneRevealOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str


class ListingReportOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: Literal["open"]
    revision: int


class ListingDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing: ListingPublicOut | ListingOwnerOut = Field(union_mode="smart")


class ListingRelatedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingPublicOut]


class ListingAnalyticsPeriodOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str


class ListingAnalyticsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: UUID
    period: ListingAnalyticsPeriodOut
    views: int
    contact_reveals: int
    chats: int


class ListingOwnerDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing: ListingOwnerOut


class FavoriteToggleOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
