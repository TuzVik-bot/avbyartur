from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, DealerTeamMember, User, UserSession
from app.security import secret_hash
from app.services import fail


def get_session_record(request: Request, db: Annotated[Session, Depends(get_db)]) -> UserSession:
    from app.config import get_settings

    raw = request.cookies.get(get_settings().session_cookie_name)
    if not raw:
        fail(401, "unauthorized", "Sign in required")
    record = db.get(UserSession, secret_hash(raw))
    now = datetime.now(timezone.utc)
    if record is None or record.revoked_at is not None:
        fail(401, "unauthorized", "Sign in required")
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        fail(401, "session_expired", "Session expired")
    return record


def get_current_user(
    record: Annotated[UserSession, Depends(get_session_record)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = db.get(User, record.user_id)
    if user is None or user.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    return user


def get_optional_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    from app.config import get_settings

    raw = request.cookies.get(get_settings().session_cookie_name)
    if not raw:
        return None
    record = db.get(UserSession, secret_hash(raw))
    if record is None or record.revoked_at is not None:
        return None
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        return None
    user = db.get(User, record.user_id)
    return user if user is not None and user.status == "active" else None


def require_csrf(
    request: Request,
    record: Annotated[UserSession, Depends(get_session_record)],
) -> UserSession:
    csrf_cookie = request.cookies.get("avtorinok_csrf")
    csrf_header = request.headers.get("x-csrf-token")
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header or secret_hash(csrf_header) != record.csrf_hash:
        fail(403, "csrf_failed", "A valid CSRF token is required")
    return record


def require_moderator(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role not in {"moderator", "admin"}:
        fail(403, "forbidden", "Moderator access required")
    return user


def company_context_for_user(db: Session, user: User) -> tuple[Company | None, str | None]:
    owned = db.scalar(select(Company).where(Company.owner_id == user.id))
    if owned is not None:
        return owned, "owner"

    memberships = db.execute(
        select(Company, DealerTeamMember.role)
        .join(DealerTeamMember, DealerTeamMember.company_id == Company.id)
        .where(
            DealerTeamMember.user_id == user.id,
            DealerTeamMember.status == "active",
        )
        .order_by(Company.created_at, Company.id)
        .limit(2)
    ).all()
    if len(memberships) != 1:
        return None, None
    company, role = memberships[0]
    return company, role


def user_out(db: Session, user: User) -> dict:
    company, company_role = company_context_for_user(db, user)
    return {
        "id": str(user.id), "email": user.email, "display_name": user.display_name,
        "role": user.role, "company_id": str(company.id) if company else None,
        "company_role": company_role,
    }
