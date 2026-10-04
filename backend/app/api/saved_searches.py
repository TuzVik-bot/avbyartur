"""Authenticated saved-searches API.

Saved searches only persist a user's search state and notification preference.
There is deliberately no delivery worker in this module: an enabled preference
is a user choice that a later notification implementation can consume.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf
from app.config import get_settings
from app.category_search import PATH_CATEGORIES, category_filter_error, detail_filters
from app.db import get_db
from app.listing_options import LISTING_OPTIONS
from app.models import IdempotencyRecord, SavedSearch, User, UserSession
from app.services import check_revision, consume_rate_limit, fail, lock_owner


router = APIRouter(prefix="/api/v1", tags=["saved-searches"])

_MAX_URL_LENGTH = 2048
_MAX_FILTER_BYTES = 16 * 1024
_MAX_FILTER_KEYS = 64
_MAX_FILTER_DEPTH = 4
_MAX_FILTER_LIST_ITEMS = 50
_ALLOWED_FILTERS = frozenset(
    {
        "q",
        "category_code", "subtype", "details", "diameter_in", "width_mm", "season",
        "make_id",
        "model_id",
        "generation_id",
        "body_variant_id",
        "modification_id",
        "price_min",
        "price_max",
        "currency",
        "year_min",
        "year_max",
        "mileage_min",
        "mileage_max",
        "fuel",
        "transmission",
        "drive",
        "body_type",
        "damaged",
        "parts_only",
        "condition",
        "color",
        "customs_status",
        "technical_condition",
        "body_condition",
        "exchange",
        "bargaining",
        "credit",
        "leasing",
        "equipment",
        "district",
        "call_hours",
        "has_vin",
        "has_photos",
        "engine_volume_min",
        "engine_volume_max",
        "power_min",
        "power_max",
        "region_id",
        "city_id",
        "seller_type",
        "page",
        "page_size",
        "sort",
    }
)
_FILTER_ENUMS = {
    "color": "colors",
    "customs_status": "customs_statuses",
    "technical_condition": "technical_conditions",
    "body_condition": "body_conditions",
}
_FILTER_BOOLEAN_KEYS = frozenset(
    {"exchange", "bargaining", "credit", "leasing", "has_vin", "has_photos"}
)
_FILTER_NUMERIC_BOUNDS = {
    "engine_volume_min": (Decimal("0"), Decimal("30"), False),
    "engine_volume_max": (Decimal("0"), Decimal("30"), False),
    "power_min": (Decimal("1"), Decimal("3000"), True),
    "power_max": (Decimal("1"), Decimal("3000"), True),
}
_FILTER_EQUIPMENT = {item["code"] for item in LISTING_OPTIONS["equipment"]}


def _normalise_name(value: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise ValueError("Name must not be blank")
    return value


def _normalise_url(value: str) -> str:
    """Accept only a relative URL from a known category search surface.

    Keeping this as a relative URL prevents a saved-search link from becoming
    an open redirect if it is later rendered as a button in the account area.
    """

    value = value.strip()
    if not value or len(value) > _MAX_URL_LENGTH:
        raise ValueError("URL must contain 1 to 2048 characters")
    if "\\" in value or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("URL contains a control character")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.username or parsed.password:
        raise ValueError("URL must be a relative category search URL")
    if parsed.fragment:
        raise ValueError("URL fragments are not supported")
    if parsed.path.rstrip("/") not in PATH_CATEGORIES:
        raise ValueError("URL must point to a category search")
    query_values = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=_MAX_FILTER_KEYS)
    unknown_query = sorted(set(query_values) - _ALLOWED_FILTERS)
    if unknown_query:
        raise ValueError(f"Unsupported URL filter: {unknown_query[0]}")
    category = PATH_CATEGORIES[parsed.path.rstrip("/")]
    query_category = query_values.get("category_code", [category])
    if len(query_category) != 1 or query_category[0] != category:
        raise ValueError("URL category_code must match the search path")
    if category != "cars" and "category_code" not in query_values:
        raise ValueError("Non-car search URLs require category_code")
    return value


def _validate_filter_value(value: Any, *, depth: int = 0) -> None:
    if depth > _MAX_FILTER_DEPTH:
        raise ValueError("Filters are nested too deeply")
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, str) and len(value) > 500:
            raise ValueError("Filter values must contain at most 500 characters")
        return
    if isinstance(value, dict):
        if len(value) > _MAX_FILTER_KEYS:
            raise ValueError("Filters contain too many keys")
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("Filter keys must be non-empty strings")
            _validate_filter_value(child, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > _MAX_FILTER_LIST_ITEMS:
            raise ValueError("Filter lists contain too many values")
        for child in value:
            _validate_filter_value(child, depth=depth + 1)
        return
    raise ValueError("Filters must contain JSON values")


def _normalise_filters(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Filters must be an object")
    unknown = sorted(set(value) - _ALLOWED_FILTERS)
    if unknown:
        raise ValueError(f"Unsupported filter: {unknown[0]}")
    _validate_filter_value(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Filters must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > _MAX_FILTER_BYTES:
        raise ValueError("Filters are too large")

    normalized = dict(value)
    category = normalized.get("category_code", "cars")
    if not isinstance(category, str):
        raise ValueError("Unsupported category_code filter")
    error = category_filter_error(category, normalized)
    if error:
        raise ValueError(error)
    try:
        normalized_details = detail_filters(category, normalized)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if "details" in normalized:
        normalized["details"] = normalized_details
    for field, option_group in _FILTER_ENUMS.items():
        if field not in normalized or normalized[field] is None:
            continue
        code = normalized[field]
        supported = {item["code"] for item in LISTING_OPTIONS[option_group]}
        if not isinstance(code, str) or code.strip().casefold() not in supported:
            raise ValueError(f"Unsupported {field} filter")
        normalized[field] = code.strip().casefold()

    for field in _FILTER_BOOLEAN_KEYS:
        if field not in normalized:
            continue
        raw = normalized[field]
        if isinstance(raw, bool):
            continue
        if isinstance(raw, str) and raw.strip().casefold() in {"true", "1", "yes"}:
            normalized[field] = True
        elif isinstance(raw, str) and raw.strip().casefold() in {"false", "0", "no"}:
            normalized[field] = False
        else:
            raise ValueError(f"{field} must be a boolean")

    if "equipment" in normalized:
        requested = normalized["equipment"]
        if isinstance(requested, str):
            requested = [requested]
        if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
            raise ValueError("equipment must be a list of supported codes")
        codes = [item.strip().casefold() for item in requested]
        if any(code not in _FILTER_EQUIPMENT for code in codes):
            raise ValueError("Unsupported equipment filter")
        normalized["equipment"] = list(dict.fromkeys(codes))

    for field, (minimum, maximum, integer_only) in _FILTER_NUMERIC_BOUNDS.items():
        if field not in normalized:
            continue
        raw = normalized[field]
        if isinstance(raw, bool):
            raise ValueError(f"{field} must be numeric")
        try:
            number = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"{field} must be numeric") from None
        if not number.is_finite() or number < minimum or number > maximum:
            raise ValueError(f"{field} is outside the supported range")
        if integer_only and number != number.to_integral_value():
            raise ValueError(f"{field} must be an integer")
        normalized[field] = int(number) if integer_only or number == number.to_integral_value() else float(number)

    for field in ("district", "call_hours"):
        if field not in normalized:
            continue
        raw = normalized[field]
        if not isinstance(raw, str):
            raise ValueError(f"{field} must be text")
        normalized[field] = " ".join(raw.split())[:120]

    return normalized


def _validate_category_pair(url: str, filters: dict[str, Any]) -> None:
    category = PATH_CATEGORIES[urlsplit(url).path.rstrip("/")]
    if filters.get("category_code", "cars") != category:
        raise ValueError("Saved-search category must match its URL")
    query = parse_qs(urlsplit(url).query)
    for field in ("category_code", "subtype", "season"):
        if field in query and str(filters.get(field, "")) != query[field][0]:
            raise ValueError(f"Saved-search {field} must match its URL")
    detail_keys = {"details", "subtype", "diameter_in", "width_mm", "season"}
    if detail_keys.intersection(query) or detail_keys.intersection(filters):
        url_details = {field: query[field][0] for field in detail_keys if field in query}
        if detail_filters(category, url_details) != detail_filters(category, filters):
            raise ValueError("Saved-search details must match its URL")


def _validate_notification(enabled: bool, channel: str | None) -> None:
    if enabled and channel is None:
        fail(
            422,
            "validation_error",
            "Notification settings are invalid",
            {"notification_channel": "Choose a channel when notifications are enabled"},
        )


class SavedSearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=_MAX_URL_LENGTH)
    filters: dict[str, Any] = Field(default_factory=dict)
    notifications_enabled: bool = False
    notification_channel: Literal["email", "web"] | None = None
    notification_frequency: Literal["instant", "daily", "weekly"] = "daily"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _normalise_name(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _normalise_url(value)

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _normalise_filters(value)

class SavedSearchPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=1, max_length=_MAX_URL_LENGTH)
    filters: dict[str, Any] | None = None
    status: Literal["active", "paused"] | None = None
    notifications_enabled: bool | None = None
    notification_channel: Literal["email", "web"] | None = None
    notification_frequency: Literal["instant", "daily", "weekly"] | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _normalise_name(value) if value is not None else None

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _normalise_url(value) if value is not None else None

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return _normalise_filters(value) if value is not None else None


class SavedSearchActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int | None = Field(default=None, ge=1)


class SavedSearchNotificationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    channel: Literal["email", "web"] | None
    frequency: Literal["instant", "daily", "weekly"]


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    url: str
    filters: dict[str, Any]
    status: Literal["active", "paused"]
    revision: int
    notifications_enabled: bool
    notification_channel: Literal["email", "web"] | None
    notification_frequency: Literal["instant", "daily", "weekly"]
    notification: SavedSearchNotificationOut
    created_at: datetime
    updated_at: datetime


class SavedSearchListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SavedSearchOut]


class SavedSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_search: SavedSearchOut


class SavedSearchDeleteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]


def _serialize(saved_search: SavedSearch) -> dict[str, Any]:
    return {
        "id": saved_search.id,
        "name": saved_search.name,
        "url": saved_search.search_url,
        "filters": dict(saved_search.filters or {}),
        "status": saved_search.status,
        "revision": saved_search.revision,
        "notifications_enabled": saved_search.notifications_enabled,
        "notification_channel": saved_search.notification_channel,
        "notification_frequency": saved_search.notification_frequency,
        "notification": {
            "enabled": saved_search.notifications_enabled,
            "channel": saved_search.notification_channel,
            "frequency": saved_search.notification_frequency,
        },
        "created_at": saved_search.created_at,
        "updated_at": saved_search.updated_at or saved_search.created_at,
    }


def _owned_saved_search(db: Session, saved_search_id: UUID, user: User, *, lock: bool = False) -> SavedSearch:
    query = select(SavedSearch).where(SavedSearch.id == saved_search_id)
    if lock:
        query = query.with_for_update()
    saved_search = db.scalar(query)
    if saved_search is None or saved_search.user_id != user.id:
        # Do not reveal whether another account owns this resource.
        fail(404, "not_found", "Saved search not found")
    return saved_search


def _mutation_limit(db: Session, user: User) -> None:
    settings = get_settings()
    consume_rate_limit(
        db,
        "saved-search-mutation",
        str(user.id),
        settings.saved_search_mutations_per_hour,
        timedelta(hours=1),
    )


def _check_revision(saved_search: SavedSearch, expected_revision: int | None) -> None:
    if expected_revision is not None:
        check_revision(saved_search, expected_revision, "Saved search")


@router.get("/me/saved-searches", response_model=SavedSearchListOut)
def list_saved_searches(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    rows = db.scalars(
        select(SavedSearch)
        .where(SavedSearch.user_id == user.id)
        .order_by(SavedSearch.created_at.desc(), SavedSearch.id.desc())
        # A lowered creation quota must not hide searches the owner already
        # saved. The administrative override itself is capped at 10,000.
        .limit(10000)
    ).all()
    return {"items": [_serialize(row) for row in rows]}


@router.post(
    "/me/saved-searches",
    response_model=SavedSearchResponse,
    response_model_exclude_unset=True,
)
def create_saved_search(
    payload: SavedSearchCreate,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    del csrf
    if not idempotency_key or not idempotency_key.strip() or len(idempotency_key.strip()) > 120 or any(ord(c) < 0x20 for c in idempotency_key):
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    idempotency_key = idempotency_key.strip()

    # Serialize creates per owner so both the total limit and idempotency
    # lookup remain deterministic under concurrent requests.
    lock_owner(db, user.id)
    prior = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == user.id,
            IdempotencyRecord.scope == "saved-search.create",
            IdempotencyRecord.key == idempotency_key,
        )
    )
    if prior is not None:
        saved_search = db.get(SavedSearch, prior.resource_id)
        if saved_search is None:
            fail(409, "idempotency_resource_missing", "The idempotent saved search no longer exists")
        return {"saved_search": _serialize(saved_search)}

    _mutation_limit(db, user)
    lock_owner(db, user.id)
    prior = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == user.id,
            IdempotencyRecord.scope == "saved-search.create",
            IdempotencyRecord.key == idempotency_key,
        )
    )
    if prior is not None:
        saved_search = db.get(SavedSearch, prior.resource_id)
        if saved_search is None:
            fail(409, "idempotency_resource_missing", "The idempotent saved search no longer exists")
        return {"saved_search": _serialize(saved_search)}

    current_count = int(db.scalar(select(func.count(SavedSearch.id)).where(SavedSearch.user_id == user.id)) or 0)
    from app.runtime_settings import runtime_limit

    if current_count >= runtime_limit(db, "saved_search_limit", fallback=get_settings().saved_search_limit):
        fail(409, "saved_search_limit", "Saved search limit reached")

    try:
        _validate_category_pair(payload.url, payload.filters)
    except ValueError as exc:
        fail(422, "invalid_category_filter", str(exc))
    _validate_notification(payload.notifications_enabled, payload.notification_channel)
    saved_search = SavedSearch(
        user_id=user.id,
        name=payload.name,
        search_url=payload.url,
        filters=payload.filters,
        status="active",
        revision=1,
        notifications_enabled=payload.notifications_enabled,
        notification_channel=payload.notification_channel,
        notification_frequency=payload.notification_frequency,
    )
    db.add(saved_search)
    db.flush()
    db.add(
        IdempotencyRecord(
            actor_id=user.id,
            scope="saved-search.create",
            key=idempotency_key,
            resource_id=saved_search.id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.actor_id == user.id,
                IdempotencyRecord.scope == "saved-search.create",
                IdempotencyRecord.key == idempotency_key,
            )
        )
        if prior is None:
            raise
        saved_search = db.get(SavedSearch, prior.resource_id)
        if saved_search is None:
            fail(409, "idempotency_resource_missing", "The idempotent saved search no longer exists")
    db.refresh(saved_search)
    return {"saved_search": _serialize(saved_search)}


@router.patch(
    "/me/saved-searches/{saved_search_id}",
    response_model=SavedSearchResponse,
    response_model_exclude_unset=True,
)
def update_saved_search(
    saved_search_id: UUID,
    payload: SavedSearchPatch,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del csrf
    values = payload.model_dump(exclude_unset=True)
    expected_revision = values.pop("expected_revision", None)
    if not values:
        fail(422, "empty_update", "At least one saved search field is required")
    _mutation_limit(db, user)
    saved_search = _owned_saved_search(db, saved_search_id, user, lock=True)
    _check_revision(saved_search, expected_revision)

    try:
        _validate_category_pair(values.get("url", saved_search.search_url), values.get("filters", saved_search.filters or {}))
    except ValueError as exc:
        fail(422, "invalid_category_filter", str(exc))

    merged_enabled = values.get("notifications_enabled", saved_search.notifications_enabled)
    merged_channel = values.get("notification_channel", saved_search.notification_channel)
    _validate_notification(merged_enabled, merged_channel)
    field_map = {"url": "search_url"}
    for field, value in values.items():
        setattr(saved_search, field_map.get(field, field), value)
    saved_search.revision += 1
    db.commit()
    db.refresh(saved_search)
    return {"saved_search": _serialize(saved_search)}


@router.post(
    "/me/saved-searches/{saved_search_id}/pause",
    response_model=SavedSearchResponse,
    response_model_exclude_unset=True,
)
def pause_saved_search(
    saved_search_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    payload: SavedSearchActionInput | None = None,
) -> dict[str, Any]:
    return _set_status(saved_search_id, payload, "paused", user, db, csrf)


@router.post(
    "/me/saved-searches/{saved_search_id}/resume",
    response_model=SavedSearchResponse,
    response_model_exclude_unset=True,
)
def resume_saved_search(
    saved_search_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    payload: SavedSearchActionInput | None = None,
) -> dict[str, Any]:
    return _set_status(saved_search_id, payload, "active", user, db, csrf)


def _set_status(
    saved_search_id: UUID,
    payload: SavedSearchActionInput | None,
    status: Literal["active", "paused"],
    user: User,
    db: Session,
    csrf: UserSession,
) -> dict[str, Any]:
    del csrf
    _mutation_limit(db, user)
    saved_search = _owned_saved_search(db, saved_search_id, user, lock=True)
    _check_revision(saved_search, payload.expected_revision if payload else None)
    if saved_search.status != status:
        saved_search.status = status
        saved_search.revision += 1
        db.commit()
        db.refresh(saved_search)
    return {"saved_search": _serialize(saved_search)}


@router.delete(
    "/me/saved-searches/{saved_search_id}",
    response_model=SavedSearchDeleteOut,
)
def delete_saved_search(
    saved_search_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    del csrf
    _mutation_limit(db, user)
    saved_search = _owned_saved_search(db, saved_search_id, user, lock=True)
    db.delete(saved_search)
    db.commit()
    return {"ok": True}
