"""Authenticated in-app notification API.

Only rows delivered through the local web channel are exposed here. Email
preferences remain persisted in saved searches, while their outbox rows are
marked ``unsupported`` until a real provider is configured.
"""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf
from app.db import get_db
from app.models import User, UserNotification, UserSession
from app.notification_schemas import UserNotificationListOut, UserNotificationReadOut
from app.services import fail


router = APIRouter(prefix="/api/v1", tags=["notifications"])


def _serialise(row: UserNotification) -> dict:
    return {
        "id": row.id,
        "saved_search_id": row.saved_search_id,
        "conversation_id": row.conversation_id,
        "listing_id": row.listing_id,
        "title": row.title,
        "body": row.body,
        "url": row.url,
        "listings": list(row.listings or []),
        "total_count": row.total_count,
        "read_at": row.read_at,
        "created_at": row.created_at,
    }


@router.get("/me/notifications", response_model=UserNotificationListOut)
def list_notifications(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    query = select(UserNotification).where(UserNotification.user_id == user.id)
    if unread_only:
        query = query.where(UserNotification.read_at.is_(None))
    rows = db.scalars(query.order_by(UserNotification.created_at.desc(), UserNotification.id.desc()).limit(limit)).all()
    unread_count = int(
        db.scalar(
            select(func.count(UserNotification.id)).where(
                UserNotification.user_id == user.id,
                UserNotification.read_at.is_(None),
            )
        )
        or 0
    )
    return {"items": [_serialise(row) for row in rows], "unread_count": unread_count}


@router.post("/me/notifications/{notification_id}/read", response_model=UserNotificationReadOut)
def mark_notification_read(
    notification_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    del csrf
    notification = db.scalar(
        select(UserNotification)
        .where(UserNotification.id == notification_id, UserNotification.user_id == user.id)
        .with_for_update()
    )
    if notification is None:
        fail(404, "not_found", "Notification not found")
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}
