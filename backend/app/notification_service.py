"""Pure saved-search matching helpers used by the notification worker.

The matcher intentionally mirrors the public listing filters and only reads
values already present on a published listing.  It never contacts an external
provider and does not treat an email preference as an email delivery.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CatalogBodyType, Listing, ListingPhoto, SavedSearch
from app.category_search import PATH_CATEGORIES, category_filter_error, detail_filters

SAVED_SEARCH_EMAIL_SUBJECT = "Новое объявление по сохранённому поиску"


def saved_search_email_content(payload: dict[str, Any], public_app_url: str) -> tuple[str, str]:
    """Build a plain-text saved-search email from a trusted same-origin link.

    Saved-search URLs are stored as relative paths.  Re-checking that
    invariant at the email boundary prevents an accidental open redirect if a
    legacy row or a future caller supplies an external URL.
    """

    origin = str(public_app_url or "").strip()
    raw_url = str(payload.get("url") or "").strip()
    try:
        parsed_origin = urlsplit(origin)
        parsed_url = urlsplit(raw_url)
        origin_port = parsed_origin.port
    except ValueError:
        raise ValueError("invalid_notification_url") from None
    if (
        parsed_origin.scheme.lower() != "https"
        or not parsed_origin.netloc
        or not parsed_origin.hostname
        or parsed_origin.username is not None
        or parsed_origin.password is not None
        or parsed_origin.path not in {"", "/"}
        or parsed_origin.query
        or parsed_origin.fragment
        or (origin_port is not None and not 1 <= origin_port <= 65535)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in origin)
    ):
        raise ValueError("invalid_notification_url")
    if (
        not raw_url.startswith("/")
        or raw_url.startswith("//")
        or parsed_url.scheme
        or parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.fragment
        or parsed_url.path.rstrip("/") not in PATH_CATEGORIES
        or "\\" in raw_url
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw_url)
    ):
        raise ValueError("invalid_notification_url")

    category = PATH_CATEGORIES[parsed_url.path.rstrip("/")]
    url_category = parse_qs(parsed_url.query).get("category_code", ["cars"])
    if len(url_category) != 1 or url_category[0] != category:
        raise ValueError("invalid_notification_url")

    absolute_url = f"{origin.rstrip('/')}{raw_url}"
    # Collapse line breaks and repeated whitespace before putting listing data
    # into a plain-text message.  The subject is a constant, so it cannot be
    # used for header injection.
    body_text = " ".join(str(payload.get("body") or "Новое объявление").split())
    body_text = body_text[:2000]
    body = f"{body_text}\n\nОткрыть объявление: {absolute_url}"
    return SAVED_SEARCH_EMAIL_SUBJECT, body


def _as_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _same_identifier(value: Any, actual: Any) -> bool:
    if value is None or actual is None:
        return value is actual
    return str(value).casefold() == str(actual).casefold()


def saved_search_matches(db: Session, saved_search: SavedSearch, listing: Listing) -> bool:
    """Return whether a saved-search filter matches one published listing."""

    filters = dict(saved_search.filters or {})
    category = filters.get("category_code", "cars")
    if category != (listing.category_code or "cars"):
        return False
    if category_filter_error(category, filters):
        return False
    try:
        selected_details = detail_filters(category, filters)
    except ValueError:
        return False
    actual_details = listing.category_details.details if listing.category_details else {}
    if any(actual_details.get(key) != value for key, value in selected_details.items()):
        return False
    if not filters:
        return True

    query = filters.get("q")
    if query:
        needle = str(query).strip().casefold()
        haystack = " ".join(
            value
            for value in (
                listing.title,
                listing.make_name_snapshot,
                listing.model_name_snapshot,
                listing.generation_name_snapshot,
                listing.manual_make,
                listing.manual_model,
                listing.manual_city,
                listing.district,
            )
            if value
        ).casefold()
        if needle not in haystack:
            return False

    identifier_filters = (
        ("make_id", listing.make_id),
        ("model_id", listing.model_id),
        ("generation_id", listing.generation_id),
        ("body_variant_id", listing.body_variant_id),
        ("modification_id", listing.modification_id),
        ("region_id", listing.region_id),
        ("city_id", listing.city_id),
    )
    for key, actual in identifier_filters:
        if key in filters and not _same_identifier(filters[key], actual):
            return False

    if "body_type" in filters:
        expected = str(filters["body_type"]).casefold()
        actual_id = str(listing.body_type_id).casefold() if listing.body_type_id else None
        actual_slug = None
        if listing.body_type_id:
            body_type = db.get(CatalogBodyType, listing.body_type_id)
            actual_slug = body_type.slug.casefold() if body_type else None
        if expected not in {actual_id, actual_slug}:
            return False

    for key, actual in (
        ("fuel", listing.fuel),
        ("transmission", listing.transmission),
        ("drive", listing.drive),
        ("condition", listing.condition),
        ("color", listing.color),
        ("customs_status", listing.customs_status),
        ("technical_condition", listing.technical_condition),
        ("body_condition", listing.body_condition),
    ):
        if key in filters and str(filters[key]).casefold() != str(actual or "").casefold():
            return False

    for key, actual in (
        ("damaged", listing.damaged),
        ("parts_only", listing.parts_only),
        ("exchange", listing.exchange),
        ("bargaining", listing.bargaining),
        ("credit", listing.credit),
        ("leasing", listing.leasing),
    ):
        if key in filters:
            expected = _as_bool(filters[key])
            if expected is None or expected != bool(actual):
                return False

    if "equipment" in filters:
        requested = filters["equipment"]
        if isinstance(requested, str):
            requested = [requested]
        if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
            return False
        if not set(requested).issubset(set(listing.equipment or [])):
            return False

    for key, actual in (("district", listing.district), ("call_hours", listing.call_hours)):
        if key in filters:
            needle = " ".join(str(filters[key]).split()).casefold()
            if not needle or actual is None or needle not in " ".join(actual.split()).casefold():
                return False

    if "has_vin" in filters:
        expected = _as_bool(filters["has_vin"])
        actual = bool((listing.vin or "").strip())
        if expected is None or expected != actual:
            return False

    if "has_photos" in filters:
        expected = _as_bool(filters["has_photos"])
        actual = db.scalar(
            select(ListingPhoto.id)
            .where(ListingPhoto.listing_id == listing.id, ListingPhoto.status == "ready")
            .limit(1)
        ) is not None
        if expected is None or expected != actual:
            return False

    if "seller_type" in filters:
        seller_type = "company" if listing.company_id else "private"
        if str(filters["seller_type"]).casefold() != seller_type:
            return False

    for key, actual in (
        ("year_min", listing.year),
        ("mileage_min", listing.mileage_km),
        ("engine_volume_min", listing.engine_volume_l),
        ("power_min", listing.power_hp),
    ):
        if key in filters:
            expected = _as_decimal(filters[key])
            actual_number = _as_decimal(actual)
            if expected is None or actual_number is None or actual_number < expected:
                return False
    for key, actual in (
        ("year_max", listing.year),
        ("mileage_max", listing.mileage_km),
        ("engine_volume_max", listing.engine_volume_l),
        ("power_max", listing.power_hp),
    ):
        if key in filters:
            expected = _as_decimal(filters[key])
            actual_number = _as_decimal(actual)
            if expected is None or actual_number is None or actual_number > expected:
                return False

    has_price_bound = "price_min" in filters or "price_max" in filters
    if has_price_bound:
        expected_currency = str(filters.get("currency") or "").upper()
        if not expected_currency or listing.currency != expected_currency or listing.price_amount is None:
            return False
        if "price_min" in filters:
            minimum = _as_decimal(filters["price_min"])
            if minimum is None or listing.price_amount < minimum:
                return False
        if "price_max" in filters:
            maximum = _as_decimal(filters["price_max"])
            if maximum is None or listing.price_amount > maximum:
                return False

    # ``page``, ``page_size``, ``sort`` and a currency used only for display
    # control the listing page, not whether an individual listing is a match.
    return True
