from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.listing_categories import CategoryCode, ListingCategoryDetailsInput


FeedFormat = Literal["csv", "xml", "api"]
FeedStatus = Literal["active", "disabled"]
ManualConflictPolicy = Literal["review", "feed_wins"]
ImportStatus = Literal["preview", "succeeded", "partial", "failed"]
ImportRowStatus = Literal["preview", "draft", "submitted", "unchanged", "rejected"]

FEED_FIELDS = frozenset({
    "dealer_external_id",
    "category_code", "category_details",
    "make_id", "model_id", "generation_id", "body_type_id", "body_variant_id", "modification_id",
    "manual_make", "manual_model", "title", "year", "mileage_km", "fuel", "transmission", "drive",
    "condition", "color", "customs_status", "technical_condition", "body_condition",
    "exchange", "bargaining", "credit", "leasing", "equipment", "district", "call_hours",
    "damaged", "parts_only", "engine_volume_l", "power_hp", "description", "vin",
    "price_amount", "currency", "region_id", "city_id", "manual_city", "contact_phone",
})

FEED_SCHEMA_FIELDS = [
    {"name": "dealer_external_id", "type": "string", "required": True, "unit": None, "allowed_values": [], "description": "Stable source key, unique within this feed; keep it unchanged across updates."},
    {"name": "category_code", "type": "string", "required": False, "unit": None, "allowed_values": ["cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires"], "description": "Omitted legacy rows are cars. Non-car rows require an explicit category and matching category_details."},
    {"name": "category_details", "type": "object", "required": False, "unit": None, "allowed_values": [], "description": "Validated category-specific object. CSV/XML use a JSON object string with category_code and details."},
    {"name": "make_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog make ID; use manual_make when you do not have a catalog mapping."},
    {"name": "model_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog model ID; use manual_model when you do not have a catalog mapping."},
    {"name": "generation_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog generation ID."},
    {"name": "body_type_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog body type ID."},
    {"name": "body_variant_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog body variant ID."},
    {"name": "modification_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog modification ID."},
    {"name": "manual_make", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Make name for listings without a catalog ID."},
    {"name": "manual_model", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Model name for listings without a catalog ID."},
    {"name": "title", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Listing title, up to 240 characters."},
    {"name": "year", "type": "integer", "required": False, "unit": "year", "allowed_values": [], "description": "Model year from 1886 through 2100."},
    {"name": "mileage_km", "type": "integer", "required": False, "unit": "km", "allowed_values": [], "description": "Odometer reading from 0 through 5000000 km."},
    {"name": "fuel", "type": "string", "required": False, "unit": None, "allowed_values": ["petrol", "diesel", "hybrid", "electric", "lpg", "other"], "description": "Fuel code."},
    {"name": "transmission", "type": "string", "required": False, "unit": None, "allowed_values": ["manual", "automatic", "robot", "cvt", "other"], "description": "Transmission code."},
    {"name": "drive", "type": "string", "required": False, "unit": None, "allowed_values": ["front", "rear", "all", "other"], "description": "Drive type code."},
    {"name": "condition", "type": "string", "required": False, "unit": None, "allowed_values": ["new", "used"], "description": "Vehicle condition code."},
    {"name": "color", "type": "string", "required": False, "unit": None, "allowed_values": ["black", "white", "gray", "silver", "red", "blue", "green", "yellow", "brown", "beige", "orange", "purple", "other"], "description": "Color code."},
    {"name": "customs_status", "type": "string", "required": False, "unit": None, "allowed_values": ["cleared_rb", "eaeu_import", "uncleared", "unknown"], "description": "Customs status code."},
    {"name": "technical_condition", "type": "string", "required": False, "unit": None, "allowed_values": ["good", "needs_repair", "non_operational"], "description": "Technical condition code."},
    {"name": "body_condition", "type": "string", "required": False, "unit": None, "allowed_values": ["good", "minor_damage", "significant_damage", "repaired"], "description": "Body condition code."},
    {"name": "exchange", "type": "boolean", "required": False, "unit": None, "allowed_values": [], "description": "Whether the seller considers an exchange."},
    {"name": "bargaining", "type": "boolean", "required": False, "unit": None, "allowed_values": [], "description": "Whether the price is negotiable."},
    {"name": "credit", "type": "boolean", "required": False, "unit": None, "allowed_values": [], "description": "Whether credit purchase is offered."},
    {"name": "leasing", "type": "boolean", "required": False, "unit": None, "allowed_values": [], "description": "Whether leasing is offered."},
    {"name": "equipment", "type": "array[string]", "required": False, "unit": None, "allowed_values": ["abs", "esp", "airbags", "air_conditioning", "climate_control", "heated_seats", "cruise_control", "parking_sensors", "rear_camera", "leather_seats", "carplay", "android_auto"], "description": "Equipment codes; API uses a JSON array, CSV/XML may use a JSON array or pipe-separated codes."},
    {"name": "district", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "District or local area, up to 120 characters."},
    {"name": "call_hours", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Preferred calling hours, up to 120 characters."},
    {"name": "damaged", "type": "boolean", "required": False, "unit": None, "allowed_values": [], "description": "Whether the vehicle is damaged."},
    {"name": "parts_only", "type": "boolean", "required": False, "unit": None, "allowed_values": [], "description": "Whether the vehicle is sold for parts only."},
    {"name": "engine_volume_l", "type": "decimal", "required": False, "unit": "litres", "allowed_values": [], "description": "Engine capacity in litres, one decimal place."},
    {"name": "power_hp", "type": "integer", "required": False, "unit": "hp", "allowed_values": [], "description": "Engine power from 1 through 3000 hp."},
    {"name": "description", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Listing description, up to 10000 characters."},
    {"name": "vin", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Vehicle VIN, up to 32 characters; treat as sensitive data."},
    {"name": "price_amount", "type": "decimal", "required": False, "unit": "currency units", "allowed_values": [], "description": "Positive price with two decimal places; send with currency."},
    {"name": "currency", "type": "string", "required": False, "unit": None, "allowed_values": ["BYN", "USD"], "description": "Required together with price_amount."},
    {"name": "region_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog region ID."},
    {"name": "city_id", "type": "uuid", "required": False, "unit": None, "allowed_values": [], "description": "Optional catalog city ID."},
    {"name": "manual_city", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "City name when no catalog city ID is supplied."},
    {"name": "contact_phone", "type": "string", "required": False, "unit": None, "allowed_values": [], "description": "Dealer contact number; stored as sensitive listing data."},
]


class DealerFeedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    format: FeedFormat
    field_mapping: dict[str, str] = Field(default_factory=dict, max_length=40)
    manual_conflict_policy: ManualConflictPolicy = "review"
    missing_retirement_enabled: bool = False
    missing_retirement_delay_hours: int = Field(default=168, ge=1, le=8760)

    @model_validator(mode="after")
    def validate_mapping(self):
        if self.format != "api" and self.field_mapping and "dealer_external_id" not in self.field_mapping:
            raise ValueError("field_mapping must include dealer_external_id")
        if any(key not in FEED_FIELDS for key in self.field_mapping):
            raise ValueError("field_mapping contains an unsupported listing field")
        if any(not source.strip() or len(source) > 120 for source in self.field_mapping.values()):
            raise ValueError("field_mapping column names must be non-empty and at most 120 characters")
        return self


class DealerFeedPatch(BaseModel):
    status: FeedStatus | None = None
    manual_conflict_policy: ManualConflictPolicy | None = None
    missing_retirement_enabled: bool | None = None
    missing_retirement_delay_hours: int | None = Field(default=None, ge=1, le=8760)

    @model_validator(mode="after")
    def require_change(self):
        if all(value is None for value in self.model_dump().values()):
            raise ValueError("At least one feed setting must be supplied")
        return self


class DealerFeedOut(BaseModel):
    id: UUID
    name: str
    format: FeedFormat
    status: FeedStatus
    field_mapping: dict[str, str]
    manual_conflict_policy: ManualConflictPolicy
    missing_retirement_enabled: bool
    missing_retirement_delay_hours: int
    api_token_prefix: str | None
    created_at: datetime


class DealerFeedListOut(BaseModel):
    items: list[DealerFeedOut]


class DealerFeedMutationOut(BaseModel):
    feed: DealerFeedOut
    api_token: str | None = None


class DealerFeedTokenOut(BaseModel):
    feed_id: UUID
    api_token: str
    api_token_prefix: str


class DealerFeedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dealer_external_id: str = Field(min_length=1, max_length=120)
    category_code: CategoryCode | None = None
    category_details: ListingCategoryDetailsInput | None = None
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
    fuel: str | None = Field(default=None, max_length=20)
    transmission: str | None = Field(default=None, max_length=20)
    drive: str | None = Field(default=None, max_length=20)
    condition: str | None = Field(default=None, max_length=30)
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
    equipment: list[Literal[
        "abs", "esp", "airbags", "air_conditioning", "climate_control", "heated_seats",
        "cruise_control", "parking_sensors", "rear_camera", "leather_seats", "carplay", "android_auto",
    ]] | None = Field(default=None, max_length=12)
    district: str | None = Field(default=None, max_length=120)
    call_hours: str | None = Field(default=None, max_length=120)
    damaged: bool | None = None
    parts_only: bool | None = None
    engine_volume_l: Decimal | None = Field(default=None, ge=0, le=30, max_digits=4, decimal_places=1)
    power_hp: int | None = Field(default=None, ge=1, le=3000)
    description: str | None = Field(default=None, max_length=10000)
    vin: str | None = Field(default=None, max_length=32)
    price_amount: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    currency: Literal["BYN", "USD"] | None = None
    region_id: UUID | None = None
    city_id: UUID | None = None
    manual_city: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def require_explicit_non_car_details(self) -> "DealerFeedRecord":
        if self.category_code is None:
            if self.category_details is not None:
                raise ValueError("category_code is required with category_details")
            return self
        if self.category_code != "cars":
            if self.category_details is None or self.category_details.category_code != self.category_code:
                raise ValueError("Non-car feed rows require matching category_details")
        elif self.category_details is not None and self.category_details.category_code != "cars":
            raise ValueError("category_details must match category_code")
        return self


class DealerFeedImportRunOut(BaseModel):
    id: UUID
    feed_id: UUID
    status: ImportStatus
    dry_run: bool
    source_filename: str
    total_rows: int
    applied_rows: int
    rejected_rows: int
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class DealerFeedMissingCandidateOut(BaseModel):
    dealer_external_id: str
    listing_id: UUID
    title: str
    status: str
    listing_revision: int
    expected_listing_revision: int | None
    snapshot_digest: str | None
    missing_since: datetime | None
    due_at: datetime | None
    eligible: bool
    reason: str | None


class DealerFeedMissingCandidatesOut(BaseModel):
    items: list[DealerFeedMissingCandidateOut]


class DealerFeedImportOut(BaseModel):
    run: DealerFeedImportRunOut
    missing_candidates: list[DealerFeedMissingCandidateOut] = Field(default_factory=list)


class DealerFeedMissingCandidateConfirmation(BaseModel):
    dealer_external_id: str = Field(min_length=1, max_length=120)
    expected_listing_revision: int = Field(ge=1)
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class DealerFeedMissingCandidatesConfirmRequest(BaseModel):
    items: list[DealerFeedMissingCandidateConfirmation] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_external_ids(self):
        ids = [item.dealer_external_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate external IDs must be unique")
        return self


class DealerFeedMissingCandidatesConfirmOut(BaseModel):
    run: DealerFeedImportRunOut
    paused_external_ids: list[str]


class DealerFeedSchemaFieldOut(BaseModel):
    name: str
    type: str
    required: bool = False
    unit: str | None = None
    allowed_values: list[str] = Field(default_factory=list)
    description: str


class DealerFeedSchemaOut(BaseModel):
    version: str
    formats: list[FeedFormat]
    stable_key: str
    fields: list[DealerFeedSchemaFieldOut]


class DealerFeedImportRowOut(BaseModel):
    id: UUID
    row_number: int
    dealer_external_id: str | None
    listing_id: UUID | None
    status: ImportRowStatus
    action: str | None
    error_code: str | None
    error_message: str | None
    field_errors: dict[str, str]


class DealerFeedImportRowsOut(BaseModel):
    items: list[DealerFeedImportRowOut]


class DealerFeedAPIImportRequest(BaseModel):
    # Rows are validated independently so an invalid row does not discard the
    # import history for otherwise valid rows.
    items: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    dry_run: bool = True
    complete_snapshot: bool = False
