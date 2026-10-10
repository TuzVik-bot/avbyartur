import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_session_record,
    require_csrf,
    user_out,
)
from app.auth_schemas import (
    EmailRegistrationInput,
    UserSessionListOut,
    UserSessionRevokedOut,
    UserSessionsRevokedOut,
)
from app.config import get_settings
from app.db import get_db
from app.email_delivery import get_email_sender
from app.models import SmsOtpChallenge, User, UserConsent, UserSession
from app.email_registration_policy import email_registration_consent_error
from app.schemas import LoginInput
from app.security import (
    client_ip,
    hash_password,
    new_secret,
    normalize_email,
    secret_hash,
    verify_password,
)
from app.services import consume_rate_limit, fail
from app.sms_auth import (
    SmsCodeProvider,
    SmscSmsCodeProvider,
    UnconfiguredSmsCodeProvider,
    create_otp_code,
    digest_matches,
    idempotency_key_digest,
    normalize_belarus_mobile_phone,
    otp_code_digest,
    phone_subject_digest,
)
from app.sms_auth_schemas import (
    AuthCapabilitiesResponse,
    OtpAcceptedResponse,
    OtpCsrfResponse,
    OtpRegistrationRequestInput,
    OtpRequestInput,
    OtpVerifyInput,
)
from app.staff_schemas import AuthSessionResponse, LogoutResponse

router = APIRouter(prefix="/api/v1", tags=["authentication"])
CSRF_COOKIE = "avtorinok_csrf"


def _public_session_id(record: UserSession) -> str:
    """Return an opaque, non-reversible session locator for account management."""
    key = get_settings().session_secret.get_secret_value().encode()
    payload = b"avtorinok:account-session:v1:" + record.token_hash.encode()
    digest = hmac.new(key, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _prevent_session_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def get_sms_provider() -> SmsCodeProvider:
    """Build only the explicitly configured SMS provider."""
    settings = get_settings()
    if settings.sms_provider == "smsc":
        return SmscSmsCodeProvider(
            settings.smsc_api_key,
            sender=settings.smsc_sender,
            api_url=settings.smsc_api_url,
            timeout_seconds=settings.smsc_timeout_seconds,
        )
    return UnconfiguredSmsCodeProvider()


@router.get("/auth/capabilities", response_model=AuthCapabilitiesResponse)
def auth_capabilities(db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    settings = get_settings()
    sms_ready = settings.sms_login_enabled and get_sms_provider().is_configured
    email_ready = get_email_sender(settings).is_configured
    return {
        "email_registration_pilot": getattr(settings, "email_registration_enabled", False) and getattr(settings, "email_registration_pilot_enabled", False),
        "email_registration": settings.email_registration_enabled
        and email_registration_consent_error(
            db,
            settings,
            settings.registration_terms_version,
            settings.registration_privacy_version,
        )
        is None,
        "sms_login": sms_ready,
        "sms_registration": sms_ready and settings.public_registration_enabled,
        "email_notifications": email_ready and bool(settings.public_app_url),
        "test_mail": bool(getattr(settings, "test_mail_enabled", False)) and email_ready,
        "email_verification": email_ready,
        "password_recovery": email_ready,
    }


def _set_auth_cookies(response: Response, raw_session: str, raw_csrf: str) -> None:
    settings = get_settings()
    max_age = settings.session_days * 86400
    response.set_cookie(
        settings.session_cookie_name,
        raw_session,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        raw_csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def _create_session(db: Session, user: User, response: Response) -> str:
    # Serialize session creation with revoke-others for this account.
    user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if user is None or user.status != "active":
        fail(401, "invalid_session", "Authentication required")
    settings = get_settings()
    raw_session = new_secret()
    raw_csrf = new_secret()
    db.add(
        UserSession(
            token_hash=secret_hash(raw_session),
            csrf_hash=secret_hash(raw_csrf),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    _set_auth_cookies(response, raw_session, raw_csrf)
    return raw_csrf


def _require_pre_auth_csrf(request: Request, header_token: str | None) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token.encode(), header_token.encode())
    ):
        fail(403, "csrf_failed", "A valid CSRF token is required")


def _validated_idempotency_key(value: str | None) -> str:
    if (
        not value
        or not value.strip()
        or len(value) > 120
        or any(ord(character) < 0x20 for character in value)
    ):
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    return value.strip()


def _existing_otp_response(challenge: SmsOtpChallenge, response: Response) -> dict:
    if challenge.sent_at is None and not challenge.delivery_suppressed:
        # A challenge is committed before calling the vendor. If the process
        # stopped between those steps, or the vendor rejected delivery, the
        # OTP itself cannot be recovered from its HMAC digest. Do not claim a
        # successful retry; require a fresh idempotency key after cooldown.
        raise HTTPException(
            status_code=503,
            detail={
                "code": "sms_delivery_uncertain",
                "message": "SMS delivery status is unavailable; retry with a new request key after the resend cooldown",
                "field_errors": {},
            },
            headers={"Cache-Control": "no-store"},
        )
    _prevent_session_caching(response)
    return {"accepted": True}


def _normalize_phone_or_fail(value: str) -> str:
    try:
        return normalize_belarus_mobile_phone(value)
    except ValueError:
        fail(422, "invalid_phone", "Enter a supported Belarus mobile phone number", {"phone": "Invalid Belarus mobile number"})


def _otp_configuration_or_fail(*, registration: bool = False) -> None:
    settings = get_settings()
    if not settings.sms_login_enabled:
        fail(404, "not_found", "The requested authentication method is not available")
    if registration and not settings.public_registration_enabled:
        fail(404, "not_found", "The requested authentication method is not available")
    if registration and (
        not settings.registration_terms_version.strip()
        or not settings.registration_privacy_version.strip()
    ):
        fail(503, "sms_auth_unavailable", "SMS authentication is not available")


def _request_otp(
    *,
    phone_value: str,
    request: Request,
    response: Response,
    db: Session,
    provider: SmsCodeProvider,
    idempotency_key_value: str | None,
    purpose: str,
    display_name: str | None = None,
    terms_version: str | None = None,
    privacy_version: str | None = None,
) -> dict:
    registration = purpose == "registration"
    _otp_configuration_or_fail(registration=registration)
    if registration:
        consent_error = registration_consent_error(
            db,
            get_settings(),
            terms_version,
            privacy_version,
        )
        if consent_error == "unavailable":
            fail(503, "sms_auth_unavailable", "SMS authentication is not available")
        if consent_error == "mismatch":
            fail(409, "consent_version_mismatch", "Refresh the approved terms and privacy documents before continuing")
    if not provider.is_configured:
        fail(503, "sms_provider_unconfigured", "SMS authentication is not available")

    settings = get_settings()
    phone = _normalize_phone_or_fail(phone_value)
    idempotency_key = _validated_idempotency_key(idempotency_key_value)
    otp_secret = settings.sms_otp_secret.get_secret_value()
    phone_hash = phone_subject_digest(phone, otp_secret)
    idempotency_hash = idempotency_key_digest(phone, otp_secret, f"{purpose}:{idempotency_key}")

    existing_request = db.scalar(
        select(SmsOtpChallenge)
        .where(
            SmsOtpChallenge.phone_hash == phone_hash,
            SmsOtpChallenge.idempotency_key_hash == idempotency_hash,
        )
        .with_for_update()
    )
    if existing_request is not None:
        return _existing_otp_response(existing_request, response)

    now = datetime.now(timezone.utc)
    consume_rate_limit(
        db,
        "sms-otp-request-ip",
        client_ip(request),
        settings.sms_otp_ip_requests_per_hour,
        timedelta(hours=1),
    )
    consume_rate_limit(
        db,
        "sms-otp-request-phone-hour",
        phone_hash,
        settings.sms_otp_sends_per_hour,
        timedelta(hours=1),
    )
    consume_rate_limit(
        db,
        "sms-otp-request-phone-cooldown",
        phone_hash,
        1,
        timedelta(seconds=settings.sms_otp_resend_cooldown_seconds),
    )

    user = db.scalar(
        select(User).where(
            User.phone_e164 == phone,
            User.phone_verified_at.is_not(None),
        )
    )
    if user is None and not registration:
        # This is the same response returned after a delivery attempt. The
        # login route never reveals whether a number belongs to an account.
        # Store only a keyed phone hash and a keyed digest for the discarded
        # random value so idempotent retries behave exactly like sent requests.
        suppressed = SmsOtpChallenge(
            phone_hash=phone_hash,
            purpose="login",
            code_digest=otp_code_digest(phone, create_otp_code(), otp_secret),
            idempotency_key_hash=idempotency_hash,
            attempt_count=0,
            delivery_suppressed=True,
            expires_at=now + timedelta(seconds=settings.sms_otp_lifetime_seconds),
            invalidated_at=now,
        )
        db.add(suppressed)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            prior = db.scalar(
                select(SmsOtpChallenge).where(
                    SmsOtpChallenge.phone_hash == phone_hash,
                    SmsOtpChallenge.idempotency_key_hash == idempotency_hash,
                )
            )
            if prior is None:
                raise
        _prevent_session_caching(response)
        return {"accepted": True}

    actual_purpose = "login" if user is not None else "registration"
    code = create_otp_code()
    digest = otp_code_digest(phone, code, otp_secret)
    for active in db.scalars(
        select(SmsOtpChallenge)
        .where(
            SmsOtpChallenge.phone_hash == phone_hash,
            SmsOtpChallenge.consumed_at.is_(None),
            SmsOtpChallenge.invalidated_at.is_(None),
        )
        .with_for_update()
    ).all():
        active.invalidated_at = now

    challenge = existing_request
    if challenge is None:
        challenge = SmsOtpChallenge(
            phone_hash=phone_hash,
            purpose=actual_purpose,
            code_digest=digest,
            idempotency_key_hash=idempotency_hash,
            attempt_count=0,
            expires_at=now + timedelta(seconds=settings.sms_otp_lifetime_seconds),
        )
        db.add(challenge)
    else:
        challenge.purpose = actual_purpose
        challenge.code_digest = digest
        challenge.attempt_count = 0
        challenge.created_at = now
        challenge.sent_at = None
        challenge.delivery_suppressed = False
        challenge.delivery_failed = False
        challenge.expires_at = now + timedelta(seconds=settings.sms_otp_lifetime_seconds)
        challenge.consumed_at = None
        challenge.invalidated_at = None

    challenge.registration_display_name = (
        display_name.strip() if actual_purpose == "registration" and display_name else None
    )
    challenge.registration_terms_version = (
        terms_version.strip() if actual_purpose == "registration" and terms_version else None
    )
    challenge.registration_privacy_version = (
        privacy_version.strip() if actual_purpose == "registration" and privacy_version else None
    )
    try:
        db.commit()
    except IntegrityError:
        # Concurrent retries with the same idempotency key share the winner's
        # challenge. Only that request proceeds to the provider adapter.
        db.rollback()
        prior = db.scalar(
            select(SmsOtpChallenge).where(
                SmsOtpChallenge.phone_hash == phone_hash,
                SmsOtpChallenge.idempotency_key_hash == idempotency_hash,
            )
        )
        if prior is not None:
            return _existing_otp_response(prior, response)
        raise

    try:
        provider.send_code(phone, code, idempotency_key=idempotency_hash)
    except Exception:
        # Do not log adapter exceptions: an adapter may include the phone,
        # provider payload, or the OTP in its error text. Keep the same public
        # acknowledgement for known and unknown accounts; the user can retry
        # with a new idempotency key after the resend window.
        challenge.invalidated_at = datetime.now(timezone.utc)
        challenge.delivery_failed = True
        db.commit()
        _prevent_session_caching(response)
        return {"accepted": True}

    challenge.sent_at = datetime.now(timezone.utc)
    db.commit()
    _prevent_session_caching(response)
    return {"accepted": True}


def _require_email_registration_enabled() -> None:
    if not get_settings().email_registration_enabled:
        fail(404, "not_found", "Registration is not available")


@router.post("/auth/register", response_model=AuthSessionResponse, status_code=201,
             dependencies=[Depends(_require_email_registration_enabled)])
def register_email(
    payload: EmailRegistrationInput,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> dict:
    settings = get_settings()
    _prevent_session_caching(response)
    _require_pre_auth_csrf(request, x_csrf_token)
    consume_rate_limit(db, "email_registration_ip_v2", client_ip(request), 100, timedelta(hours=1))
    consume_rate_limit(db, "email_registration_address", normalize_email(str(payload.email)), 5, timedelta(hours=1))
    consent_error = email_registration_consent_error(db, settings, payload.terms_version, payload.privacy_version)
    if consent_error == "unavailable":
        fail(503, "registration_unavailable", "Registration documents are not available")
    if consent_error:
        fail(409, "consent_version_mismatch", "Refresh the page to accept the current documents")
    email = normalize_email(str(payload.email))
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        fail(409, "email_unavailable", "This email cannot be used; try signing in")
    user = User(email=email, display_name=payload.display_name,
                password_hash=hash_password(payload.password), role="user", status="active")
    try:
        db.add(user)
        db.flush()
        db.add_all([
            UserConsent(user_id=user.id, document_type="terms", version=payload.terms_version, source="email_registration"),
            UserConsent(user_id=user.id, document_type="privacy", version=payload.privacy_version, source="email_registration"),
        ])
        # Session creation commits the account, consents and session together.
        raw_csrf = _create_session(db, user, response)
    except IntegrityError:
        db.rollback()
        fail(409, "email_unavailable", "This email cannot be used; try signing in")
    return {"user": user_out(db, user), "csrf_token": raw_csrf}


@router.post("/auth/login", response_model=AuthSessionResponse)
def login(payload: LoginInput, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> dict:
    email = normalize_email(str(payload.email))
    user = db.scalar(select(User).where(User.email == email))
    password_valid = verify_password(payload.password, user.password_hash if user is not None else None)
    if user is None or user.status != "active" or not password_valid:
        consume_rate_limit(db, "login", f"{client_ip(request)}:{email}", 10, timedelta(minutes=15))
        fail(401, "invalid_credentials", "Email or password is incorrect")

    raw_csrf = _create_session(db, user, response)
    return {"user": user_out(db, user), "csrf_token": raw_csrf}


@router.get("/auth/otp/csrf", response_model=OtpCsrfResponse)
def otp_csrf(response: Response) -> dict:
    """Issue a same-origin double-submit token for the unauthenticated OTP flow."""
    settings = get_settings()
    token = new_secret()
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=900,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"csrf_token": token}


@router.post(
    "/auth/otp/request",
    response_model=OtpAcceptedResponse,
    status_code=202,
)
def request_login_otp(
    payload: OtpRequestInput,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[SmsCodeProvider, Depends(get_sms_provider)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    _require_pre_auth_csrf(request, csrf_token)
    return _request_otp(
        phone_value=payload.phone,
        request=request,
        response=response,
        db=db,
        provider=provider,
        idempotency_key_value=idempotency_key,
        purpose="login",
    )


@router.post(
    "/auth/register/otp/request",
    response_model=OtpAcceptedResponse,
    status_code=202,
)
def request_registration_otp(
    payload: OtpRegistrationRequestInput,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[SmsCodeProvider, Depends(get_sms_provider)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    _require_pre_auth_csrf(request, csrf_token)
    return _request_otp(
        phone_value=payload.phone,
        request=request,
        response=response,
        db=db,
        provider=provider,
        idempotency_key_value=idempotency_key,
        purpose="registration",
        display_name=payload.display_name,
        terms_version=payload.terms_version,
        privacy_version=payload.privacy_version,
    )


@router.post("/auth/otp/verify", response_model=AuthSessionResponse)
def verify_phone_otp(
    payload: OtpVerifyInput,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> dict:
    _require_pre_auth_csrf(request, csrf_token)
    _otp_configuration_or_fail()
    settings = get_settings()
    phone = _normalize_phone_or_fail(payload.phone)
    phone_hash = phone_subject_digest(phone, settings.sms_otp_secret.get_secret_value())
    now = datetime.now(timezone.utc)
    consume_rate_limit(
        db,
        "sms-otp-verify-ip",
        client_ip(request),
        settings.sms_otp_ip_verifications_per_hour,
        timedelta(hours=1),
    )
    consume_rate_limit(
        db,
        "sms-otp-verify-phone",
        phone_hash,
        settings.sms_otp_phone_verifications_per_hour,
        timedelta(hours=1),
    )

    challenge = db.scalar(
        select(SmsOtpChallenge)
        .where(
            SmsOtpChallenge.phone_hash == phone_hash,
            SmsOtpChallenge.sent_at.is_not(None),
            SmsOtpChallenge.consumed_at.is_(None),
            SmsOtpChallenge.invalidated_at.is_(None),
        )
        .order_by(SmsOtpChallenge.created_at.desc())
        .with_for_update()
    )
    if challenge is None:
        fail(401, "invalid_otp", "The code is invalid or expired")
    expires_at = challenge.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now or challenge.attempt_count >= settings.sms_otp_max_attempts:
        challenge.invalidated_at = now
        db.commit()
        fail(401, "invalid_otp", "The code is invalid or expired")

    expected_digest = otp_code_digest(
        phone,
        payload.code,
        settings.sms_otp_secret.get_secret_value(),
    )
    if not digest_matches(challenge.code_digest, expected_digest):
        challenge.attempt_count += 1
        if challenge.attempt_count >= settings.sms_otp_max_attempts:
            challenge.invalidated_at = now
        db.commit()
        fail(401, "invalid_otp", "The code is invalid or expired")

    if challenge.purpose == "registration":
        consent_error = registration_consent_error(
            db,
            settings,
            challenge.registration_terms_version,
            challenge.registration_privacy_version,
        )
        if consent_error is not None:
            challenge.invalidated_at = now
            db.commit()
            fail(503, "sms_auth_unavailable", "SMS authentication is not available")

    user = db.scalar(select(User).where(User.phone_e164 == phone).with_for_update())
    created_user = False
    if user is None:
        if (
            challenge.purpose != "registration"
            or not settings.public_registration_enabled
            or not challenge.registration_display_name
            or not challenge.registration_terms_version
            or not challenge.registration_privacy_version
        ):
            challenge.invalidated_at = now
            db.commit()
            fail(401, "invalid_otp", "The code is invalid or expired")
        try:
            with db.begin_nested():
                user = User(
                    email=None,
                    password_hash=None,
                    display_name=challenge.registration_display_name,
                    phone_e164=phone,
                    phone_verified_at=now,
                    role="user",
                    status="active",
                )
                db.add(user)
                db.flush()
        except IntegrityError:
            # Concurrent verified registration can win the unique phone key.
            # Authenticate the winner rather than attempt a duplicate account.
            user = db.scalar(select(User).where(User.phone_e164 == phone).with_for_update())
            if user is None:
                db.rollback()
                fail(401, "invalid_otp", "The code is invalid or expired")
        else:
            created_user = True

    if user is None or user.status != "active":
        challenge.invalidated_at = now
        db.commit()
        fail(401, "invalid_otp", "The code is invalid or expired")

    if created_user:
        db.add_all(
            [
                UserConsent(
                    user_id=user.id,
                    document_type="terms",
                    version=challenge.registration_terms_version,
                    source="sms_registration",
                ),
                UserConsent(
                    user_id=user.id,
                    document_type="privacy",
                    version=challenge.registration_privacy_version,
                    source="sms_registration",
                ),
            ]
        )
    challenge.consumed_at = now
    _prevent_session_caching(response)
    csrf = _create_session(db, user, response)
    return {"user": user_out(db, user), "csrf_token": csrf}


@router.post("/auth/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    record: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    record.revoked_at = datetime.now(timezone.utc)
    db.commit()
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/", secure=settings.session_cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.session_cookie_secure, samesite="lax")
    return {"ok": True}


@router.get("/me", response_model=AuthSessionResponse)
def me(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    record: Annotated[UserSession, Depends(get_session_record)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    return {"user": user_out(db, user), "csrf_token": request.cookies.get(CSRF_COOKIE, "")}


@router.get("/me/sessions", response_model=UserSessionListOut)
def list_sessions(
    response: Response,
    user: Annotated[User, Depends(get_current_user)],
    current: Annotated[UserSession, Depends(get_session_record)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    now = datetime.now(timezone.utc)
    records = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": _public_session_id(record),
                "created_at": record.created_at,
                "is_current": record.token_hash == current.token_hash,
            }
            for record in records
        ]
    }


@router.post("/me/sessions/revoke-others", response_model=UserSessionsRevokedOut)
def revoke_other_sessions(
    response: Response,
    current: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    locked_user = db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    if locked_user is None:
        fail(401, "invalid_session", "Authentication required")
    now = datetime.now(timezone.utc)
    records = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            UserSession.token_hash != current.token_hash,
        )
        .with_for_update()
    ).all()
    for record in records:
        record.revoked_at = now
    db.commit()
    return {"revoked_count": len(records)}


@router.delete("/me/sessions/{session_id}", response_model=UserSessionRevokedOut)
def revoke_session(
    session_id: str,
    response: Response,
    current: Annotated[UserSession, Depends(require_csrf)],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _prevent_session_caching(response)
    try:
        requested_id = session_id.encode("ascii")
    except UnicodeEncodeError:
        fail(404, "not_found", "Session not found")

    now = datetime.now(timezone.utc)
    records = db.scalars(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .with_for_update()
    ).all()
    record = next(
        (
            item
            for item in records
            if hmac.compare_digest(_public_session_id(item).encode("ascii"), requested_id)
        ),
        None,
    )
    if record is None:
        fail(404, "not_found", "Session not found")

    record.revoked_at = now
    db.commit()
    if record.token_hash == current.token_hash:
        settings = get_settings()
        response.delete_cookie(
            settings.session_cookie_name,
            path="/",
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite="lax",
        )
        response.delete_cookie(
            CSRF_COOKIE,
            path="/",
            secure=settings.session_cookie_secure,
            samesite="lax",
        )
    return {"ok": True}
