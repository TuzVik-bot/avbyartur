"""Catalog editor preserves IDs, slugs and provenance across manual revisions."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin_catalog_schemas import (
    AdminCatalogChangeInput, AdminCatalogChangeOut, AdminCatalogListOut,
    AdminCatalogVersionListOut, CatalogKind,
)
from app.api.dependencies import require_csrf
from app.api.moderation import require_admin
from app.db import get_db
from app.models import (
    AuditEvent, CatalogBodyType, CatalogBodyVariant, CatalogGeneration, CatalogMake,
    CatalogModel, CatalogModification, LocationCity, LocationRegion, User,
)
from app.security import verify_password
from app.services import consume_rate_limit, fail

router = APIRouter(prefix="/api/v1/admin/catalog", tags=["administration"])

_KINDS = {
    "makes": (CatalogMake, None), "models": (CatalogModel, "make_id"),
    "generations": (CatalogGeneration, "model_id"), "body-types": (CatalogBodyType, None),
    "body-variants": (CatalogBodyVariant, "generation_id"), "modifications": (CatalogModification, "generation_id"),
    "regions": (LocationRegion, None), "cities": (LocationCity, "region_id"),
}


def _revision(row) -> int:
    value = (row.source_metadata or {}).get("_admin_revision", 0)
    return value if type(value) is int and value >= 0 else 0


def _editable_snapshot(row) -> dict:
    result = {"name": row.name}
    for name in ["aliases", "year_from", "year_to"]:
        if hasattr(row, name):
            result[name] = getattr(row, name)
    result["source"] = _source_projection(row)
    return result


def _safe_text(value, limit: int) -> str | None:
    return value[:limit] if isinstance(value, str) else None


def _safe_source_url(value) -> str | None:
    if not isinstance(value, str) or len(value) > 4096:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname
        host = f"[{host}]" if ":" in host else host
        if parsed.port is not None:
            host += f":{parsed.port}"
        allowed = {"market", "lang", "language", "locale", "id", "qid", "format", "action", "model", "generation"}
        query = urlencode([(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                           if key.casefold() in allowed])
        return urlunsplit((parsed.scheme, host, parsed.path, query, ""))
    except ValueError:
        return None


def _scrub_source(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    result = {
        "source_name": _safe_text(value.get("source_name"), 100),
        "canonical_url": _safe_source_url(value.get("canonical_url")),
        "license_url": _safe_source_url(value.get("license_url")),
        "permission_reference": _safe_text(value.get("permission_reference"), 256),
        "query_url": _safe_source_url(value.get("query_url")),
        "checksum": _safe_text(value.get("checksum"), 64),
        "retrieved_at": _safe_text(value.get("retrieved_at"), 80),
    }
    return result if any(item is not None for item in result.values()) else None


def _source_projection(row) -> dict | None:
    metadata = row.source_metadata if isinstance(row.source_metadata, dict) else {}
    return _scrub_source({
        "source_name": row.source_name,
        "canonical_url": metadata.get("source_url") or metadata.get("url") or metadata.get("generation_url") or metadata.get("model_url"),
        "license_url": metadata.get("license_url"), "permission_reference": metadata.get("permission_ref"),
        "query_url": metadata.get("query_url"), "checksum": metadata.get("query_sha256") or metadata.get("checksum"),
        "retrieved_at": metadata.get("retrieved_at"),
    })


def _scrub_snapshot(value) -> dict:
    if not isinstance(value, dict):
        return {}
    result = {}
    if isinstance(value.get("name"), str):
        result["name"] = value["name"][:1024]
    aliases = value.get("aliases")
    if isinstance(aliases, list):
        result["aliases"] = [alias[:180] for alias in aliases[:40] if isinstance(alias, str)]
    for field in ("year_from", "year_to"):
        year = value.get(field)
        if year is None or type(year) is int and 1886 <= year <= 2100:
            result[field] = year
    result["source"] = _scrub_source(value.get("source"))
    return result


def _item(row, kind: CatalogKind) -> dict:
    parent = _KINDS[kind][1]
    return {
        "id": row.id, "kind": kind, "name": row.name, "slug": row.slug,
        "aliases": getattr(row, "aliases", []) or [],
        "parent_id": getattr(row, parent) if parent else None,
        "year_from": getattr(row, "year_from", None), "year_to": getattr(row, "year_to", None),
        "source_name": row.source_name, "manual_override": row.manual_override,
        "source": _source_projection(row),
        "revision": _revision(row),
    }


@router.get("/{kind}", response_model=AdminCatalogListOut)
def catalog_records(
    kind: CatalogKind,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=25, ge=1, le=100),
    q: str | None = Query(default=None, max_length=180),
    parent_id: UUID | None = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    entity, parent = _KINDS[kind]
    query = select(entity)
    if parent_id:
        if not parent:
            fail(422, "invalid_parent_filter", "This catalog does not have parent records")
        query = query.where(getattr(entity, parent) == parent_id)
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(entity.name.ilike(f"%{escaped}%", escape="\\"))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(entity.name, entity.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_item(row, kind) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/{kind}/{record_id}", response_model=AdminCatalogChangeOut)
def edit_catalog_record(
    kind: CatalogKind, record_id: UUID, payload: AdminCatalogChangeInput,
    admin: Annotated[User, Depends(require_admin)],
    csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    consume_rate_limit(db, "admin-catalog-reauth", str(admin.id), 10, timedelta(minutes=15))
    actor = db.scalar(select(User).where(User.id == admin.id).with_for_update().execution_options(populate_existing=True))
    if actor is None or actor.role != "admin" or actor.status != "active":
        fail(403, "forbidden", "An active administrator is required")
    if not verify_password(payload.current_password.get_secret_value(), actor.password_hash):
        fail(401, "reauthentication_failed", "Подтвердите пароль администратора")
    entity = _KINDS[kind][0]
    row = db.scalar(select(entity).where(entity.id == record_id).with_for_update().execution_options(populate_existing=True))
    if row is None:
        fail(404, "not_found", "Catalog record not found")
    if _revision(row) != payload.expected_revision:
        fail(409, "revision_conflict", "Запись справочника изменена; обновите список")
    name_limit = getattr(entity.name.property.columns[0].type, "length", None)
    if name_limit and len(payload.name) > name_limit:
        fail(422, "validation_error", "Название слишком длинное", {"name": f"Не более {name_limit} символов"})
    before = _editable_snapshot(row)
    changes = {"name": payload.name}
    for field in ["aliases", "year_from", "year_to"]:
        if field not in payload.model_fields_set:
            continue
        value = getattr(payload, field)
        if not hasattr(row, field):
            if value not in (None, []):
                fail(422, "unsupported_catalog_field", "Поле не применяется к этому справочнику", {field: "Недоступно"})
            continue
        if field == "aliases" and value is None:
            continue
        changes[field] = value
    combined = {**before, **changes}
    if combined.get("year_from") is not None and combined.get("year_to") is not None and combined["year_from"] > combined["year_to"]:
        fail(422, "validation_error", "Год окончания не может предшествовать началу", {"year_to": "Проверьте диапазон"})
    if all(getattr(row, key) == value for key, value in changes.items()):
        db.commit()
        return {"item": _item(row, kind), "changed": False}
    revision = _revision(row) + 1
    for key, value in changes.items():
        setattr(row, key, value)
    row.manual_override = True
    row.source_metadata = {**(row.source_metadata or {}), "_admin_revision": revision}
    db.add(AuditEvent(actor_id=actor.id, entity_type=f"catalog:{kind}", entity_id=row.id, action="catalog_updated",
                      details={"revision": revision, "reason": payload.reason, "before": before, "after": _editable_snapshot(row)}))
    db.commit()
    return {"item": _item(row, kind), "changed": True}


@router.get("/{kind}/{record_id}/versions", response_model=AdminCatalogVersionListOut)
def catalog_versions(
    kind: CatalogKind, record_id: UUID,
    admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)],
    response: Response,
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if db.get(_KINDS[kind][0], record_id) is None:
        fail(404, "not_found", "Catalog record not found")
    query = select(AuditEvent).where(AuditEvent.entity_type == f"catalog:{kind}", AuditEvent.entity_id == record_id, AuditEvent.action == "catalog_updated")
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for row in rows:
        details = row.details if isinstance(row.details, dict) else {}
        revision = details.get("revision")
        valid = type(revision) is int and revision >= 1 and isinstance(details.get("before"), dict) and isinstance(details.get("after"), dict) and isinstance(details.get("reason"), str)
        before = _scrub_snapshot(details.get("before"))
        after = _scrub_snapshot(details.get("after"))
        items.append({"id": row.id, "revision": revision if type(revision) is int and revision >= 0 else 0, "actor_id": row.actor_id,
                      "reason": _safe_text(details.get("reason"), 1000) or "", "before": before, "after": after,
                      "source": after.get("source"), "valid": valid,
                      "created_at": row.created_at})
    return {
        "items": items,
        "total": total, "page": page, "page_size": page_size,
    }
