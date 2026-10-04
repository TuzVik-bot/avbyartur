"""Stable listing categories and validated category-specific characteristics."""

from typing import Any, Literal
from numbers import Real

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


CategoryCode = Literal[
    "cars",
    "trucks",
    "buses",
    "motorcycles",
    "special_equipment",
    "agricultural_equipment",
    "trailers",
    "watercraft",
    "parts",
    "wheels",
    "tires",
]

CATEGORY_CODES: tuple[CategoryCode, ...] = (
    "cars", "trucks", "buses", "motorcycles", "special_equipment",
    "agricultural_equipment", "trailers", "watercraft", "parts", "wheels", "tires",
)


class _Details(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _CarsDetails(_Details):
    pass


class _TrucksDetails(_Details):
    vehicle_type: Literal["truck", "tractor_unit", "van", "other"] | None = None
    payload_kg: int | None = Field(default=None, ge=0)
    gross_weight_kg: int | None = Field(default=None, ge=0)
    axle_configuration: str | None = Field(default=None, max_length=32)


class _BusesDetails(_Details):
    vehicle_type: Literal["bus", "minibus", "coach", "other"] | None = None
    seats: int | None = Field(default=None, ge=0, le=500)
    engine_type: str | None = Field(default=None, max_length=40)


class _MotorcyclesDetails(_Details):
    vehicle_type: Literal["motorcycle", "scooter", "atv", "snowmobile", "other"] | None = None
    engine_volume_cc: int | None = Field(default=None, ge=0, le=10000)
    power_hp: int | None = Field(default=None, ge=0, le=3000)


class _SpecialEquipmentDetails(_Details):
    equipment_type: str | None = Field(default=None, max_length=80)
    operating_hours: int | None = Field(default=None, ge=0)
    weight_kg: int | None = Field(default=None, ge=0)
    payload_kg: int | None = Field(default=None, ge=0)


class _AgriculturalEquipmentDetails(_Details):
    equipment_type: str | None = Field(default=None, max_length=80)
    operating_hours: int | None = Field(default=None, ge=0)
    power_hp: int | None = Field(default=None, ge=0, le=3000)
    working_width_m: float | None = Field(default=None, ge=0, le=100)


class _TrailersDetails(_Details):
    trailer_type: str | None = Field(default=None, max_length=80)
    axles: int | None = Field(default=None, ge=0, le=20)
    payload_kg: int | None = Field(default=None, ge=0)
    gross_weight_kg: int | None = Field(default=None, ge=0)


class _WatercraftDetails(_Details):
    watercraft_type: str | None = Field(default=None, max_length=80)
    length_m: float | None = Field(default=None, ge=0, le=200)
    hull_material: str | None = Field(default=None, max_length=80)
    motor_power_hp: int | None = Field(default=None, ge=0, le=3000)


class _PartsDetails(_Details):
    part_group: str | None = Field(default=None, max_length=120)
    manufacturer: str | None = Field(default=None, max_length=120)
    part_number: str | None = Field(default=None, max_length=120)
    compatibility: str | None = Field(default=None, max_length=500)
    quantity: int | None = Field(default=None, ge=0)


class _WheelsDetails(_Details):
    diameter_in: float | None = Field(default=None, gt=0, le=40)
    width_in: float | None = Field(default=None, gt=0, le=30)
    bolt_holes: int | None = Field(default=None, gt=0, le=12)
    pcd_mm: float | None = Field(default=None, gt=0, le=300)
    offset_et: float | None = Field(default=None, ge=-200, le=200)
    dia_mm: float | None = Field(default=None, ge=0, le=300)
    material: Literal["steel", "alloy", "forged", "other"] | None = None
    quantity: int | None = Field(default=None, ge=0, le=100)


class _TiresDetails(_Details):
    width_mm: int | None = Field(default=None, gt=0, le=1000)
    profile_percent: int | None = Field(default=None, gt=0, le=100)
    diameter_in: float | None = Field(default=None, gt=0, le=40)
    season: Literal["summer", "winter", "all_season"] | None = None
    load_index: int | None = Field(default=None, ge=0, le=1000)
    speed_index: str | None = Field(default=None, max_length=8)
    quantity: int | None = Field(default=None, ge=0, le=100)


_DETAILS_SCHEMAS: dict[str, type[_Details]] = {
    "cars": _CarsDetails,
    "trucks": _TrucksDetails,
    "buses": _BusesDetails,
    "motorcycles": _MotorcyclesDetails,
    "special_equipment": _SpecialEquipmentDetails,
    "agricultural_equipment": _AgriculturalEquipmentDetails,
    "trailers": _TrailersDetails,
    "watercraft": _WatercraftDetails,
    "parts": _PartsDetails,
    "wheels": _WheelsDetails,
    "tires": _TiresDetails,
}

_REQUIRED_SUBMISSION_FIELDS: dict[str, tuple[str, ...]] = {
    "cars": (),
    "trucks": ("vehicle_type",),
    "buses": ("vehicle_type",),
    "motorcycles": ("vehicle_type",),
    "special_equipment": ("equipment_type",),
    "agricultural_equipment": ("equipment_type",),
    "trailers": ("trailer_type",),
    "watercraft": ("watercraft_type",),
    "parts": ("part_group",),
    "wheels": ("diameter_in", "width_in", "bolt_holes", "pcd_mm"),
    "tires": ("width_mm", "profile_percent", "diameter_in", "season"),
}

_POSITIVE_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "wheels": frozenset({"diameter_in", "width_in", "bolt_holes", "pcd_mm"}),
    "tires": frozenset({"width_mm", "profile_percent", "diameter_in"}),
}


class ListingCategoryDetailsInput(BaseModel):
    """A typed, category-specific JSON payload stored separately from a listing."""

    model_config = ConfigDict(extra="forbid")

    category_code: CategoryCode
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_details(self) -> "ListingCategoryDetailsInput":
        schema = _DETAILS_SCHEMAS[self.category_code]
        try:
            self.details = schema.model_validate(self.details).model_dump(exclude_none=True)
        except ValidationError as exc:
            raise ValueError(f"Invalid {self.category_code} category details: {exc}") from exc
        return self


def validate_category_details(category_code: CategoryCode, details: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize a stored JSONB payload for one listing category."""

    return ListingCategoryDetailsInput(
        category_code=category_code,
        details=details or {},
    ).details


def category_submission_errors(category_code: CategoryCode, details: dict[str, Any] | None) -> dict[str, str]:
    """Return missing category-detail errors for a submit attempt, not a draft save."""

    values = details or {}
    errors: dict[str, str] = {}
    for field in _REQUIRED_SUBMISSION_FIELDS[category_code]:
        value = values.get(field)
        if isinstance(value, str):
            present = bool(value.strip())
        else:
            present = value is not None
        if not present:
            errors[f"category_details.{field}"] = "This category characteristic is required"
        elif field in _POSITIVE_REQUIRED_FIELDS.get(category_code, frozenset()) and (
            isinstance(value, bool) or not isinstance(value, Real) or value <= 0
        ):
            errors[f"category_details.{field}"] = "This category characteristic must be greater than zero"
    return errors
