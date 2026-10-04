"""Focused contract tests for the gated, provider-agnostic SMS auth core.

These integration tests require the disposable PostgreSQL fixture in conftest.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable
from fastapi.testclient import TestClient

from app import models
from app.api import auth
from app.config import get_settings
from app.sms_auth import (
    idempotency_key_digest,
    normalize_belarus_mobile_phone,
    otp_code_digest,
    phone_subject_digest,
)


def _unique_phone() -> str:
    suffix = int(uuid.uuid4().hex[:7], 16) % 10_000_000
    return f"+37529{suffix:07d}"


class FakeSmsProvider:
    is_configured = True

    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []
        self.fail_with_sensitive_error = False

    def send_code(self, phone_e164: str, code: str, *, idempotency_key: str) -> None:
        self.sent.append((phone_e164, code, idempotency_key))
        if self.fail_with_sensitive_error:
            raise RuntimeError(f"failed for {phone_e164} with OTP {code}")


def _configure_auth(monkeypatch, app, *, registration: bool = False, provider=None):
    settings = get_settings().model_copy(
        update={
            "sms_login_enabled": True,
            "public_registration_enabled": registration,
            "sms_otp_secret": SecretStr("sms-otp-test-secret-that-is-long-enough"),
            "registration_terms_version": "terms-test-v3" if registration else "",
            "registration_privacy_version": "privacy-test-v2" if registration else "",
            "session_cookie_secure": False,
        }
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    if provider is not None:
        monkeypatch.setitem(app.dependency_overrides, auth.get_sms_provider, lambda: provider)
    return settings


def _client(app) -> TestClient:
    return TestClient(app, base_url="http://testserver")


def _csrf(client: TestClient) -> str:
    response = client.get("/api/v1/auth/otp/csrf")
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _request_code(client: TestClient, phone: str, *, registration: bool = False, csrf: str | None = None, key: str | None = None):
    is_registration = registration
    payload = {"phone": phone}
    if is_registration:
        payload.update(
            {
                "display_name": "SMS Pilot User",
                "accept_terms": True,
                "accept_privacy": True,
                "terms_version": "terms-test-v3",
                "privacy_version": "privacy-test-v2",
            }
        )
    return client.post(
        "/api/v1/auth/register/otp/request" if is_registration else "/api/v1/auth/otp/request",
        json=payload,
        headers={
            "X-CSRF-Token": csrf or _csrf(client),
            "Idempotency-Key": key or uuid.uuid4().hex,
        },
    )


def _seed_registration_documents(factory):
    from app.managed_content import ManagedContent
    with factory() as db:
        for key, title, version in (("terms_of_use", "Условия", "terms-test-v3"), ("privacy_policy", "Политика", "privacy-test-v2")):
            db.add(ManagedContent(kind="legal_document", key=key, status="published", revision=1,
                                  updated_by=_add_phone_user(factory, _unique_phone()).id,
                                  payload={"title": title, "body": "Approved legal text " * 30, "document_version": version,
                                           "approved": True, "operator": {"legal_name": "Test Operator", "unp": "123456789",
                                                                             "address": "Test address", "contact_email": "operator@example.com"}}))
        db.commit()


def _error_without_request_id(response):
    return {key: value for key, value in response.json().items() if key != "request_id"}


def _verify(client: TestClient, phone: str, code: str, csrf: str):
    return client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": code},
        headers={"X-CSRF-Token": csrf},
    )


def _add_phone_user(factory, phone: str) -> models.User:
    user = models.User(
        email=f"otp-{uuid.uuid4().hex}@example.test",
        display_name="Existing Phone User",
        password_hash="existing-password-hash",
        phone_e164=phone,
        phone_verified_at=datetime.now(timezone.utc),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+375 (29) 123-45-67", "+375291234567"),
        ("029 123 45 67", "+375291234567"),
        ("333456789", "+375333456789"),
    ],
)
def test_belarus_mobile_number_normalizes_to_e164(raw, expected):
    assert normalize_belarus_mobile_phone(raw) == expected


def test_landline_and_unsupported_mobile_prefix_are_rejected():
    with pytest.raises(ValueError):
        normalize_belarus_mobile_phone("+375 17 222-33-44")
    with pytest.raises(ValueError):
        normalize_belarus_mobile_phone("+375 21 123-45-67")


def test_phone_format_constraint_is_postgresql_only():
    sqlite_ddl = str(CreateTable(models.User.__table__).compile(dialect=sqlite.dialect()))
    postgres_ddl = str(CreateTable(models.User.__table__).compile(dialect=postgresql.dialect()))

    assert "phone_e164 ~" not in sqlite_ddl
    assert "phone_e164 ~" in postgres_ddl


def test_sms_login_flag_is_off_by_default_and_provider_is_not_configured(integration, monkeypatch):
    app = integration["client"].app
    client = _client(app)
    token = _csrf(client)

    disabled = _request_code(client, "+375 (29) 123-45-67", csrf=token)
    assert disabled.status_code == 404

    _configure_auth(monkeypatch, app)
    known_phone = _unique_phone()
    _add_phone_user(integration["SessionLocal"], known_phone)
    unknown = _request_code(client, "+375333456789", csrf=token)
    known = _request_code(client, known_phone, csrf=token)

    assert unknown.status_code == known.status_code == 503
    assert _error_without_request_id(unknown) == _error_without_request_id(known)


def test_unknown_login_phone_gets_same_ack_without_sending(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    _configure_auth(monkeypatch, app, provider=provider)
    known_phone = _unique_phone()
    _add_phone_user(integration["SessionLocal"], known_phone)
    client = _client(app)
    csrf = _csrf(client)

    known = _request_code(client, known_phone, csrf=csrf)
    unknown_phone = _unique_phone()
    unknown_key = uuid.uuid4().hex
    unknown = _request_code(client, unknown_phone, csrf=csrf, key=unknown_key)
    unknown_retry = _request_code(client, unknown_phone, csrf=csrf, key=unknown_key)

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"accepted": True}
    assert unknown_retry.status_code == 202
    assert unknown_retry.json() == {"accepted": True}
    assert len(provider.sent) == 1
    assert provider.sent[0][0] == known_phone
    with integration["SessionLocal"]() as db:
        suppressed = db.scalar(
            select(models.SmsOtpChallenge).where(
                models.SmsOtpChallenge.phone_hash
                == phone_subject_digest(unknown_phone, "sms-otp-test-secret-that-is-long-enough")
            )
        )
        assert suppressed is not None and suppressed.delivery_suppressed
        assert len(suppressed.phone_hash) == 64


def test_delivery_error_is_sanitized_and_uncertain_retry_fails_closed(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    provider.fail_with_sensitive_error = True
    _configure_auth(monkeypatch, app, provider=provider)
    phone = _unique_phone()
    _add_phone_user(integration["SessionLocal"], phone)
    client = _client(app)
    csrf = _csrf(client)
    key = uuid.uuid4().hex

    known = _request_code(client, phone, csrf=csrf, key=key)
    known_retry = _request_code(client, phone, csrf=csrf, key=key)
    unknown_phone = _unique_phone()
    unknown_key = uuid.uuid4().hex
    unknown = _request_code(client, unknown_phone, csrf=csrf, key=unknown_key)
    unknown_retry = _request_code(client, unknown_phone, csrf=csrf, key=unknown_key)

    assert known.status_code == unknown.status_code == unknown_retry.status_code == 202
    assert known.json() == unknown.json() == unknown_retry.json() == {"accepted": True}
    assert known_retry.status_code == 503
    assert known_retry.headers.get("cache-control") == "no-store"
    assert "accepted" not in known_retry.json()
    assert len(provider.sent) == 1
    assert phone not in known.text and phone not in known_retry.text
    assert provider.sent[0][1] not in known.text and provider.sent[0][1] not in known_retry.text
    with integration["SessionLocal"]() as db:
        failed = db.scalar(
            select(models.SmsOtpChallenge).where(
                models.SmsOtpChallenge.phone_hash
                == phone_subject_digest(phone, "sms-otp-test-secret-that-is-long-enough")
            )
        )
        assert failed is not None and failed.delivery_failed


def test_duplicate_idempotency_key_fails_closed_for_unsent_challenge(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    settings = _configure_auth(monkeypatch, app, provider=provider)
    phone = _unique_phone()
    key = uuid.uuid4().hex
    secret = settings.sms_otp_secret.get_secret_value()
    challenge = models.SmsOtpChallenge(
        phone_hash=phone_subject_digest(phone, secret),
        purpose="login",
        code_digest=otp_code_digest(phone, "123456", secret),
        idempotency_key_hash=idempotency_key_digest(phone, secret, f"login:{key}"),
        attempt_count=0,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    with integration["SessionLocal"]() as db:
        db.add(challenge)
        db.commit()

    client = _client(app)
    response = _request_code(client, phone, csrf=_csrf(client), key=key)

    assert response.status_code == 503
    assert "accepted" not in response.json()
    assert provider.sent == []


def test_wrong_code_exhausts_attempt_budget_and_blocks_valid_code(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    _configure_auth(monkeypatch, app, provider=provider)
    phone = _unique_phone()
    _add_phone_user(integration["SessionLocal"], phone)
    client = _client(app)
    csrf = _csrf(client)
    assert _request_code(client, phone, csrf=csrf).status_code == 202
    valid_code = provider.sent[0][1]

    for _ in range(5):
        assert _verify(client, phone, "000000" if valid_code != "000000" else "000001", csrf).status_code == 401
    rejected = _verify(client, phone, valid_code, csrf)

    assert rejected.status_code == 401
    assert client.get("/api/v1/me").status_code == 401
    with integration["SessionLocal"]() as db:
        challenge = db.scalar(
            select(models.SmsOtpChallenge).where(
                models.SmsOtpChallenge.phone_hash
                == phone_subject_digest(phone, "sms-otp-test-secret-that-is-long-enough")
            )
        )
        assert challenge is not None and challenge.attempt_count == 5
        assert len(challenge.code_digest) == 64
        assert challenge.code_digest != valid_code


def test_expired_code_is_rejected_without_creating_a_session(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    _configure_auth(monkeypatch, app, provider=provider)
    phone = _unique_phone()
    _add_phone_user(integration["SessionLocal"], phone)
    client = _client(app)
    csrf = _csrf(client)
    assert _request_code(client, phone, csrf=csrf).status_code == 202
    with integration["SessionLocal"]() as db:
        challenge = db.scalar(
            select(models.SmsOtpChallenge).where(
                models.SmsOtpChallenge.phone_hash
                == phone_subject_digest(phone, "sms-otp-test-secret-that-is-long-enough")
            )
        )
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    response = _verify(client, phone, provider.sent[0][1], csrf)

    assert response.status_code == 401
    assert client.get("/api/v1/me").status_code == 401


def test_sms_registration_records_configured_consent_and_creates_secure_session(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    _configure_auth(monkeypatch, app, registration=True, provider=provider)
    _seed_registration_documents(integration["SessionLocal"])
    phone = _unique_phone()
    client = _client(app)
    csrf = _csrf(client)
    requested = _request_code(client, phone, registration=True, csrf=csrf)
    assert requested.status_code == 202, requested.text

    verified = _verify(client, phone, provider.sent[0][1], csrf)

    assert verified.status_code == 200, verified.text
    assert verified.json()["user"]["display_name"] == "SMS Pilot User"
    assert verified.json()["user"]["email"] is None
    assert client.get("/api/v1/me").status_code == 200
    assert get_settings().session_cookie_name in client.cookies
    with integration["SessionLocal"]() as db:
        user = db.scalar(select(models.User).where(models.User.phone_e164 == phone))
        assert user is not None and user.phone_verified_at is not None
        consents = db.scalars(select(models.UserConsent).where(models.UserConsent.user_id == user.id)).all()
        assert {(item.document_type, item.version) for item in consents} == {
            ("terms", "terms-test-v3"),
            ("privacy", "privacy-test-v2"),
        }
        assert db.scalar(select(models.UserSession).where(models.UserSession.user_id == user.id)) is not None

    replay = _verify(client, phone, provider.sent[0][1], verified.json()["csrf_token"])
    assert replay.status_code == 401
    with integration["SessionLocal"]() as db:
        assert db.scalar(select(models.User.id).where(models.User.phone_e164 == phone)) is not None
        assert len(db.scalars(select(models.UserSession).where(models.UserSession.user_id == user.id)).all()) == 1


def test_resend_idempotency_and_per_phone_cooldown(integration, monkeypatch):
    app = integration["client"].app
    provider = FakeSmsProvider()
    _configure_auth(monkeypatch, app, provider=provider)
    phone = _unique_phone()
    _add_phone_user(integration["SessionLocal"], phone)
    client = _client(app)
    csrf = _csrf(client)
    key = uuid.uuid4().hex

    first = _request_code(client, phone, csrf=csrf, key=key)
    duplicate = _request_code(client, phone, csrf=csrf, key=key)
    too_soon = _request_code(client, phone, csrf=csrf, key=uuid.uuid4().hex)

    assert first.status_code == duplicate.status_code == 202
    assert duplicate.json() == {"accepted": True}
    assert too_soon.status_code == 429
    assert len(provider.sent) == 1


def test_phone_uniqueness_is_enforced_by_database(integration):
    factory = integration["SessionLocal"]
    phone = _unique_phone()
    _add_phone_user(factory, phone)

    with pytest.raises(IntegrityError):
        with factory() as db:
            db.add(
                models.User(
                    email=f"duplicate-{uuid.uuid4().hex}@example.test",
                    display_name="Duplicate Phone User",
                    password_hash="not-a-real-password-hash",
                    phone_e164=phone,
                    phone_verified_at=datetime.now(timezone.utc),
                    role="user",
                    status="active",
                )
            )
            db.commit()


def test_registration_route_stays_disabled_until_separately_enabled(integration, monkeypatch):
    app = integration["client"].app
    settings = get_settings().model_copy(update={"sms_login_enabled": True, "public_registration_enabled": False})
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    client = _client(app)

    response = _request_code(client, "+375291234567", registration=True)

    assert response.status_code == 404
