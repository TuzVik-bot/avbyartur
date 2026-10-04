"""Profile phone-change and global notification preference endpoints."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import auth as auth_api
from app.api.auth import _prevent_session_caching
from app.api.dependencies import get_current_user, get_session_record, require_csrf
from app.config import get_settings
from app.db import get_db
from app.models import AuditEvent, User, UserSession
from app.profile_identity_models import ProfilePhoneChangeChallenge, UserNotificationPreferences
from app.profile_identity_schemas import (
    NotificationPreferencesEnvelope,
    NotificationPreferencesInput,
    PhoneChangeAcceptedResponse,
    PhoneChangeConfirmInput,
    PhoneChangeConfirmedResponse,
    PhoneChangeRequestInput,
)
from app.profile_identity_service import verified_email
from app.sms_auth import (
    SmsCodeProvider,
    create_otp_code,
    digest_matches,
    idempotency_key_digest,
    normalize_belarus_mobile_phone,
    otp_code_digest,
    phone_subject_digest,
)
from app.services import consume_rate_limit, fail


router = APIRouter(prefix="/api/v1", tags=["profile identity"])


def get_profile_sms_provider():
    return auth_api.get_sms_provider()
PHONE_CHANGE_TTL = timedelta(minutes=10)
PHONE_CHANGE_MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    return f"+{digits[:3]}{'*' * max(3, len(digits) - 5)}{digits[-2:]}"


def _normalize_phone(value: str) -> str:
    try:
        return normalize_belarus_mobile_phone(value)
    except ValueError:
        fail(422, "invalid_phone", "Enter a supported Belarus mobile phone number", {"phone": "Invalid Belarus mobile number"})


def _preference_response(db: Session, user_id: uuid.UUID) -> dict:
    row = db.get(UserNotificationPreferences, user_id)
    return {
        "preferences": {
            "web_enabled": row.web_enabled if row is not None else True,
            "email_enabled": row.email_enabled if row is not None else True,
            "revision": row.revision if row is not None else 0,
            "email_verified": verified_email(db, user_id) is not None,
        }
    }


@router.get(
    "/me/notification-preferences", response_model=NotificationPreferencesEnvelope
)
def get_notification_preferences(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    return _preference_response(db, user.id)


@router.put(
    "/me/notification-preferences", response_model=NotificationPreferencesEnvelope
)
def update_notification_preferences(
    payload: NotificationPreferencesInput,
    response: Response,
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    row = db.scalar(
        select(UserNotificationPreferences)
        .where(UserNotificationPreferences.user_id == user.id)
        .with_for_update()
    )
    if row is None:
        if payload.expected_revision != 0:
            fail(409, "revision_conflict", "Notification preferences changed; reload and retry")
        row = UserNotificationPreferences(
            user_id=user.id,
            web_enabled=payload.web_enabled,
            email_enabled=payload.email_enabled,
            revision=1,
        )
        db.add(row)
    else:
        if row.revision != payload.expected_revision:
            fail(409, "revision_conflict", "Notification preferences changed; reload and retry")
        row.web_enabled = payload.web_enabled
        row.email_enabled = payload.email_enabled
        row.revision += 1
    db.add(
        AuditEvent(
            actor_id=user.id,
            entity_type="notification_preferences",
            entity_id=user.id,
            action="notification_preferences_updated",
            details={
                "revision": row.revision,
                "web_enabled": row.web_enabled,
                "email_enabled": row.email_enabled,
            },
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "revision_conflict", "Notification preferences changed; reload and retry")
    return _preference_response(db, user.id)


@router.post(
    "/me/profile/phone-change/request",
    response_model=PhoneChangeAcceptedResponse,
    status_code=202,
)
def request_phone_change(
    payload: PhoneChangeRequestInput,
    request: Request,
    response: Response,
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[SmsCodeProvider, Depends(get_profile_sms_provider)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    _prevent_session_caching(response)
    settings = get_settings()
    if not settings.sms_login_enabled or not provider.is_configured:
        fail(503, "sms_provider_unconfigured", "Phone verification is not available")
    if not idempotency_key or not idempotency_key.strip() or len(idempotency_key) > 120 or any(ord(character) < 0x20 for character in idempotency_key):
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    if not user.phone_e164 or user.phone_verified_at is None:
        fail(409, "current_phone_unverified", "A verified current phone number is required")
    new_phone = _normalize_phone(payload.phone)
    if new_phone == user.phone_e164:
        fail(422, "phone_unchanged", "Enter a different phone number")

    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    new_phone_owner = db.scalar(
        select(User.id).where(
            User.phone_e164 == new_phone,
            User.id != user.id,
            User.phone_verified_at.is_not(None),
        )
    )
    if new_phone_owner is not None:
        fail(409, "phone_in_use", "This phone number is already in use")

    consume_rate_limit(db, "identity-phone-change-ip", request.client.host if request.client else "unknown", 20, timedelta(hours=1))
    consume_rate_limit(db, "identity-phone-change-user", str(user.id), 5, timedelta(hours=1))

    # Rate-limit accounting commits its own transaction. Reacquire the user
    # lock and recheck the bound number after that commit so a concurrent
    # profile mutation cannot make this proof stale.
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status != "active" or not locked_user.phone_e164 or locked_user.phone_verified_at is None:
        fail(409, "current_phone_unverified", "A verified current phone number is required")
    if new_phone == locked_user.phone_e164:
        fail(422, "phone_unchanged", "Enter a different phone number")
    new_phone_owner = db.scalar(
        select(User.id).where(
            User.phone_e164 == new_phone,
            User.id != user.id,
            User.phone_verified_at.is_not(None),
        )
    )
    if new_phone_owner is not None:
        fail(409, "phone_in_use", "This phone number is already in use")

    otp_secret = settings.sms_otp_secret.get_secret_value()
    old_phone_hash = phone_subject_digest(locked_user.phone_e164, otp_secret)
    key_hash = idempotency_key_digest(str(user.id), otp_secret, f"profile-phone-change:{idempotency_key.strip()}")
    request_digest = hmac.new(
        otp_secret.encode(),
        f"profile-phone-change-request:v1:{user.id}:{locked_user.phone_e164}:{new_phone}".encode(),
        hashlib.sha256,
    ).hexdigest()
    existing = db.scalar(
        select(ProfilePhoneChangeChallenge)
        .where(
            ProfilePhoneChangeChallenge.user_id == user.id,
            ProfilePhoneChangeChallenge.idempotency_key_hash == key_hash,
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.request_digest != request_digest:
            fail(409, "idempotency_conflict", "Idempotency key was already used for a different request")
        if existing.consumed_at is not None or existing.invalidated_at is not None or existing.expires_at <= _now():
            fail(409, "phone_change_challenge_expired", "Request a new verification code")
        if existing.sent_at is None:
            fail(503, "sms_delivery_uncertain", "SMS delivery status is unavailable; request a new code after the resend cooldown")
        return {
            "accepted": True,
            "challenge_id": existing.id,
            "old_phone_masked": _mask_phone(locked_user.phone_e164),
            "new_phone_masked": _mask_phone(existing.new_phone_e164),
            "expires_in_seconds": max(1, int((existing.expires_at - _now()).total_seconds())),
        }

    now = _now()
    for previous in db.scalars(
        select(ProfilePhoneChangeChallenge)
        .where(
            ProfilePhoneChangeChallenge.user_id == user.id,
            ProfilePhoneChangeChallenge.consumed_at.is_(None),
            ProfilePhoneChangeChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        previous.invalidated_at = now

    challenge = ProfilePhoneChangeChallenge(
        user_id=user.id,
        old_phone_hash=old_phone_hash,
        new_phone_e164=new_phone,
        idempotency_key_hash=key_hash,
        request_digest=request_digest,
        old_code_digest="pending",
        new_code_digest="pending",
        expires_at=now + PHONE_CHANGE_TTL,
    )
    old_code, new_code = create_otp_code(), create_otp_code()
    challenge.old_code_digest = otp_code_digest(locked_user.phone_e164, old_code, otp_secret)
    challenge.new_code_digest = otp_code_digest(new_phone, new_code, otp_secret)
    db.add(challenge)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "phone_in_use", "This phone number is already in use")

    try:
        provider.send_code(
            locked_user.phone_e164,
            old_code,
            idempotency_key=f"{key_hash}:old",
        )
        provider.send_code(new_phone, new_code, idempotency_key=f"{key_hash}:new")
    except Exception:
        with db.begin():
            failed = db.scalar(
                select(ProfilePhoneChangeChallenge)
                .where(ProfilePhoneChangeChallenge.id == challenge.id)
                .with_for_update()
            )
            if failed is not None:
                failed.invalidated_at = _now()
        fail(503, "sms_delivery_uncertain", "Phone verification delivery is unavailable; retry with a new request key")

    challenge.sent_at = _now()
    db.commit()
    return {
        "accepted": True,
        "challenge_id": challenge.id,
        "old_phone_masked": _mask_phone(locked_user.phone_e164),
        "new_phone_masked": _mask_phone(new_phone),
        "expires_in_seconds": int(PHONE_CHANGE_TTL.total_seconds()),
    }


@router.post(
    "/me/profile/phone-change/confirm", response_model=PhoneChangeConfirmedResponse
)
def confirm_phone_change(
    payload: PhoneChangeConfirmInput,
    response: Response,
    current_session: Annotated[UserSession, Depends(get_session_record)],
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    now = _now()
    settings = get_settings()
    challenge = db.scalar(
        select(ProfilePhoneChangeChallenge)
        .where(
            ProfilePhoneChangeChallenge.id == payload.challenge_id,
            ProfilePhoneChangeChallenge.user_id == user.id,
            ProfilePhoneChangeChallenge.sent_at.is_not(None),
            ProfilePhoneChangeChallenge.consumed_at.is_(None),
            ProfilePhoneChangeChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    )
    if challenge is None or challenge.expires_at <= now or challenge.attempt_count >= PHONE_CHANGE_MAX_ATTEMPTS:
        if challenge is not None:
            challenge.invalidated_at = now
            db.commit()
        fail(401, "invalid_phone_change_otp", "The verification codes are invalid or expired")

    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    otp_secret = settings.sms_otp_secret.get_secret_value()
    current_old_hash = phone_subject_digest(locked_user.phone_e164 or "", otp_secret)
    supplied_old_digest = otp_code_digest(locked_user.phone_e164 or "", payload.old_code, otp_secret)
    supplied_new_digest = otp_code_digest(challenge.new_phone_e164, payload.new_code, otp_secret)
    old_phone_unchanged = hmac.compare_digest(challenge.old_phone_hash, current_old_hash)
    old_valid = digest_matches(challenge.old_code_digest, supplied_old_digest)
    new_valid = digest_matches(challenge.new_code_digest, supplied_new_digest)
    if not (old_phone_unchanged and old_valid and new_valid):
        challenge.attempt_count += 1
        if challenge.attempt_count >= PHONE_CHANGE_MAX_ATTEMPTS:
            challenge.invalidated_at = now
        db.commit()
        fail(401, "invalid_phone_change_otp", "The verification codes are invalid or expired")

    existing_owner = db.scalar(
        select(User.id).where(
            User.phone_e164 == challenge.new_phone_e164,
            User.id != user.id,
            User.phone_verified_at.is_not(None),
        )
    )
    if existing_owner is not None:
        challenge.invalidated_at = now
        db.commit()
        fail(409, "phone_in_use", "This phone number is already in use")

    locked_user.phone_e164 = challenge.new_phone_e164
    locked_user.phone_verified_at = now
    challenge.consumed_at = now
    sessions = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        ).with_for_update()
    ).all()
    for session in sessions:
        session.revoked_at = now
    db.add(
        AuditEvent(
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            action="profile_phone_changed",
            details={"sessions_revoked": len(sessions)},
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        diagnostic = getattr(exc.orig, "diag", None)
        if getattr(diagnostic, "constraint_name", None) != "uq_user_phone_e164":
            raise
        rejected = db.scalar(select(ProfilePhoneChangeChallenge).where(
            ProfilePhoneChangeChallenge.id == payload.challenge_id,
            ProfilePhoneChangeChallenge.user_id == user.id,
        ).with_for_update())
        if rejected is not None:
            rejected.invalidated_at = now
            db.commit()
        fail(409, "phone_in_use", "This phone number is already in use")
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("avtorinok_csrf", path="/")
    del current_session
    return {"changed": True}
