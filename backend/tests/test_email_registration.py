"""Email/password public registration.

These integration tests require the disposable PostgreSQL fixture in conftest.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.api import auth
from app.config import get_settings
from app.managed_content import ManagedContent
from app.security import verify_password

TERMS = "terms-test-v3"
PRIVACY = "privacy-test-v2"


def _configure(monkeypatch, *, enabled: bool = True):
    settings = get_settings().model_copy(
        update={
            "email_registration_enabled": enabled,
            "registration_terms_version": TERMS if enabled else "",
            "registration_privacy_version": PRIVACY if enabled else "",
            "session_cookie_secure": False,
        }
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    return settings


def _seed_documents(factory):
    with factory() as db:
        editor = models.User(email=f"editor-{uuid.uuid4().hex}@example.test", display_name="Editor", role="admin", status="active")
        db.add(editor)
        db.flush()
        for key, title, version in (("terms_of_use", "Условия", TERMS), ("privacy_policy", "Политика", PRIVACY)):
            db.add(ManagedContent(kind="legal_document", key=key, status="published", revision=1, updated_by=editor.id,
                                  payload={"title": title, "body": "Approved legal text " * 30, "document_version": version,
                                           "approved": True, "operator": {"legal_name": "Test Operator", "unp": "123456789",
                                                                             "address": "Test address", "contact_email": "operator@example.com"}}))
        db.commit()


def _client(app) -> TestClient:
    return TestClient(app, base_url="http://testserver")


def _register(client: TestClient, email: str, **overrides):
    csrf = client.get("/api/v1/auth/otp/csrf").json()["csrf_token"]
    payload = {
        "email": email,
        "password": "correct-horse-battery",
        "display_name": "  Новый пользователь  ",
        "accept_terms": True,
        "accept_privacy": True,
        "terms_version": TERMS,
        "privacy_version": PRIVACY,
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload, headers={"X-CSRF-Token": csrf})


def test_email_registration_is_disabled_by_default(integration, monkeypatch):
    _configure(monkeypatch, enabled=False)
    client = _client(integration["client"].app)

    assert client.get("/api/v1/auth/capabilities").json()["email_registration"] is False
    assert _register(client, "off@example.com").status_code == 404


def test_email_registration_creates_user_consents_and_session(integration, monkeypatch):
    _configure(monkeypatch)
    _seed_documents(integration["SessionLocal"])
    client = _client(integration["client"].app)
    assert client.get("/api/v1/auth/capabilities").json()["email_registration"] is True

    response = _register(client, "  New.User@Example.com ")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "new.user@example.com"
    assert body["user"]["display_name"] == "Новый пользователь"
    assert body["user"]["role"] == "user"
    assert client.get("/api/v1/me").status_code == 200
    with integration["SessionLocal"]() as db:
        user = db.scalar(select(models.User).where(models.User.email == "new.user@example.com"))
        assert user is not None and user.status == "active"
        assert verify_password("correct-horse-battery", user.password_hash)
        consents = db.scalars(select(models.UserConsent).where(models.UserConsent.user_id == user.id)).all()
        assert {(item.document_type, item.version, item.source) for item in consents} == {
            ("terms", TERMS, "email_registration"),
            ("privacy", PRIVACY, "email_registration"),
        }

    login = _client(integration["client"].app).post(
        "/api/v1/auth/login", json={"email": "new.user@example.com", "password": "correct-horse-battery"}
    )
    assert login.status_code == 200, login.text


def test_duplicate_email_is_rejected_without_a_second_account(integration, monkeypatch):
    _configure(monkeypatch)
    _seed_documents(integration["SessionLocal"])
    assert _register(_client(integration["client"].app), "twice@example.com").status_code == 201

    again = _register(_client(integration["client"].app), "TWICE@example.com")

    assert again.status_code == 409
    assert again.json()["code"] == "email_taken"
    with integration["SessionLocal"]() as db:
        assert len(db.scalars(select(models.User).where(models.User.email == "twice@example.com")).all()) == 1


def test_registration_requires_csrf_strong_password_and_current_consent(integration, monkeypatch):
    _configure(monkeypatch)
    _seed_documents(integration["SessionLocal"])
    client = _client(integration["client"].app)

    no_csrf = client.post("/api/v1/auth/register", json={
        "email": "nocsrf@example.com", "password": "correct-horse-battery", "display_name": "Без токена",
        "accept_terms": True, "accept_privacy": True, "terms_version": TERMS, "privacy_version": PRIVACY,
    })
    assert no_csrf.status_code == 403

    assert _register(client, "short@example.com", password="short").status_code == 422
    assert _register(client, "noconsent@example.com", accept_terms=False).status_code == 422
    stale = _register(client, "stale@example.com", terms_version="terms-old")
    assert stale.status_code == 409
    assert stale.json()["code"] == "consent_version_mismatch"
    with integration["SessionLocal"]() as db:
        assert db.scalar(select(models.User).where(models.User.email.in_(
            ["nocsrf@example.com", "short@example.com", "noconsent@example.com", "stale@example.com"]
        ))) is None


def test_registration_is_unavailable_without_published_documents(integration, monkeypatch):
    _configure(monkeypatch)
    client = _client(integration["client"].app)

    response = _register(client, "nodocs@example.com")

    assert response.status_code == 503
    assert response.json()["code"] == "registration_unavailable"
