"""Profile, email verification, recovery, and account deactivation endpoints."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.account_schemas import (
    AccountDeletionRequestInput,
    AccountDeletionRequestedResponse,
    ConsentHistoryResponse,
    EmailRequestInput,
    EmailVerifiedResponse,
    ProfileEnvelope,
    ProfilePatchInput,
    RecoveryConfirmInput,
    RecoveryConfirmedResponse,
    TokenInput,
)
from app.api.auth import CSRF_COOKIE, _prevent_session_caching
from app.api.dependencies import get_current_user, require_csrf
from app.config import get_settings
from app.db import get_db
from app.email_delivery import EmailDeliveryUnavailable, get_email_sender
from app.identity_models import (
    AccountDeletionRequest,
    AccountRecoveryChallenge,
    EmailVerificationChallenge,
    IdentityEmailOutbox,
    VerifiedEmailContact,
)
from app.models import AuditEvent, Listing, ListingStatusEvent, User, UserConsent, UserSession
from app.security import client_ip, hash_password, new_secret, normalize_email, secret_hash
from app.services import consume_rate_limit, enqueue_job, fail
from app.sms_auth_schemas import OtpAcceptedResponse
from app.managed_content import render_notification_template

router = APIRouter(prefix="/api/v1", tags=["identity"])
EMAIL_CHALLENGE_LIFETIME = timedelta(minutes=30)
RECOVERY_CHALLENGE_LIFETIME = timedelta(minutes=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, domain = value.rsplit("@", 1)
    domain_name, separator, suffix = domain.rpartition(".")
    masked_domain = f"{domain_name[:1]}***.{suffix}" if separator else "***"
    return f"{local[:1]}***@{masked_domain}"


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 2:
        return "*" * len(digits)
    country = f"+{digits[:3]}" if len(digits) >= 11 else ""
    visible_suffix = digits[-2:]
    masked_count = max(3, len(digits) - len(country.removeprefix("+")) - 2)
    return f"{country}{'*' * masked_count}{visible_suffix}"


def _profile(db: Session, user: User) -> dict:
    verified_email = db.scalar(
        select(VerifiedEmailContact).where(VerifiedEmailContact.user_id == user.id)
    )
    email_value = user.email or (verified_email.email if verified_email else None)
    return {
        "profile": {
            "id": str(user.id),
            "display_name": user.display_name,
            "contacts": {
                "email": {
                    "masked": _mask_email(email_value),
                    "verified": bool(
                        verified_email
                        and email_value
                        and verified_email.email == normalize_email(email_value)
                    ),
                },
                "phone": {
                    "masked": _mask_phone(user.phone_e164),
                    "verified": user.phone_verified_at is not None,
                },
            },
        }
    }


def _rate_limit(db: Session, request_ip: str, namespace: str, subject: str, limit: int) -> None:
    consume_rate_limit(db, f"identity-{namespace}-ip", request_ip, limit * 4, timedelta(hours=1))
    consume_rate_limit(db, f"identity-{namespace}", subject, limit, timedelta(hours=1))


def _active_challenge(challenge, now: datetime) -> bool:
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return challenge.consumed_at is None and challenge.invalidated_at is None and expires_at > now


def _create_identity_email(
    db: Session,
    *,
    user_id: uuid.UUID,
    recipient: str,
    message_type: str,
    challenge_id: uuid.UUID,
    token: str,
    now: datetime,
) -> IdentityEmailOutbox:
    if message_type == "email_verification":
        subject = "Подтверждение адреса электронной почты"
        purpose = "подтвердить адрес электронной почты"
    else:
        subject = "Восстановление доступа к аккаунту"
        purpose = "восстановить доступ к аккаунту"
    body = (
        f"Используйте этот код, чтобы {purpose} на сайте Авторынок.\n\n"
        f"Код: {token}\n\n"
        "Код действует 30 минут. Если вы не запрашивали его, проигнорируйте письмо."
    )
    user = db.get(User, user_id)
    origin = get_settings().public_app_url.rstrip("/")
    route = "/verify-email" if message_type == "email_verification" else "/recover"
    # Fragment capabilities never enter HTTP access logs or Referer headers.
    confirmation_url = f"{origin}{route}#token={quote(token, safe='')}" if origin else ""
    subject, body = render_notification_template(db, message_type, {
        "confirmation_code": token, "confirmation_url": confirmation_url,
        "display_name": user.display_name if user else "",
    }, default_subject=subject, default_body=body)
    outbox = IdentityEmailOutbox(
        dedupe_key=f"identity-email:{message_type}:{challenge_id}",
        message_type=message_type,
        challenge_id=challenge_id,
        user_id=user_id,
        recipient=recipient,
        subject=subject,
        body=body,
        status="queued",
        attempts=0,
        available_at=now,
    )
    db.add(outbox)
    db.flush()
    enqueue_job(
        db,
        "identity.email.deliver",
        f"identity.email.deliver:{outbox.id}",
        {"outbox_id": str(outbox.id)},
        run_after=now,
    )
    return outbox


@router.get("/me/profile", response_model=ProfileEnvelope)
def get_profile(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    return _profile(db, user)


@router.patch("/me/profile", response_model=ProfileEnvelope)
def patch_profile(
    payload: ProfilePatchInput,
    response: Response,
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    consume_rate_limit(db, "identity-profile", str(user.id), 30, timedelta(hours=1))
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    locked_user.display_name = payload.display_name
    db.commit()
    return _profile(db, locked_user)


@router.get("/me/consents", response_model=ConsentHistoryResponse)
def consent_history(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    items = db.scalars(
        select(UserConsent)
        .where(UserConsent.user_id == user.id)
        .order_by(UserConsent.accepted_at.desc(), UserConsent.id)
    ).all()
    return {
        "items": [
            {
                "document_type": item.document_type,
                "version": item.version,
                "accepted_at": item.accepted_at,
                "source": item.source,
            }
            for item in items
        ]
    }


@router.post(
    "/auth/email/verification/request",
    response_model=OtpAcceptedResponse,
    status_code=202,
)
def request_email_verification(
    payload: EmailRequestInput,
    request: Request,
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    sender = get_email_sender(get_settings())
    if not sender.is_configured:
        fail(503, "email_provider_unconfigured", "Email verification is unavailable")
    email = normalize_email(str(payload.email))
    _rate_limit(db, client_ip(request), "email-verification", str(user.id), 5)
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    existing_user = db.scalar(select(User.id).where(User.email == email, User.id != locked_user.id))
    existing_contact = db.scalar(
        select(VerifiedEmailContact.id).where(
            VerifiedEmailContact.email == email,
            VerifiedEmailContact.user_id != locked_user.id,
        )
    )
    if existing_user is not None or existing_contact is not None:
        fail(409, "email_unavailable", "This email address cannot be used")
    current_contact = db.scalar(
        select(VerifiedEmailContact).where(VerifiedEmailContact.user_id == locked_user.id)
    )
    if current_contact and current_contact.email == email and locked_user.email == email:
        return {"accepted": True}

    now = _now()
    for previous in db.scalars(
        select(EmailVerificationChallenge)
        .where(
            EmailVerificationChallenge.user_id == locked_user.id,
            EmailVerificationChallenge.consumed_at.is_(None),
            EmailVerificationChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        previous.invalidated_at = now
    token = new_secret()
    challenge = EmailVerificationChallenge(
        user_id=locked_user.id,
        email=email,
        token_digest=secret_hash(token),
        expires_at=now + EMAIL_CHALLENGE_LIFETIME,
    )
    db.add(challenge)
    db.flush()
    _create_identity_email(
        db,
        user_id=locked_user.id,
        recipient=email,
        message_type="email_verification",
        challenge_id=challenge.id,
        token=token,
        now=now,
    )
    db.commit()
    return {"accepted": True}


@router.post("/auth/email/verification/confirm", response_model=EmailVerifiedResponse)
def confirm_email_verification(
    payload: TokenInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _rate_limit(db, client_ip(request), "email-confirm", "all", 12)
    now = _now()
    challenge = db.scalar(
        select(EmailVerificationChallenge)
        .where(EmailVerificationChallenge.token_digest == secret_hash(payload.token))
        .with_for_update()
    )
    if challenge is None or not _active_challenge(challenge, now):
        fail(401, "email_verification_invalid", "The verification code is invalid or expired")
    user = db.scalar(select(User).where(User.id == challenge.user_id).with_for_update())
    if user is None or user.status != "active":
        fail(401, "email_verification_invalid", "The verification code is invalid or expired")
    current_owner = db.scalar(
        select(User.id).where(User.email == challenge.email, User.id != user.id)
    )
    contact_owner = db.scalar(
        select(VerifiedEmailContact.user_id).where(
            VerifiedEmailContact.email == challenge.email,
            VerifiedEmailContact.user_id != user.id,
        )
    )
    if current_owner is not None or contact_owner is not None:
        fail(409, "email_unavailable", "This email address cannot be used")
    try:
        with db.begin_nested():
            contact = db.scalar(
                select(VerifiedEmailContact)
                .where(VerifiedEmailContact.user_id == user.id)
                .with_for_update()
            )
            if contact is None:
                contact = VerifiedEmailContact(
                    user_id=user.id,
                    email=challenge.email,
                    verified_at=now,
                )
                db.add(contact)
            else:
                contact.email = challenge.email
                contact.verified_at = now
            user.email = challenge.email
            challenge.consumed_at = now
            for recovery in db.scalars(
                select(AccountRecoveryChallenge)
                .where(
                    AccountRecoveryChallenge.user_id == user.id,
                    AccountRecoveryChallenge.consumed_at.is_(None),
                    AccountRecoveryChallenge.invalidated_at.is_(None),
                )
                .with_for_update()
            ).all():
                recovery.invalidated_at = now
            db.flush()
    except IntegrityError:
        fail(409, "email_unavailable", "This email address cannot be used")
    db.commit()
    return {"verified": True}


@router.post("/auth/recovery/request", response_model=OtpAcceptedResponse, status_code=202)
def request_account_recovery(
    payload: EmailRequestInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _rate_limit(db, client_ip(request), "recovery", "all", 10)
    sender = get_email_sender(get_settings())
    if not sender.is_configured:
        return {"accepted": True}
    email = normalize_email(str(payload.email))
    user = db.scalar(
        select(User)
        .join(VerifiedEmailContact, VerifiedEmailContact.user_id == User.id)
        .where(
            VerifiedEmailContact.email == email,
            User.email == email,
            User.status == "active",
        )
        .with_for_update()
    )
    if user is None:
        return {"accepted": True}
    now = _now()
    for previous in db.scalars(
        select(AccountRecoveryChallenge)
        .where(
            AccountRecoveryChallenge.user_id == user.id,
            AccountRecoveryChallenge.consumed_at.is_(None),
            AccountRecoveryChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        previous.invalidated_at = now
    token = new_secret()
    challenge = AccountRecoveryChallenge(
        user_id=user.id,
        token_digest=secret_hash(token),
        expires_at=now + RECOVERY_CHALLENGE_LIFETIME,
    )
    db.add(challenge)
    db.flush()
    _create_identity_email(
        db,
        user_id=user.id,
        recipient=email,
        message_type="password_recovery",
        challenge_id=challenge.id,
        token=token,
        now=now,
    )
    db.commit()
    return {"accepted": True}


@router.post("/auth/recovery/confirm", response_model=RecoveryConfirmedResponse)
def confirm_account_recovery(
    payload: RecoveryConfirmInput,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _rate_limit(db, client_ip(request), "recovery-confirm", "all", 12)
    now = _now()
    challenge = db.scalar(
        select(AccountRecoveryChallenge)
        .where(AccountRecoveryChallenge.token_digest == secret_hash(payload.token))
        .with_for_update()
    )
    if challenge is None or not _active_challenge(challenge, now):
        fail(401, "recovery_invalid", "The recovery code is invalid or expired")
    user = db.scalar(select(User).where(User.id == challenge.user_id).with_for_update())
    contact = db.scalar(
        select(VerifiedEmailContact).where(VerifiedEmailContact.user_id == challenge.user_id)
    )
    if (
        user is None
        or user.status != "active"
        or contact is None
        or user.email != contact.email
    ):
        fail(401, "recovery_invalid", "The recovery code is invalid or expired")
    user.password_hash = hash_password(payload.new_password)
    challenge.consumed_at = now
    for previous in db.scalars(
        select(AccountRecoveryChallenge)
        .where(
            AccountRecoveryChallenge.user_id == user.id,
            AccountRecoveryChallenge.id != challenge.id,
            AccountRecoveryChallenge.consumed_at.is_(None),
            AccountRecoveryChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        previous.invalidated_at = now
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
        .with_for_update()
    ).all()
    for session in sessions:
        session.revoked_at = now
    db.commit()
    return {"ok": True}


@router.post(
    "/me/deletion-requests",
    response_model=AccountDeletionRequestedResponse,
    status_code=202,
)
def request_account_deletion(
    payload: AccountDeletionRequestInput,
    request: Request,
    response: Response,
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    _rate_limit(db, client_ip(request), "deletion", str(user.id), 3)
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    if locked_user.role == "admin":
        fail(409, "admin_handoff_required", "Transfer administrative access before deleting this account")
    if db.scalar(select(AccountDeletionRequest.id).where(AccountDeletionRequest.user_id == user.id)):
        fail(409, "deletion_already_requested", "Account deletion has already been requested")

    now = _now()
    sessions = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == locked_user.id, UserSession.revoked_at.is_(None))
        .with_for_update()
    ).all()
    for session in sessions:
        session.revoked_at = now
    listings = db.scalars(
        select(Listing)
        .where(Listing.owner_id == locked_user.id, Listing.status.in_(("active", "pending_review")))
        .with_for_update()
    ).all()
    for listing in listings:
        old_status = listing.status
        listing.status = "paused"
        db.add(
            ListingStatusEvent(
                listing_id=listing.id,
                actor_id=locked_user.id,
                actor_kind="user",
                from_status=old_status,
                to_status="paused",
                revision=listing.revision,
                reason="account deletion requested",
            )
        )
    for challenge in db.scalars(
        select(EmailVerificationChallenge)
        .where(
            EmailVerificationChallenge.user_id == locked_user.id,
            EmailVerificationChallenge.consumed_at.is_(None),
            EmailVerificationChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        challenge.invalidated_at = now
    for challenge in db.scalars(
        select(AccountRecoveryChallenge)
        .where(
            AccountRecoveryChallenge.user_id == locked_user.id,
            AccountRecoveryChallenge.consumed_at.is_(None),
            AccountRecoveryChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        challenge.invalidated_at = now
    locked_user.status = "deleted"
    deletion = AccountDeletionRequest(
        user_id=locked_user.id,
        status="requested",
        revoked_sessions=len(sessions),
        withdrawn_listings=len(listings),
        requested_at=now,
    )
    db.add(deletion)
    db.add(
        AuditEvent(
            actor_id=locked_user.id,
            entity_type="user",
            entity_id=locked_user.id,
            action="account.deletion_requested",
            details={"revoked_sessions": len(sessions), "withdrawn_listings": len(listings)},
        )
    )
    db.commit()
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.session_cookie_secure, samesite="lax")
    return {
        "status": "requested",
        "revoked_sessions": len(sessions),
        "withdrawn_listings": len(listings),
    }
