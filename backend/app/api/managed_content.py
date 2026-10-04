"""Explicit admin publishing and public reads of approved editorial content."""

import copy
import hashlib
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import require_csrf
from app.api.moderation import require_admin
from app.db import get_db
from app.managed_content import ManagedContent, ManagedContentVersion, validate_content
from app.managed_content_schemas import (
    ContentKind, ManagedContentChangeInput, ManagedContentEnvelope, ManagedContentListOut,
    ManagedContentPublicEnvelope, ManagedContentVersionsOut,
)
from app.models import AuditEvent, Listing, LocationCity, User
from app.security import verify_password
from app.services import consume_rate_limit, fail

router = APIRouter(prefix="/api/v1", tags=["managed content"])


def _out(row: ManagedContent) -> dict:
    return {"id": row.id, "kind": row.kind, "key": row.key, "payload": row.payload,
            "status": row.status, "revision": row.revision, "updated_at": row.updated_at}


@router.get("/admin/content", response_model=ManagedContentListOut)
def list_content(
    admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)], response: Response,
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), kind: ContentKind | None = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    query = select(ManagedContent)
    if kind:
        query = query.where(ManagedContent.kind == kind)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(ManagedContent.kind, ManagedContent.key).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_out(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.put("/admin/content/{kind}/{key}", response_model=ManagedContentEnvelope)
def update_content(
    kind: ContentKind, key: Annotated[str, Path(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")],
    payload: ManagedContentChangeInput, admin: Annotated[User, Depends(require_admin)],
    csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)], response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        content_payload = validate_content(kind, key, payload.payload, payload.status)
    except (ValidationError, ValueError):
        fail(422, "invalid_content", "Проверьте поля, шаблон и утверждение документа")
    consume_rate_limit(db, "admin-content-reauth", str(admin.id), 10, timedelta(minutes=15))
    actor = db.scalar(select(User).where(User.id == admin.id).with_for_update().execution_options(populate_existing=True))
    if actor is None or actor.role != "admin" or actor.status != "active":
        fail(403, "forbidden", "An active administrator is required")
    if not verify_password(payload.current_password.get_secret_value(), actor.password_hash):
        fail(401, "reauthentication_failed", "Подтвердите пароль администратора")
    lock_key = int.from_bytes(hashlib.sha256(f"avtorinok-content:{kind}:{key}".encode()).digest()[:8], "big") & ((1 << 63) - 1)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    row = db.scalar(select(ManagedContent).where(ManagedContent.kind == kind, ManagedContent.key == key).with_for_update().execution_options(populate_existing=True))
    if (row.revision if row else 0) != payload.expected_revision:
        fail(409, "revision_conflict", "Материал изменён; обновите редактор")
    if row is None:
        row = ManagedContent(kind=kind, key=key, payload=content_payload, status=payload.status, revision=1, updated_by=actor.id)
        db.add(row); db.flush()
    else:
        row.payload = content_payload; row.status = payload.status; row.revision += 1; row.updated_by = actor.id
    db.add(ManagedContentVersion(content_id=row.id, revision=row.revision, payload=copy.deepcopy(content_payload), status=row.status, actor_id=actor.id, reason=payload.reason))
    db.add(AuditEvent(actor_id=actor.id, entity_type="managed_content", entity_id=row.id, action="content_updated",
                      details={"revision": row.revision, "reason": payload.reason, "to_status": row.status}))
    db.commit()
    return {"content": _out(row)}


@router.get("/admin/content/{kind}/{key}/versions", response_model=ManagedContentVersionsOut)
def content_versions(
    kind: ContentKind, key: str, admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)], response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    row = db.scalar(select(ManagedContent).where(ManagedContent.kind == kind, ManagedContent.key == key))
    if row is None:
        fail(404, "not_found", "Content not found")
    versions = db.scalars(select(ManagedContentVersion).where(ManagedContentVersion.content_id == row.id).order_by(ManagedContentVersion.revision.desc()).limit(100)).all()
    return {"items": [{"revision": version.revision, "payload": version.payload, "status": version.status,
                       "actor_id": version.actor_id, "reason": version.reason, "created_at": version.created_at} for version in versions]}


@router.get("/content/{kind}/{key}", response_model=ManagedContentPublicEnvelope)
def public_content(kind: ContentKind, key: str, db: Annotated[Session, Depends(get_db)], response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if kind == "notification_template":
        fail(404, "not_found", "Content not found")
    row = db.scalar(select(ManagedContent).where(ManagedContent.kind == kind, ManagedContent.key == key, ManagedContent.status == "published"))
    if row is None:
        fail(404, "not_found", "Content not found")
    try:
        valid_payload = validate_content(row.kind, row.key, row.payload, row.status)
    except (ValidationError, ValueError):
        fail(404, "not_found", "Content not found")
    indexable = False
    if kind == "seo_page" and valid_payload["indexable"]:
        from app.api.listings import _active_query
        query = _active_query()
        for field, identifier in valid_payload["filters"].items():
            from uuid import UUID
            query = query.where(getattr(Listing, field) == UUID(identifier))
        path = valid_payload["canonical_path"]
        if path.startswith("/cars/city/"):
            query = query.join(LocationCity, Listing.city_id == LocationCity.id).where(LocationCity.slug == path.removeprefix("/cars/city/").strip("/"))
        available = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        indexable = available >= valid_payload["minimum_results"]
    result = _out(row); result["payload"] = valid_payload
    return {"content": result, "indexable": indexable}
