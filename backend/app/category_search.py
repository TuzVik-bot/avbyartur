"""Category-specific search fields shared by listings and notifications."""

import json
from typing import Any

from pydantic import ValidationError

from app.listing_categories import CATEGORY_CODES, validate_category_details

SUBTYPE_FIELD = {
    "trucks": "vehicle_type",
    "buses": "vehicle_type",
    "motorcycles": "vehicle_type",
    "special_equipment": "equipment_type",
    "agricultural_equipment": "equipment_type",
    "trailers": "trailer_type",
    "watercraft": "watercraft_type",
    "parts": "part_group",
}

CATEGORY_PATHS = {code: "/" + code.replace("_", "-") for code in CATEGORY_CODES}
PATH_CATEGORIES = {path: code for code, path in CATEGORY_PATHS.items()}

DETAIL_FILTER_CATEGORIES = {
    "diameter_in": frozenset({"wheels", "tires"}),
    "width_mm": frozenset({"tires"}),
    "season": frozenset({"tires"}),
}


def normalized_details(category_code: str, raw: Any) -> dict[str, Any]:
    """Accept only fields from the category's already published detail contract."""
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ValueError("details must be a JSON object") from exc
    if not isinstance(raw, dict):
        raise ValueError("details must be a JSON object")
    if category_code not in CATEGORY_CODES:
        raise ValueError("Unsupported category_code")
    try:
        return validate_category_details(category_code, raw)
    except (ValidationError, ValueError) as exc:
        raise ValueError("Invalid category details filter") from exc


def category_filter_error(category_code: str, filters: dict) -> str | None:
    if category_code not in CATEGORY_CODES:
        return "Unsupported category_code"
    if filters.get("subtype") is not None and category_code not in SUBTYPE_FIELD:
        return "subtype is unavailable for this category"
    for field, categories in DETAIL_FILTER_CATEGORIES.items():
        if filters.get(field) is not None and category_code not in categories:
            return f"{field} is unavailable for this category"
    return None


def detail_filters(category_code: str, filters: dict) -> dict[str, object]:
    result = {}
    result.update(normalized_details(category_code, filters.get("details")))
    if filters.get("subtype") is not None:
        field = SUBTYPE_FIELD[category_code]
        if field in result and result[field] != filters["subtype"]:
            raise ValueError("Conflicting subtype and details filters")
        result[field] = filters["subtype"]
    for field in DETAIL_FILTER_CATEGORIES:
        if filters.get(field) is not None:
            value = filters[field]
            if field in {"diameter_in", "width_mm"}:
                try:
                    if isinstance(value, bool):
                        raise ValueError
                    value = float(value) if field == "diameter_in" else int(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(f"Invalid {field} filter") from exc
            if field in result and result[field] != value:
                raise ValueError(f"Conflicting {field} and details filters")
            result[field] = value
    return normalized_details(category_code, result)
