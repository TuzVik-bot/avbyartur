"""Pure saved-search matching helpers used by the notification worker.

The matcher intentionally mirrors the public listing filters and only reads
values already present on a published listing.  It never contacts an external
provider and does not treat an email preference as an email delivery.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.orm import Session

from app.models import Listing, SavedSearch
from app.services import listing_matches_public_search

SAVED_SEARCH_EMAIL_SUBJECT = "Новое объявление по сохранённому поиску"
_SAVED_SEARCH_PRESENTATION_KEYS = frozenset({"page", "page_size", "sort"})


def saved_search_filter_snapshot(filters: Any) -> dict[str, Any] | None:
    """Drop pagination and ordering from current or legacy filter snapshots."""

    if not isinstance(filters, dict):
        return None
    return {
        key: value
        for key, value in filters.items()
        if key not in _SAVED_SEARCH_PRESENTATION_KEYS
    }


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
        or parsed_url.path not in {"/cars", "/cars/"}
        or "\\" in raw_url
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw_url)
    ):
        raise ValueError("invalid_notification_url")

    absolute_url = f"{origin.rstrip('/')}{raw_url}"
    # Collapse line breaks and repeated whitespace before putting listing data
    # into a plain-text message.  The subject is a constant, so it cannot be
    # used for header injection.
    body_text = " ".join(str(payload.get("body") or "Новое объявление").split())
    body_text = body_text[:2000]
    body = f"{body_text}\n\nОткрыть объявление: {absolute_url}"
    return SAVED_SEARCH_EMAIL_SUBJECT, body


def saved_search_digest_email_content(
    payload: dict[str, Any], public_app_url: str, total_count: int
) -> tuple[str, str]:
    """Build a bounded digest email with stable same-origin listing links."""

    origin = str(public_app_url or "").strip()
    try:
        parsed_origin = urlsplit(origin)
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
        try:
            parsed_url = urlsplit(raw_url)
        except ValueError:
            raise ValueError("invalid_notification_url") from None
        if (
            not raw_url.startswith("/")
            or raw_url.startswith("//")
            or parsed_url.scheme
            or parsed_url.netloc
            or parsed_url.fragment
            or "\\" in raw_url
            or any(ord(character) < 0x20 or ord(character) == 0x7F for character in raw_url)
        ):
            raise ValueError("invalid_notification_url")
        title = " ".join(str(item.get("title") or "Новое объявление").split())[:240]
        lines.append(f"{title}\n{origin.rstrip('/')}{raw_url}")
    if safe_total_count > len(listings):
        lines.append(f"Ещё объявлений: {safe_total_count - len(listings)}")
    search_url = str(payload.get("search_url") or "").strip()
    try:
        parsed_search_url = urlsplit(search_url)
    except ValueError:
        raise ValueError("invalid_notification_url") from None
    if (
        not search_url.startswith("/")
        or search_url.startswith("//")
        or parsed_search_url.scheme
        or parsed_search_url.netloc
        or parsed_search_url.username is not None
        or parsed_search_url.password is not None
        or parsed_search_url.path not in {"/cars", "/cars/"}
        or parsed_search_url.fragment
        or "\\" in search_url
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in search_url)
    ):
        raise ValueError("invalid_notification_url")
    lines.extend(("", f"Все результаты поиска: {origin.rstrip('/')}{search_url}"))
    return SAVED_SEARCH_EMAIL_SUBJECT, "\n\n".join(lines)[:12000]


def saved_search_filters(saved_search: SavedSearch) -> dict[str, Any]:
    """Read matcher filters from the canonical URL, including legacy rows."""

    search_url = getattr(saved_search, "search_url", None)
    if not search_url:
        # Small legacy rows and unit-test stubs may only carry the normalized
        # filter snapshot. Real saved searches are canonicalized through the
        # URL path, but retaining this fallback keeps old records matchable.
        return dict(getattr(saved_search, "filters", {}) or {})
    parsed = urlsplit(search_url)
    query = parse_qs(parsed.query, keep_blank_values=False, max_num_fields=64)
    filters: dict[str, Any] = {}
    for key, values in query.items():
        if key in _SAVED_SEARCH_PRESENTATION_KEYS or not values:
            continue
        if key == "equipment":
            filters[key] = values
        else:
            if len(set(values)) > 1:
                raise ValueError(f"Contradictory repeated URL filter: {key}")
            filters[key] = values[0]
    return saved_search_filter_snapshot(filters) or {}


def saved_search_matches(db: Session, saved_search: SavedSearch, listing: Listing) -> bool:
    """Match a saved search with the same filters and visibility as the catalog."""

    return listing_matches_public_search(db, saved_search_filters(saved_search), listing)
