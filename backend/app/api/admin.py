"""Admin-only user management, safe audit history and runtime summaries."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.admin_schemas import (
    AdminAuditListOut,
    AdminOperationsOut,
    AdminUserChangeInput,
    AdminUserChangeOut,
    AdminUserListOut,
    UserRole,
    TariffAuditSnapshotOut,
)
from app.api.dependencies import require_csrf
from app.api.moderation import require_admin
from app.admin_service import AdminChangeRejected, guard_administrative_change, lock_active_administrators
from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, Listing, User, UserSession, WorkerJob
from app.security import verify_password
from app.services import consume_rate_limit, fail

router = APIRouter(prefix="/api/v1/admin", tags=["administration"])

_SAFE_AUDIT_KEYS = frozenset({
    "reason", "revision", "expected_revision", "from_role", "to_role", "from_status",
    "to_status", "from_revision", "to_revision", "changed", "count", "format_version",
})


def _audit_details(row: AuditEvent) -> dict:
    details = row.details if isinstance(row.details, dict) else {}
    result = {key: value[:1000] if isinstance(value, str) else value for key, value in details.items()
              if key in _SAFE_AUDIT_KEYS and (value is None or isinstance(value, (str, int, bool)))}
    if row.entity_type == "runtime_setting" and row.action == "runtime_setting_updated":
        key = details.get("key")
        if isinstance(key, str) and key in {"private_listing_quota", "company_listing_quota", "saved_search_limit"}:
            result["key"] = key
            for field in ("before", "after"):
                value = details.get(field)
                if type(value) is int and 1 <= value <= 10000:
                    result[field] = value
    if row.entity_type == "billing_tariff":
        fields = set(TariffAuditSnapshotOut.model_fields)
        for field in ("before", "after"):
            snapshot = details.get(field)
            if not isinstance(snapshot, dict):
                continue
            try:
                clean = TariffAuditSnapshotOut.model_validate(
                    {key: value for key, value in snapshot.items() if key in fields}
                )
            except ValidationError:
                continue
            result[field] = clean.model_dump()
    return result


def _user_out(user: User) -> dict:
    return {
        "id": user.id, "email": user.email, "display_name": user.display_name,
        "role": user.role, "status": user.status, "created_at": user.created_at,
    }


@router.get("/users", response_model=AdminUserListOut)
def user_directory(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=25, ge=1, le=100),
    q: str | None = Query(default=None, max_length=180),
    role: UserRole | None = None,
    status: str | None = Query(default=None, max_length=20),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if q and q.strip():
        escaped = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(or_(User.email.ilike(pattern, escape="\\"), User.display_name.ilike(pattern, escape="\\")))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(User.created_at.desc(), User.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_user_out(user) for user in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/users/{user_id}", response_model=AdminUserChangeOut)
def update_user(
    user_id: UUID,
    payload: AdminUserChangeInput,
    admin: Annotated[User, Depends(require_admin)],
    csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    # This existing rate-limit helper commits its transaction. Consume before
    # taking authorization locks, so it cannot release the protected admin set.
    consume_rate_limit(db, "admin-user-reauth", str(admin.id), 10, timedelta(minutes=15))
    # Lock the active administrator set in a stable order before either user.
    # Concurrent demotions and blocking cannot remove the final administrator.
    active_admins = lock_active_administrators(db)
    actor = next((user for user in active_admins if user.id == admin.id), None)
    if actor is None:
        fail(403, "forbidden", "An active administrator is required")
    if not verify_password(payload.current_password.get_secret_value(), actor.password_hash):
        # Persist attempts even when the request fails, as in login throttling.
        db.commit()
        fail(401, "reauthentication_failed", "Подтвердите пароль администратора")
    target = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if target is None:
        fail(404, "not_found", "User not found")
    if target.status not in {"active", "blocked"}:
        fail(409, "account_unavailable", "This account cannot be reactivated through user management")
    if target.role != payload.expected_role or target.status != payload.expected_status:
        fail(409, "revision_conflict", "Учётная запись изменена; обновите список")
    try:
        guard_administrative_change(active_admins, actor, target, role=payload.role, status=payload.status)
    except AdminChangeRejected as exc:
        fail(409, exc.code, str(exc))
    if target.role == payload.role and target.status == payload.status:
        db.commit()
        return {"user": _user_out(target), "changed": False}
    old_role, old_status = target.role, target.status
    target.role, target.status = payload.role, payload.status
    db.execute(update(UserSession).where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).values(revoked_at=func.now()))
    db.add(AuditEvent(
        actor_id=actor.id, entity_type="user", entity_id=target.id,
        action="admin_user_updated", details={
            "reason": payload.reason, "from_role": old_role, "to_role": target.role,
            "from_status": old_status, "to_status": target.status,
        },
    ))
    db.commit()
    return {"user": _user_out(target), "changed": True}


@router.get("/audit", response_model=AdminAuditListOut)
def audit_history(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=25, ge=1, le=100),
    entity_type: str | None = Query(default=None, max_length=40),
    entity_id: UUID | None = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    query = select(AuditEvent)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [{
            "id": row.id, "actor_id": row.actor_id, "entity_type": row.entity_type,
            "entity_id": row.entity_id, "action": row.action, "created_at": row.created_at,
            "details": _audit_details(row),
        } for row in rows],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/operations", response_model=AdminOperationsOut)
def operation_summary(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    counts = {}
    for name, entity in [("users_by_status", User), ("listings_by_status", Listing), ("jobs_by_status", WorkerJob)]:
        counts[name] = {str(status): count for status, count in db.execute(select(entity.status, func.count()).group_by(entity.status))}
    return {
        **counts,
        "capabilities": {
            "sms_login_enabled": settings.sms_login_enabled,
            "public_registration_enabled": settings.public_registration_enabled,
        },
    }
