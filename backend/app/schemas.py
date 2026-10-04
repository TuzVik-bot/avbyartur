import re
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.listing_categories import CategoryCode, ListingCategoryDetailsInput


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class EmailRegistrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=2, max_length=120)
    accept_terms: Literal[True]
    accept_privacy: Literal[True]
    terms_version: str | None = Field(default=None, max_length=80)
    privacy_version: str | None = Field(default=None, max_length=80)

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_display_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class PriceInput(BaseModel):
    amount: Decimal = Field(gt=0, le=9999999999, decimal_places=2)
    currency: Literal["BYN", "USD"]


class UserOut(BaseModel):
    id: UUID
    email: str | None
    display_name: str
    role: Literal["user", "moderator", "admin"]
    company_id: UUID | None
    company_role: Literal["owner", "admin", "seller", "viewer"] | None = None


class ApiErrorOut(BaseModel):
    code: str
    message: str
    field_errors: dict[str, str]
    request_id: str


class CatalogItemOut(BaseModel):
    id: UUID
    slug: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    make_id: UUID | None = None
    model_id: UUID | None = None
    year_from: int | None = None
    year_to: int | None = None


class ListingForm(BaseModel):
    category_code: CategoryCode = "cars"
    category_details: ListingCategoryDetailsInput | None = None
    seller_type: Literal["private", "company"] | None = None
    make_id: UUID | None = None
    model_id: UUID | None = None
    generation_id: UUID | None = None
    body_type_id: UUID | None = None
    body_variant_id: UUID | None = None
    modification_id: UUID | None = None
    manual_make: str | None = Field(default=None, max_length=180)
    manual_model: str | None = Field(default=None, max_length=180)
    title: str | None = Field(default=None, max_length=240)
    year: int | None = Field(default=None, ge=1886, le=2100)
    mileage_km: int | None = Field(default=None, ge=0, le=5_000_000)
    fuel: Literal["petrol", "diesel", "hybrid", "electric", "lpg", "other"] | None = None
    transmission: Literal["manual", "automatic", "robot", "cvt", "other"] | None = None
    drive: Literal["front", "rear", "all", "other"] | None = None
    condition: Literal["new", "used"] | None = None
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
    equipment: list[
        Literal[
            "abs", "esp", "airbags", "air_conditioning", "climate_control", "heated_seats",
            "cruise_control", "parking_sensors", "rear_camera", "leather_seats", "carplay", "android_auto",
        ]
    ] | None = Field(default=None, max_length=12)
    district: str | None = Field(default=None, max_length=120)
    call_hours: str | None = Field(default=None, max_length=120)
    damaged: bool | None = None
    parts_only: bool | None = None
    engine_volume_l: Decimal | None = Field(default=None, ge=0, le=30, decimal_places=1)
    power_hp: int | None = Field(default=None, ge=1, le=3000)
    description: str | None = Field(default=None, max_length=10000)
    vin: str | None = Field(default=None, max_length=32)
    price: PriceInput | None = None
    region_id: UUID | None = None
    city_id: UUID | None = None
    manual_city: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, min_length=5, max_length=40)

    @model_validator(mode="after")
    def category_details_match_category(self) -> "ListingForm":
        if self.category_details is not None and self.category_code is not None and self.category_details.category_code != self.category_code:
            raise ValueError("category_details.category_code must match category_code")
        return self

    @field_validator("manual_city", mode="before")
    @classmethod
    def normalize_manual_city(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = re.sub(r"\s+", " ", value).strip()
            return cleaned or None
        return value

    @field_validator("district", "call_hours", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            cleaned = re.sub(r"\s+", " ", value).strip()
            return cleaned or None
        return value

    @field_validator("equipment")
    @classmethod
    def unique_equipment_items(cls, value: list[str] | None) -> list[str] | None:
        return list(dict.fromkeys(value)) if value is not None else None

    @field_validator("vin")
    @classmethod
    def clean_vin(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip().upper()
        if cleaned and re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", cleaned) is None:
            raise ValueError("VIN must contain 17 valid characters")
        return cleaned or None

    @field_validator("description")
    @classmethod
    def plain_text_description(cls, value: str | None) -> str | None:
        if value is not None and "<" in value and ">" in value:
            raise ValueError("Description must be plain text")
        return value


class RevisionInput(BaseModel):
    expected_revision: int = Field(ge=1)


class ListingPatch(ListingForm):
    category_code: CategoryCode | None = None
    expected_revision: int = Field(ge=1)
    confirm_category_change: bool = False

    @field_validator("category_code", mode="before")
    @classmethod
    def reject_explicit_null_category_code(cls, value: object) -> object:
        if value is None:
            raise ValueError("category_code cannot be null; omit it to preserve the current category")
        return value


class ModerationInput(RevisionInput):
    reason: str | None = Field(default=None, max_length=2000)


class CompanyModerationInput(BaseModel):
    expected_revision: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2000)


class CompanyClosedHoursDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    closed: Literal[True]


class CompanyOpenHoursDay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    close: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @model_validator(mode="after")
    def close_after_open(self) -> "CompanyOpenHoursDay":
        if self.open >= self.close:
            raise ValueError("Closing time must be later than opening time")
        return self


CompanyHoursDay = CompanyClosedHoursDay | CompanyOpenHoursDay


class CompanyBusinessHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mon: CompanyHoursDay
    tue: CompanyHoursDay
    wed: CompanyHoursDay
    thu: CompanyHoursDay
    fri: CompanyHoursDay
    sat: CompanyHoursDay
    sun: CompanyHoursDay


class CompanyInput(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    unp: str = Field(pattern=r"^\d{9}$")
    address: str = Field(min_length=4, max_length=300)
    phone: str = Field(min_length=5, max_length=40)
    business_hours: CompanyBusinessHours | None = None

    @field_validator("name", "address", "phone", mode="before")
    @classmethod
    def trim_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class CompanyPatchInput(CompanyInput):
    expected_revision: int = Field(ge=1)


class ReportInput(BaseModel):
    category: Literal["fraud", "incorrect_info", "prohibited", "duplicate", "other"]
    comment: str = Field(default="", max_length=2000)


class ReportResolveInput(BaseModel):
    expected_revision: int = Field(ge=1)
    resolution: str = Field(min_length=3, max_length=2000)


class PhotoReorderInput(BaseModel):
    expected_revision: int = Field(ge=1)
    photo_ids: list[UUID] = Field(min_length=1, max_length=30)


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    title: str
    status: str
    revision: int
    category_code: str
    category_details: dict[str, object] = Field(default_factory=dict)
    make: CatalogItemOut | None
    model: CatalogItemOut | None
    generation: CatalogItemOut | None = None
    year: int | None
    mileage_km: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    body_type: str | None = None
    price: dict | None
    region: CatalogItemOut | None = None
    city: CatalogItemOut | None = None
    manual_city: str | None = None
    seller: dict
    created_at: str
    damaged: bool
    parts_only: bool
    description: str = ""
    engine_volume_l: str | None = None
    power_hp: int | None = None
    condition: str | None
    vin: str | None = None
    moderation_reason: str | None = None
    photo_urls: list[str] = Field(default_factory=list)
    photos: list[dict] = Field(default_factory=list)
