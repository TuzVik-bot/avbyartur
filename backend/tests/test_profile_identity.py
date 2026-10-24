"""Profile identity changes and global notification delivery preferences."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta, timezone

from pydantic import SecretStr
from sqlalchemy import select

from app import models
from app.api import auth
from app.api import profile_identity as _profile_identity
from app.config import Settings
from app.identity_models import VerifiedEmailContact
from app.main import app
from app.profile_identity_schemas import NotificationPreferencesOut
from app.security import hash_password, new_secret, secret_hash
from fastapi.testclient import TestClient


class MemorySmsProvider:
    is_configured = True

    def __init__(self):
        self.messages: list[tuple[str, str, str]] = []

    def send_code(self, phone_e164: str, code: str, *, idempotency_key: str) -> None:
        self.messages.append((phone_e164, code, idempotency_key))

    def code_for(self, phone_e164: str) -> str:
        return next(code for phone, code, _key in self.messages if phone == phone_e164)


def _create_phone_user(factory, email: str, phone: str = "+375291234567") -> uuid.UUID:
    user = models.User(
        email=email,
        display_name="Identity Phone User",
        password_hash=hash_password("identity-phone-test-password-975"),
        phone_e164=phone,
        phone_verified_at=datetime.now(timezone.utc),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _login(integration, email: str):
    client = integration["client"]
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "identity-phone-test-password-975"},
    )
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _configure_phone_change(monkeypatch, provider: MemorySmsProvider) -> None:
    settings = Settings(
        sms_login_enabled=True,
        sms_otp_secret=SecretStr("identity-phone-test-secret-0123456789-abcdefghijkl"),
        sms_otp_lifetime_seconds=300,
        sms_otp_max_attempts=5,
        sms_otp_sends_per_hour=5,
        sms_otp_resend_cooldown_seconds=30,
        sms_otp_ip_requests_per_hour=30,
        sms_otp_ip_verifications_per_hour=30,
        sms_otp_phone_verifications_per_hour=10,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "get_sms_provider", lambda: provider)
    monkeypatch.setattr(_profile_identity, "get_settings", lambda: settings)

    # FastAPI retains the dependency function registered at router creation;
    # patch that captured seam for the existing auth router as well.
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for dependency in dependant.dependencies:
            if getattr(dependency.call, "__name__", "") == "get_sms_provider":
                monkeypatch.setitem(app.dependency_overrides, dependency.call, lambda: provider)
    monkeypatch.setitem(app.dependency_overrides, auth.get_sms_provider, lambda: provider)
    codes = iter(("111111", "222222"))
    monkeypatch.setattr(_profile_identity, "create_otp_code", lambda: next(codes))


def test_phone_change_routes_require_an_authenticated_user(integration):
    response = integration["client"].post(
        "/api/v1/me/profile/phone-change/request",
        json={"phone": "+375331234567"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "unauthorized"


def test_phone_change_requires_both_purpose_codes_then_revokes_all_sessions(integration, monkeypatch):
    factory = integration["SessionLocal"]
    email = f"phone-change-{uuid.uuid4().hex[:10]}@example.com"
    user_id = _create_phone_user(factory, email)
    client, csrf = _login(integration, email)
    provider = MemorySmsProvider()
    _configure_phone_change(monkeypatch, provider)

    with factory() as db:
        other_raw_session = new_secret()
        db.add(
            models.UserSession(
                token_hash=secret_hash(other_raw_session),
                csrf_hash=secret_hash(new_secret()),
                user_id=user_id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=2),
            )
        )
        db.commit()

    request_key = uuid.uuid4().hex
    requested = client.post(
        "/api/v1/me/profile/phone-change/request",
        json={"phone": "+375331234567"},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": request_key},
    )
    assert requested.status_code == 202, requested.text
    accepted = requested.json()
    assert accepted["accepted"] is True
    assert accepted["old_phone_masked"].endswith("67")
    assert accepted["new_phone_masked"].endswith("67")
    assert len(provider.messages) == 2
    repeated_request = client.post(
        "/api/v1/me/profile/phone-change/request",
        json={"phone": "+375331234567"},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": request_key},
    )
    assert repeated_request.status_code == 202, repeated_request.text
    assert repeated_request.json()["challenge_id"] == accepted["challenge_id"]
    assert len(provider.messages) == 2

    old_code = provider.code_for("+375291234567")
    new_code = provider.code_for("+375331234567")
    swapped = client.post(
        "/api/v1/me/profile/phone-change/confirm",
        json={"challenge_id": accepted["challenge_id"], "old_code": new_code, "new_code": old_code},
        headers={"X-CSRF-Token": csrf},
    )
    assert swapped.status_code == 401
    with factory() as db:
        assert db.get(models.User, user_id).phone_e164 == "+375291234567"

    confirmed = client.post(
        "/api/v1/me/profile/phone-change/confirm",
        json={"challenge_id": accepted["challenge_id"], "old_code": old_code, "new_code": new_code},
        headers={"X-CSRF-Token": csrf},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"changed": True}
    with factory() as db:
        user = db.get(models.User, user_id)
        assert user.phone_e164 == "+375331234567"
        assert user.phone_verified_at is not None
        sessions = db.scalars(select(models.UserSession).where(models.UserSession.user_id == user_id)).all()
        assert sessions and all(session.revoked_at is not None for session in sessions)

    repeated = client.post(
        "/api/v1/me/profile/phone-change/confirm",
        json={"challenge_id": accepted["challenge_id"], "old_code": old_code, "new_code": new_code},
        headers={"X-CSRF-Token": csrf},
    )
    assert repeated.status_code == 401
    assert client.get("/api/v1/me").status_code == 401


def test_phone_change_rejects_an_existing_account_number_before_sms(integration, monkeypatch):
    factory = integration["SessionLocal"]
    email = f"phone-taken-{uuid.uuid4().hex[:10]}@example.com"
    _create_phone_user(factory, email)
    _create_phone_user(factory, f"phone-owner-{uuid.uuid4().hex[:10]}@example.com", "+375331234567")
    client, csrf = _login(integration, email)
    provider = MemorySmsProvider()
    _configure_phone_change(monkeypatch, provider)

    response = client.post(
        "/api/v1/me/profile/phone-change/request",
        json={"phone": "+375331234567"},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid.uuid4().hex},
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "phone_in_use"
    assert provider.messages == []


def test_global_notification_preferences_are_explicitly_opted_out_and_versioned(integration):
    factory = integration["SessionLocal"]
    email = f"notification-preferences-{uuid.uuid4().hex[:10]}@example.com"
    user_id = _create_phone_user(factory, email)
    client, csrf = _login(integration, email)

    initial = client.get("/api/v1/me/notification-preferences")
    assert initial.status_code == 200, initial.text
    assert initial.json() == {
        "preferences": {
            "web_enabled": True,
            "email_enabled": True,
            "revision": 0,
            "email_verified": False,
            "email_delivery_configured": False,
        }
    }
    from app import profile_identity_service as service
    with factory() as db:
        assert service.notification_delivery_allowed(db, user_id, "web") is True
        assert service.notification_delivery_allowed(db, user_id, "email") is True

    opted_out = client.put(
        "/api/v1/me/notification-preferences",
        json={"web_enabled": False, "email_enabled": False, "expected_revision": 0},
        headers={"X-CSRF-Token": csrf},
    )
    assert opted_out.status_code == 200, opted_out.text
    assert opted_out.json()["preferences"]["revision"] == 1

    with factory() as db:
        db.add(VerifiedEmailContact(user_id=user_id, email=email, verified_at=datetime.now(timezone.utc)))
        db.commit()
    enabled = client.put(
        "/api/v1/me/notification-preferences",
        json={"web_enabled": False, "email_enabled": True, "expected_revision": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["preferences"] == {
        "web_enabled": False,
        "email_enabled": True,
        "revision": 2,
        "email_verified": True,
        "email_delivery_configured": False,
    }

    stale = client.put(
        "/api/v1/me/notification-preferences",
        json={"web_enabled": True, "email_enabled": False, "expected_revision": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"

    with factory() as db:
        assert service.notification_delivery_allowed(db, user_id, "web") is False
        assert service.notification_delivery_allowed(db, user_id, "email") is True


def test_notification_preferences_contract_exposes_email_delivery_capability():
    preferences = NotificationPreferencesOut(
        web_enabled=True,
        email_enabled=True,
        revision=0,
        email_verified=False,
        email_delivery_configured=True,
    )

    assert preferences.email_delivery_configured is True


def _legal_document_payload(version: str, *, approved: bool = True) -> dict:
    return {
        "title": "Условия использования",
        "body": "Утверждённый текст правил и порядка обработки информации. " * 4,
        "document_version": version,
        "approved": approved,
        "operator": {
            "legal_name": "Тестовый оператор",
            "unp": "123456789",
            "address": "Тестовый адрес, Минск",
            "contact_email": "operator@example.com",
        },
    }


def test_registration_requires_matching_approved_published_document_versions(integration, monkeypatch):
    from app.managed_content import ManagedContent
    from app.profile_identity_service import registration_consent_error

    factory = integration["SessionLocal"]
    actor_id = _create_phone_user(factory, f"legal-author-{uuid.uuid4().hex[:10]}@example.com")
    settings = Settings(
        sms_login_enabled=True,
        public_registration_enabled=True,
        sms_otp_secret=SecretStr("identity-registration-test-secret-0123456789-abcdefgh"),
        registration_terms_version="terms-test-v3",
        registration_privacy_version="privacy-test-v2",
        session_cookie_secure=False,
    )
    provider = MemorySmsProvider()
    captured_sms_provider = auth.get_sms_provider
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "get_sms_provider", lambda: provider)
    monkeypatch.setattr(_profile_identity, "get_settings", lambda: settings)

    # Dependency overrides use the captured dependency function, independent
    # of FastAPI's lazy included-router representation.
    monkeypatch.setitem(app.dependency_overrides, captured_sms_provider, lambda: provider)

    with factory() as db:
        db.add_all(
            [
                ManagedContent(
                    kind="legal_document",
                    key="terms_of_use",
                    payload=_legal_document_payload("terms-test-v3"),
                    status="published",
                    revision=1,
                    updated_by=actor_id,
                ),
                ManagedContent(
                    kind="legal_document",
                    key="privacy_policy",
                    payload=_legal_document_payload("privacy-test-v2"),
                    status="published",
                    revision=1,
                    updated_by=actor_id,
                ),
            ]
        )
        db.commit()

    client = integration["client"]
    csrf = client.get("/api/v1/auth/otp/csrf").json()["csrf_token"]
    request_payload = {
        "phone": "+375251234567",
        "display_name": "New Registration",
        "accept_terms": True,
        "accept_privacy": True,
        "terms_version": "terms-test-v2",
        "privacy_version": "privacy-test-v2",
    }
    mismatch = client.post(
        "/api/v1/auth/register/otp/request",
        json=request_payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert mismatch.status_code == 409, mismatch.text
    assert mismatch.json()["code"] == "consent_version_mismatch"
    assert provider.messages == []

    request_payload["terms_version"] = "terms-test-v3"
    accepted = client.post(
        "/api/v1/auth/register/otp/request",
        json=request_payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert accepted.status_code == 202, accepted.text
    assert len(provider.messages) == 1

    with factory() as db:
        terms = db.scalar(
            select(ManagedContent).where(ManagedContent.key == "terms_of_use")
        )
        terms.payload = _legal_document_payload("terms-test-v4")
        db.commit()

    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": "+375251234567", "code": provider.messages[0][1]},
        headers={"X-CSRF-Token": csrf},
    )
    assert verified.status_code == 503
    assert verified.json()["code"] == "sms_auth_unavailable"
    with factory() as db:
        assert db.scalar(
            select(models.User.id).where(models.User.phone_e164 == "+375251234567")
        ) is None


def test_two_verified_accounts_cannot_claim_same_phone_or_return_internal_error(integration, monkeypatch):
    factory = integration["SessionLocal"]
    accounts = []
    provider = MemorySmsProvider()
    _configure_phone_change(monkeypatch, provider)
    codes = iter(("111111", "222222", "333333", "444444"))
    monkeypatch.setattr(_profile_identity, "create_otp_code", lambda: next(codes))
    for index, old_phone in enumerate(("+375291234560", "+375291234561")):
        email = f"claim-{index}-{uuid.uuid4().hex[:8]}@example.com"
        _create_phone_user(factory, email, old_phone)
        client = TestClient(app)
        login = client.post("/api/v1/auth/login", json={"email": email, "password": "identity-phone-test-password-975"})
        csrf = login.json()["csrf_token"]
        request = client.post("/api/v1/me/profile/phone-change/request", json={"phone": "+375331234569"},
                              headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid.uuid4().hex})
        assert request.status_code == 202, request.text
        old_code, new_code = provider.messages[-2][1], provider.messages[-1][1]
        accounts.append((client, csrf, request.json()["challenge_id"], old_code, new_code))
    ready = Barrier(2)

    def confirm(account):
        client, csrf, challenge_id, old_code, new_code = account
        ready.wait(timeout=10)
        result = client.post("/api/v1/me/profile/phone-change/confirm", json={"challenge_id": challenge_id, "old_code": old_code, "new_code": new_code},
                             headers={"X-CSRF-Token": csrf})
        return result.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(confirm, accounts))
    assert sorted(results) == [200, 409]
    with factory() as db:
        assert len(db.scalars(select(models.User).where(models.User.phone_e164 == "+375331234569")).all()) == 1


def test_phone_unique_conflict_rolls_back_changes_and_returns_stable_409(integration, monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError
    from types import SimpleNamespace
    factory = integration["SessionLocal"]
    email = f"claim-conflict-{uuid.uuid4().hex[:8]}@example.com"
    user_id = _create_phone_user(factory, email)
    provider = MemorySmsProvider(); _configure_phone_change(monkeypatch, provider)
    client, csrf = _login(integration, email)
    request = client.post("/api/v1/me/profile/phone-change/request", json={"phone": "+375331234569"},
                          headers={"X-CSRF-Token": csrf, "Idempotency-Key": uuid.uuid4().hex})
    assert request.status_code == 202, request.text
    commit = Session.commit
    failures = []

    def conflict_once(db):
        if not failures and any(isinstance(row, models.User) and row.phone_e164 == "+375331234569" for row in db.dirty):
            failures.append(True)
            original = Exception("unique constraint violation")
            original.diag = SimpleNamespace(constraint_name="uq_user_phone_e164")
            raise IntegrityError("UPDATE users", {}, original)
        return commit(db)

    monkeypatch.setattr(Session, "commit", conflict_once)
    no_raise = TestClient(app, raise_server_exceptions=False)
    no_raise.cookies.update(client.cookies)
    result = no_raise.post("/api/v1/me/profile/phone-change/confirm", json={"challenge_id": request.json()["challenge_id"], "old_code": provider.messages[0][1], "new_code": provider.messages[1][1]}, headers={"X-CSRF-Token": csrf})
    assert result.status_code == 409, result.text
    assert result.json()["code"] == "phone_in_use"
    with factory() as db:
        assert db.get(models.User, user_id).phone_e164 == "+375291234567"
    assert client.get("/api/v1/me").status_code == 200
