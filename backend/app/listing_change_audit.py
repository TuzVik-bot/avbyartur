"""Sanitized, immutable listing-edit snapshots for private moderation history."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Listing,
    ListingPhoto,
    LocationCity,
    LocationRegion,
)

LISTING_EDIT_ACTION = "listing_edited"
LISTING_EDIT_REASON = "seller_edit"
LISTING_PHOTO_EDIT_REASON = "seller_photo_edit"
_DESCRIPTION_FIELDS = frozenset({"description"})
_CONTACT_FIELDS = frozenset({"contact_phone"})
_VIN_FIELDS = frozenset({"vin"})
_REFERENCE_MODELS: dict[str, type] = {
    "make_id": CatalogMake,
    "model_id": CatalogModel,
    "generation_id": CatalogGeneration,
    "body_type_id": CatalogBodyType,
    "body_variant_id": CatalogBodyVariant,
    "modification_id": CatalogModification,
    "region_id": LocationRegion,
    "city_id": LocationCity,
}
_TRACKED_FIELDS = (
    "make_id",
    "model_id",
    "generation_id",
    "body_type_id",
    "body_variant_id",
    "modification_id",
    "manual_make",
    "manual_model",
    "title",
    "year",
    "mileage_km",
    "fuel",
    "transmission",
    "drive",
    "condition",
    "damaged",
    "parts_only",
    "engine_volume_l",
    "power_hp",
    "description",
    "vin",
    "price",
    "region_id",
    "city_id",
    "manual_city",
    "contact_phone",
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
    "seller_type",
)
_ALLOWED_HISTORY_FIELDS = frozenset((*_TRACKED_FIELDS, "photos"))
_PHONE_DIGITS_RE = re.compile(r"\D+")
_VIN_CHARS_RE = re.compile(r"[^A-Z0-9]")
_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d().\s-]{6,}\d)(?!\w)")
_HANDLE_RE = re.compile(r"(?<![\w.])@[a-z0-9_]{4,}", re.IGNORECASE)
_URL_RE = re.compile(r"(?i)(?:https?://|www\.)\S+")


class ListingFieldChangeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    before: Any
    after: Any


class ListingChangeHistoryItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int
    reason: str
    from_status: str | None
    to_status: str | None
    changed_field_keys: list[str]
    changes: list[ListingFieldChangeOut]
    created_at: datetime


@dataclass(frozen=True)
class ListingEditSnapshot:
    fields: dict[str, Any]
    comparison_fingerprints: dict[str, str]


def _masked_phone(value: object) -> str | None:
    if value is None:
        return None
    digits = _PHONE_DIGITS_RE.sub("", str(value))
    if not digits:
        return "••••"
    return f"••••{digits[-4:]}"


def _masked_vin(value: object) -> str | None:
    if value is None:
        return None
    normalized = _VIN_CHARS_RE.sub("", str(value).upper())
    if not normalized:
        return "••••"
    return f"••••••••••••{normalized[-4:]}"


def _redacted_description(value: object) -> dict[str, object]:
    description = str(value or "")
    return {"present": bool(description), "length": len(description)}


def _safe_text(value: object, *, limit: int = 240) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", str(value)).strip()
    cleaned = _EMAIL_RE.sub("[email]", cleaned)
    cleaned = _PHONE_RE.sub("[phone]", cleaned)
    cleaned = _HANDLE_RE.sub("[account]", cleaned)
    cleaned = _URL_RE.sub("[link]", cleaned)
    return cleaned[:limit]


def _reference_snapshot(db: Session, field: str, value: UUID | None, listing: Listing) -> dict[str, str] | None:
    if value is None:
        return None
    if field == "make_id":
        name = listing.make_name_snapshot
    elif field == "model_id":
        name = listing.model_name_snapshot
    elif field == "generation_id":
        name = listing.generation_name_snapshot
    else:
        model = _REFERENCE_MODELS[field]
        row = db.get(model, value)
        name = getattr(row, "name", None) if row is not None else None
    return {"id": str(value), "name": _safe_text(name) or ""}


def _fingerprint(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def snapshot_listing_fields(db: Session, listing: Listing) -> ListingEditSnapshot:
    """Return JSON-ready field snapshots with contact and VIN values masked."""
    result: dict[str, Any] = {}
    comparison_values: dict[str, Any] = {}
    for field in _TRACKED_FIELDS:
        if field == "seller_type":
            comparison_values[field] = str(listing.company_id) if listing.company_id is not None else "private"
            result[field] = (
                {"type": "company", "company_id": str(listing.company_id)}
                if listing.company_id is not None
                else {"type": "private", "company_id": None}
            )
        elif field == "price":
            amount = listing.price_amount
            comparison_values[field] = {"amount": amount, "currency": listing.currency}
            result[field] = (
                {"amount": f"{Decimal(amount):.2f}", "currency": listing.currency}
                if amount is not None
                else None
            )
        elif field in _DESCRIPTION_FIELDS:
            comparison_values[field] = listing.description or ""
            result[field] = _redacted_description(listing.description)
        elif field in _CONTACT_FIELDS:
            comparison_values[field] = listing.contact_phone or ""
            result[field] = _masked_phone(listing.contact_phone)
        elif field in _VIN_FIELDS:
            comparison_values[field] = listing.vin or ""
            result[field] = _masked_vin(listing.vin)
        elif field in _REFERENCE_MODELS:
            reference_id = getattr(listing, field)
            comparison_values[field] = str(reference_id) if reference_id is not None else None
            result[field] = _reference_snapshot(db, field, reference_id, listing)
        elif field == "manual_city":
            comparison_values[field] = listing.manual_city
            result[field] = _safe_text(listing.manual_city)
        elif field in {"title", "manual_make", "manual_model", "district", "call_hours"}:
            comparison_values[field] = getattr(listing, field)
            result[field] = _safe_text(getattr(listing, field))
        elif field == "equipment":
            value = getattr(listing, field)
            comparison_values[field] = value
            result[field] = list(value) if value is not None else None
        else:
            value = getattr(listing, field)
            comparison_values[field] = value
            if isinstance(value, Decimal):
                value = str(value)
            elif isinstance(value, UUID):
                value = str(value)
            result[field] = value
    return ListingEditSnapshot(
        fields=result,
        comparison_fingerprints={field: _fingerprint(value) for field, value in comparison_values.items()},
    )


def _field_changes(before: ListingEditSnapshot, after: ListingEditSnapshot) -> list[dict[str, Any]]:
    return [
        {"field": field, "before": before.fields.get(field), "after": after.fields.get(field)}
        for field in _TRACKED_FIELDS
        if before.comparison_fingerprints.get(field) != after.comparison_fingerprints.get(field)
    ]


def build_listing_edit_event(
    *,
    actor_id: UUID,
    listing: Listing,
    before: ListingEditSnapshot,
    after: ListingEditSnapshot,
    from_status: str,
    reason: str = LISTING_EDIT_REASON,
) -> AuditEvent | None:
    """Build an AuditEvent after a successful edit, without committing it."""
    changes = _field_changes(before, after)
    if not changes and from_status == listing.status:
        return None
    return AuditEvent(
        actor_id=actor_id,
        entity_type="listing",
        entity_id=listing.id,
        action=LISTING_EDIT_ACTION,
        details={
            "revision": listing.revision,
            "reason": reason,
            "from_status": from_status,
            "to_status": listing.status,
            "changed_field_keys": [change["field"] for change in changes],
            "changes": changes,
        },
    )


def _photo_summary(photos: Iterable[ListingPhoto | Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for photo in photos:
        if isinstance(photo, Mapping):
            photo_id = photo.get("id")
            position = photo.get("position", 0)
            is_cover = photo.get("is_cover", False)
            status = photo.get("status", "unknown")
        else:
            photo_id = photo.id
            position = photo.position
            is_cover = photo.is_cover
            status = photo.status
        rows.append(
            {
                "id": str(photo_id) if photo_id is not None else "",
                "position": int(position),
                "is_cover": bool(is_cover),
                "status": str(status)[:20],
            }
        )
    rows.sort(key=lambda row: (row["position"], row["id"]))
    return {"count": len(rows), "items": rows}


def build_listing_photo_edit_event(
    *,
    actor_id: UUID,
    listing_id: UUID,
    revision: int,
    from_status: str,
    to_status: str,
    before: Iterable[ListingPhoto | Mapping[str, Any]],
    after: Iterable[ListingPhoto | Mapping[str, Any]],
) -> AuditEvent | None:
    """Build a sanitized photo-change audit event for use by media mutations."""
    before_snapshot = _photo_summary(before)
    after_snapshot = _photo_summary(after)
    if before_snapshot == after_snapshot:
        return None
    return AuditEvent(
        actor_id=actor_id,
        entity_type="listing",
        entity_id=listing_id,
        action=LISTING_EDIT_ACTION,
        details={
            "revision": revision,
            "reason": LISTING_PHOTO_EDIT_REASON,
            "from_status": from_status,
            "to_status": to_status,
            "changed_field_keys": ["photos"],
            "changes": [{"field": "photos", "before": before_snapshot, "after": after_snapshot}],
        },
    )


def _safe_integer(value: Any, *, maximum: int) -> int:
    if type(value) is int:
        return max(0, min(maximum, value))
    return 0


def _project_value(field: str, value: Any) -> Any:
    if field == "contact_phone":
        return _masked_phone(value)
    if field == "vin":
        return _masked_vin(value)
    if field == "description":
        if isinstance(value, Mapping):
            return {
                "present": bool(value.get("present")),
                "length": _safe_integer(value.get("length"), maximum=10000),
            }
        return _redacted_description(value)
    if field == "price":
        if not isinstance(value, Mapping):
            return None
        currency = value.get("currency")
        amount = value.get("amount")
        if not isinstance(currency, str) or currency not in {"BYN", "USD"}:
            return None
        if type(amount) not in {str, int, float, Decimal}:
            return None
        try:
            number = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            return None
        if not number.is_finite() or not 0 < number <= Decimal("9999999999.99") or number != number.quantize(Decimal("0.01")):
            return None
        return {"amount": format(number, ".2f"), "currency": currency}
    if field == "photos":
        if not isinstance(value, Mapping):
            return {"count": 0, "items": []}
        items = []
        raw_items = value.get("items", [])
        if not isinstance(raw_items, list):
            raw_items = []
        for item in raw_items[:30]:
            if not isinstance(item, Mapping):
                continue
            items.append(
                {
                    "id": str(item.get("id", ""))[:64],
                    "position": _safe_integer(item.get("position"), maximum=29),
                    "is_cover": bool(item.get("is_cover")),
                    "status": str(item.get("status", "unknown"))[:20],
                }
            )
        return {"count": _safe_integer(value.get("count", len(items)), maximum=30), "items": items}
    if field == "seller_type":
        if isinstance(value, Mapping):
            seller_type = value.get("type")
            if seller_type not in {"private", "company"}:
                return None
            company_id = value.get("company_id")
            return {
                "type": seller_type,
                "company_id": str(company_id)[:64] if company_id is not None else None,
            }
        return value if value in {"private", "company"} else None
    if isinstance(value, Mapping):
        # Catalog references contain only opaque ids and catalog labels.
        if field in _REFERENCE_MODELS:
            return {"id": str(value.get("id", ""))[:64], "name": _safe_text(value.get("name")) or ""}
        return None
    if isinstance(value, list):
        return [_safe_text(item, limit=80) for item in value[:12]]
    if isinstance(value, str):
        return _safe_text(value, limit=240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return None


def project_listing_change_event(event: AuditEvent) -> ListingChangeHistoryItemOut | None:
    """Project only supported, sanitized listing-edit fields for moderator views."""
    if event.entity_type != "listing" or event.action != LISTING_EDIT_ACTION or not isinstance(event.details, Mapping):
        return None
    details = event.details
    changes: list[ListingFieldChangeOut] = []
    raw_changes = details.get("changes", [])
    raw_keys = details.get("changed_field_keys", [])
    if not isinstance(raw_changes, list) or not isinstance(raw_keys, list):
        return None
    for change in raw_changes[:64]:
        if not isinstance(change, Mapping):
            continue
        field = change.get("field")
        if not isinstance(field, str) or field not in _ALLOWED_HISTORY_FIELDS:
            continue
        changes.append(
            ListingFieldChangeOut(
                field=field,
                before=_project_value(field, change.get("before")),
                after=_project_value(field, change.get("after")),
            )
        )
    changed_keys = [key for key in raw_keys[:64] if isinstance(key, str) and key in _ALLOWED_HISTORY_FIELDS]
    # Keep the projection internally consistent even if a legacy event is malformed.
    projected_keys = {change.field for change in changes}
    changed_keys = [key for key in changed_keys if key in projected_keys]
    if event.created_at is None:
        return None
    revision = details.get("revision")
    if type(revision) is not int or revision < 1:
        return None
    reason = details.get("reason")
    if not isinstance(reason, str) or reason not in {LISTING_EDIT_REASON, LISTING_PHOTO_EDIT_REASON}:
        return None
    from_status = details.get("from_status")
    to_status = details.get("to_status")
    return ListingChangeHistoryItemOut(
        revision=revision,
        reason=reason,
        from_status=from_status if isinstance(from_status, str) else None,
        to_status=to_status if isinstance(to_status, str) else None,
        changed_field_keys=changed_keys,
        changes=changes,
        created_at=event.created_at,
    )


def list_listing_change_history(
    db: Session,
    listing_id: UUID,
    *,
    limit: int = 50,
) -> list[ListingChangeHistoryItemOut]:
    """Return newest safe edit snapshots; callers must authorize moderators first."""
    safe_limit = max(1, min(limit, 100))
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "listing",
            AuditEvent.entity_id == listing_id,
            AuditEvent.action == LISTING_EDIT_ACTION,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(safe_limit)
    ).all()
    return [
        projected
        for event in events
        if (projected := project_listing_change_event(event)) is not None
    ]
