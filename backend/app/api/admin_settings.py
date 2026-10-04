"""Non-secret limit changes require current admin authentication and audit."""

import hashlib
from datetime import timedelta
from typing import Annotated
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import require_csrf
from app.api.moderation import require_admin
from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, User
from app.runtime_setting_schemas import RuntimeSettingChangeInput, RuntimeSettingChangeOut, RuntimeSettingListOut
from app.runtime_settings import LIMIT_KEYS, RuntimeSetting
from app.security import verify_password
from app.services import consume_rate_limit, fail

router = APIRouter(prefix="/api/v1/admin/settings", tags=["administration"])


def _setting(key: str, row: RuntimeSetting | None) -> dict:
    return {"key": key, "value": row.value if row else getattr(get_settings(), key),
            "revision": row.revision if row else 0, "source": "override" if row else "environment"}


@router.get("", response_model=RuntimeSettingListOut)
def list_settings(
    admin: Annotated[User, Depends(require_admin)], db: Annotated[Session, Depends(get_db)], response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    overrides = {row.key: row for row in db.scalars(select(RuntimeSetting).where(RuntimeSetting.key.in_(LIMIT_KEYS))).all()}
    return {"items": [_setting(key, overrides.get(key)) for key in sorted(LIMIT_KEYS)]}


@router.patch("/{key}", response_model=RuntimeSettingChangeOut)
def update_setting(
    key: str, payload: RuntimeSettingChangeInput,
    admin: Annotated[User, Depends(require_admin)], csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)], response: Response,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    if key not in LIMIT_KEYS:
        fail(404, "not_found", "Настройка не поддерживается")
    consume_rate_limit(db, "admin-setting-reauth", str(admin.id), 10, timedelta(minutes=15))
    actor = db.scalar(select(User).where(User.id == admin.id).with_for_update().execution_options(populate_existing=True))
    if actor is None or actor.role != "admin" or actor.status != "active":
        fail(403, "forbidden", "An active administrator is required")
    if not verify_password(payload.current_password.get_secret_value(), actor.password_hash):
        fail(401, "reauthentication_failed", "Подтвердите пароль администратора")
    # There may be no override row yet. A transaction-scoped per-key advisory
    # lock protects its first creation as well as later revision updates.
    lock_key = int.from_bytes(hashlib.sha256(f"avtorinok-runtime-setting:{key}".encode()).digest()[:8], "big") & ((1 << 63) - 1)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    row = db.scalar(select(RuntimeSetting).where(RuntimeSetting.key == key).with_for_update().execution_options(populate_existing=True))
    current = _setting(key, row)
    if current["revision"] != payload.expected_revision:
        fail(409, "revision_conflict", "Настройка изменена; обновите страницу")
    if current["value"] == payload.value:
        db.commit()
        return {"setting": current, "changed": False}
    if row is None:
        row = RuntimeSetting(key=key, value=payload.value, revision=1)
        db.add(row)
    else:
        row.value = payload.value
        row.revision += 1
    db.add(AuditEvent(actor_id=actor.id, entity_type="runtime_setting", entity_id=uuid5(NAMESPACE_URL, f"avtorinok:setting:{key}"),
                      action="runtime_setting_updated", details={"key": key, "reason": payload.reason, "revision": row.revision,
                                                                   "before": current["value"], "after": payload.value}))
    db.commit()
    return {"setting": _setting(key, row), "changed": True}
