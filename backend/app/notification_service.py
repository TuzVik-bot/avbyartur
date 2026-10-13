"""Saved-search notification formatting and catalog matching helpers."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.orm import Session

from app.category_search import PATH_CATEGORIES, category_filter_error, detail_filters
from app.models import Listing, SavedSearch
from app.services import listing_matches_public_search

SAVED_SEARCH_EMAIL_SUBJECT = "Новое объявление по сохранённому поиску"
_NON_MATCHING_FILTERS = frozenset({"page", "page_size", "sort"})
_CATEGORY_DETAIL_FILTERS = frozenset({"details", "subtype", "diameter_in", "width_mm", "season"})


def _validated_public_origin(public_app_url: str):
    origin = str(public_app_url or "").strip()
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        raise ValueError("invalid_notification_url") from None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65535)
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in origin)
    ):
        raise ValueError("invalid_notification_url")
    return origin.rstrip("/")


def _validated_relative_url(raw_url: str) -> Any:
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        raise ValueError("invalid_notification_url") from None
    if (
        not raw_url.startswith("/")
        or raw_url.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or "\\" in raw_url
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw_url)
    ):
        raise ValueError("invalid_notification_url")
    return parsed


def _validate_search_url(raw_url: str):
    parsed = _validated_relative_url(raw_url)
    category = PATH_CATEGORIES.get(parsed.path.rstrip("/"))
    if category is None:
        raise ValueError("invalid_notification_url")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=64)
    except ValueError:
        raise ValueError("invalid_notification_url") from None
    url_categories = query.get("category_code", [category])
    if (
        len(url_categories) != 1
        or url_categories[0].strip().casefold() != category
        or (category != "cars" and "category_code" not in query)
    ):
        raise ValueError("invalid_notification_url")
    return parsed


def saved_search_email_content(payload: dict[str, Any], public_app_url: str) -> tuple[str, str]:
    """Build a plain-text email with a trusted same-origin search link."""

    origin = _validated_public_origin(public_app_url)
    raw_url = str(payload.get("url") or "").strip()
    _validate_search_url(raw_url)
    body_text = " ".join(str(payload.get("body") or "Новое объявление").split())[:2000]
    return SAVED_SEARCH_EMAIL_SUBJECT, f"{body_text}\n\nОткрыть поиск: {origin}{raw_url}"


def saved_search_digest_email_content(
    payload: dict[str, Any], public_app_url: str, total_count: int
) -> tuple[str, str]:
    """Build a bounded digest email with same-origin listing links."""

    origin = _validated_public_origin(public_app_url)
    listings = payload.get("listings")
    if not isinstance(listings, list) or not 1 <= len(listings) <= 20:
        raise ValueError("invalid_notification_batch")
    try:
        safe_total_count = max(1, int(total_count))
    except (TypeError, ValueError, OverflowError):
        raise ValueError("invalid_notification_batch") from None

    lines = [f"Найдено объявлений: {safe_total_count}"]
    for item in listings:
        if not isinstance(item, dict):
            raise ValueError("invalid_notification_batch")
        raw_url = str(item.get("url") or "").strip()
        _validated_relative_url(raw_url)
        title = " ".join(str(item.get("title") or "Новое объявление").split())[:240]
        lines.append(f"{title}\n{origin}{raw_url}")
    if safe_total_count > len(listings):
        lines.append(f"Ещё объявлений: {safe_total_count - len(listings)}")

    search_url = str(payload.get("search_url") or "").strip()
    _validate_search_url(search_url)
    lines.extend(("", f"Все результаты поиска: {origin}{search_url}"))
    return SAVED_SEARCH_EMAIL_SUBJECT, "\n\n".join(lines)[:12000]


def saved_search_filters(saved_search: SavedSearch) -> dict[str, Any]:
    """Read matching filters from a saved URL, with a legacy snapshot fallback."""

    search_url = getattr(saved_search, "search_url", None)
    if not search_url:
        return dict(getattr(saved_search, "filters", {}) or {})
    parsed = urlsplit(search_url)
    try:
        query = parse_qs(parsed.query, keep_blank_values=False, max_num_fields=64)
    except ValueError as exc:
        raise ValueError("invalid_saved_search_filters") from exc
    filters: dict[str, Any] = {}
    for key, values in query.items():
        if key in _NON_MATCHING_FILTERS or not values:
            continue
        if key == "equipment":
            filters[key] = values
        elif len(set(values)) > 1:
            raise ValueError(f"Contradictory repeated URL filter: {key}")
        else:
            value = values[0]
            if key == "details":
                try:
                    value = json.loads(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid_saved_search_filters") from exc
            filters[key] = value
    if "category_code" in filters:
        filters["category_code"] = str(filters["category_code"]).strip().casefold()
    return filters


def saved_search_matches(db: Session, saved_search: SavedSearch, listing: Listing) -> bool:
    """Match catalog filters and category details using public listing semantics."""

    try:
        filters = saved_search_filters(saved_search)
        category = str(filters.get("category_code", "cars")).strip().casefold()
        if category != (listing.category_code or "cars"):
            return False
        if category_filter_error(category, filters):
            return False
        selected_details = detail_filters(category, filters)
    except (TypeError, ValueError):
        return False

    actual_details = listing.category_details.details if listing.category_details else {}
    if any(actual_details.get(key) != value for key, value in selected_details.items()):
        return False

    catalog_filters = {
        key: value
        for key, value in filters.items()
        if key not in _CATEGORY_DETAIL_FILTERS and key not in _NON_MATCHING_FILTERS
    }
    catalog_filters["category_code"] = category
    return listing_matches_public_search(db, catalog_filters, listing)
