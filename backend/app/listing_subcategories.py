"""Stable subcategory slugs stored in the existing category details payload."""

from typing import Literal

from app.listing_categories import CategoryCode

SubcategoryCode = Literal[
    "motorcycle", "scooter", "atv", "snowmobile",
    "road_construction", "municipal", "crane", "forestry", "loader", "lift", "concrete", "tow_truck", "excavator", "other",
    "livestock", "mini", "soil_preparation", "sowing", "post_harvest", "other_harvest", "grain_harvest", "forage_harvest", "vegetable_harvest", "tractor", "crop_care",
    "jet_ski", "boat", "motor", "passenger", "truck",
]

SUBCATEGORY_FIELDS: dict[str, str] = {
    "motorcycles": "vehicle_type",
    "special_equipment": "equipment_type",
    "agricultural_equipment": "equipment_type",
    "watercraft": "watercraft_type",
    "tires": "vehicle_type",
}

SUBCATEGORY_VALUES: dict[str, frozenset[str]] = {
    "motorcycles": frozenset({"motorcycle", "scooter", "atv", "snowmobile"}),
    "special_equipment": frozenset({"road_construction", "municipal", "crane", "forestry", "loader", "lift", "concrete", "tow_truck", "excavator", "other"}),
    "agricultural_equipment": frozenset({"livestock", "mini", "soil_preparation", "sowing", "post_harvest", "other_harvest", "grain_harvest", "forage_harvest", "vegetable_harvest", "tractor", "crop_care", "other"}),
    "watercraft": frozenset({"jet_ski", "boat", "motor", "other"}),
    "tires": frozenset({"passenger", "truck", "motorcycle"}),
}


def subcategory_field(category_code: CategoryCode) -> str | None:
    return SUBCATEGORY_FIELDS.get(category_code)


def subcategory_details_condition(category_code: CategoryCode, subcategory: str):
    """SQL predicate for matching typed subtype data, including its parent category."""

    from app.models import ListingCategoryDetails

    field = subcategory_field(category_code)
    if field is None or subcategory not in SUBCATEGORY_VALUES.get(category_code, frozenset()):
        raise ValueError("Unsupported subcategory filter")
    return (
        (ListingCategoryDetails.category_code == category_code)
        & (ListingCategoryDetails.details[field].as_string() == subcategory)
    )
