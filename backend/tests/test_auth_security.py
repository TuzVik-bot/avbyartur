import uuid
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from types import SimpleNamespace

import pytest
from app.config import Settings, get_settings
from app.models import Listing, User, UserSession
from app.schemas import LoginInput
from app.security import hash_password, new_secret, secret_hash
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from pydantic import ValidationError

PASSWORD = "security-test-password-123"


def add_user(factory, email: str, role: str = "user") -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(PASSWORD),
        role=role,
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def add_listing(factory, owner_id, *, status: str = "draft", revision: int = 1) -> Listing:
    listing = Listing(
        owner_id=owner_id,
        slug=f"security-{uuid.uuid4().hex}",
        status=status,
        revision=revision,
        submitted_revision=revision if status == "pending_review" else None,
        title="Security regression listing",
        description="Original description",
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def login(client, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _auth_login_harness(monkeypatch, user, *, verifier=None):
    from app.api import auth

    events = []
    counts = {}

    class StubDb:
        def scalar(self, query):
            return user

        def add(self, record):
            pass

        def commit(self):
            pass

    def tracked_verify(password, stored_hash):
        events.append(("verify", stored_hash))
        if verifier is not None:
            return verifier(password, stored_hash)
        return user is not None and user.status == "active" and stored_hash == "stored" and password == PASSWORD

    def tracked_rate_limit(db, namespace, subject, limit, period):
        events.append(("limit", namespace))
        assert namespace == "login"
        assert limit == 10
        assert period == timedelta(minutes=15)
        key = (namespace, subject)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > limit:
            raise HTTPException(status_code=429)

    monkeypatch.setattr(auth, "client_ip", lambda request: "203.0.113.42")
    monkeypatch.setattr(auth, "verify_password", tracked_verify)
    monkeypatch.setattr(auth, "consume_rate_limit", tracked_rate_limit)
    monkeypatch.setattr(auth, "secret_hash", lambda value: f"hashed-{value}")
    monkeypatch.setattr(auth, "user_out", lambda db, record: {"email": record.email})
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(session_cookie_secure=False))

    def attempt(email, password):
        try:
            auth.login(LoginInput(email=email, password=password), object(), Response(), StubDb())
            return 200
        except HTTPException as error:
            return error.status_code

    return attempt, counts, events


@pytest.mark.parametrize("role", ["moderator", "admin"])
@pytest.mark.parametrize(
    ("method", "path", "payload", "headers"),
    [
        ("patch", "/api/v1/listings/{listing_id}", {"expected_revision": 1, "description": "Changed by staff"}, {}),
        ("post", "/api/v1/listings/{listing_id}/submit", {"expected_revision": 1}, {"Idempotency-Key": "staff-submit"}),
        ("post", "/api/v1/listings/{listing_id}/pause", {"expected_revision": 1}, {}),
        ("post", "/api/v1/listings/{listing_id}/resume", {"expected_revision": 1}, {}),
        ("post", "/api/v1/listings/{listing_id}/sold", {"expected_revision": 1}, {}),
    ],
)
def test_staff_cannot_use_seller_listing_mutations(integration, role, method, path, payload, headers):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"owner-{uuid.uuid4().hex[:8]}@example.com")
    staff = add_user(factory, f"{role}-{uuid.uuid4().hex[:8]}@example.com", role=role)
    listing = add_listing(factory, owner.id)

    client = TestClient(integration["client"].app, base_url="http://testserver")
    csrf = login(client, staff.email)
    request_headers = {"X-CSRF-Token": csrf, **headers}
    response = getattr(client, method)(
        path.format(listing_id=listing.id),
        json=payload,
        headers=request_headers,
    )

    assert response.status_code == 404, response.text
    with factory() as db:
        persisted = db.get(Listing, listing.id)
        assert persisted is not None
        assert persisted.status == "draft"
        assert persisted.revision == 1
        assert persisted.description == "Original description"


def test_moderator_can_view_and_approve_pending_listing(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"pending-owner-{uuid.uuid4().hex[:8]}@example.com")
    moderator = add_user(factory, f"pending-mod-{uuid.uuid4().hex[:8]}@example.com", role="moderator")
    listing = add_listing(factory, owner.id, status="pending_review")
    client = TestClient(integration["client"].app, base_url="http://testserver")
    csrf = login(client, moderator.email)

    detail = client.get(f"/api/v1/listings/{listing.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["listing"]["status"] == "pending_review"

    approved = client.post(
        f"/api/v1/moderation/listings/{listing.id}/approve",
        json={"expected_revision": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["listing"]["status"] == "active"


def test_ten_failed_logins_do_not_block_correct_password(monkeypatch):
    email = f"limited-{uuid.uuid4().hex[:8]}@example.com"
    user = SimpleNamespace(id=uuid.uuid4(), email=email, password_hash="stored", status="active")
    attempt, counts, _ = _auth_login_harness(monkeypatch, user)
    for _ in range(10):
        assert attempt(email, "wrong-password") == 401

    correct = attempt(email, PASSWORD)

    assert correct == 200
    assert counts[("login", f"203.0.113.42:{email}")] == 10


def test_successful_logins_do_not_increment_failed_attempt_quota(monkeypatch):
    email = f"success-quota-{uuid.uuid4().hex[:8]}@example.com"
    user = SimpleNamespace(id=uuid.uuid4(), email=email, password_hash="stored", status="active")
    attempt, counts, _ = _auth_login_harness(monkeypatch, user)

    for _ in range(10):
        assert attempt(email, PASSWORD) == 200

    assert counts == {}

    for _ in range(10):
        assert attempt(email, "wrong-password") == 401

    blocked = attempt(email, "wrong-password")
    assert blocked == 429


def test_wrong_credentials_are_rate_limited_after_ten_failures(monkeypatch):
    email = f"limited-wrong-{uuid.uuid4().hex[:8]}@example.com"
    user = SimpleNamespace(id=uuid.uuid4(), email=email, password_hash="stored", status="active")
    attempt, _, events = _auth_login_harness(monkeypatch, user)

    statuses = [attempt(email, "wrong-password") for _ in range(11)]

    assert statuses == [401] * 10 + [429]
    assert events == [(event, value) for _ in range(11) for event, value in (("verify", "stored"), ("limit", "login"))]


def test_unknown_email_still_uses_dummy_password_verification(monkeypatch):
    from app.security import verify_password

    email = f"missing-{uuid.uuid4().hex[:8]}@example.com"
    verified_hashes = []

    def verify_unknown(password, stored_hash):
        verified_hashes.append(stored_hash)
        return verify_password(password, stored_hash)

    attempt, _, events = _auth_login_harness(monkeypatch, None, verifier=verify_unknown)
    status = attempt(email, PASSWORD)

    assert status == 401
    assert verified_hashes == [None]
    assert events == [("verify", None), ("limit", "login")]


def test_production_requires_secure_session_cookies():
    production_secret = "production-test-secret-with-at-least-32-characters"
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE"):
        Settings(app_env="production", session_secret=production_secret, session_cookie_secure=False)

    assert Settings(app_env="production", session_secret=production_secret, session_cookie_secure=True)
    assert Settings(app_env="development", session_cookie_secure=False).session_cookie_secure is False


@pytest.mark.parametrize("app_env", ["staging", "prodution", ""])
def test_unknown_app_env_is_rejected(app_env):
    with pytest.raises(ValidationError, match="APP_ENV"):
        Settings(app_env=app_env)


@pytest.mark.parametrize("app_env", ["PROD", " production "])
def test_production_app_env_aliases_are_normalized(app_env):
    settings = Settings(
        app_env=app_env,
        session_secret="production-test-secret-with-at-least-32-characters",
        session_cookie_secure=True,
    )

    assert settings.app_env == "production"


def test_login_sets_session_and_csrf_cookie_security_attributes(integration, monkeypatch):
    from app.api import auth

    factory = integration["SessionLocal"]
    user = add_user(factory, f"cookie-{uuid.uuid4().hex[:8]}@example.com")
    client = TestClient(integration["client"].app, base_url="http://testserver")
    cookie_settings = Settings(
        app_env="production",
        session_secret="cookie-test-secret-with-at-least-32-characters",
        session_cookie_secure=True,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: cookie_settings)

    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200, response.text
    cookies = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookies.load(header)

    session_cookie = cookies[cookie_settings.session_cookie_name]
    assert session_cookie["httponly"] is True
    assert session_cookie["secure"] is True
    assert session_cookie["samesite"] == "lax"
    assert session_cookie["path"] == "/"
    assert session_cookie["max-age"] == "604800"

    csrf_cookie = cookies["avtorinok_csrf"]
    assert csrf_cookie["httponly"] == ""
    assert csrf_cookie["secure"] is True
    assert csrf_cookie["samesite"] == "lax"
    assert csrf_cookie["path"] == "/"
    assert csrf_cookie["max-age"] == "604800"


def test_expired_server_side_session_is_rejected(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, f"expired-{uuid.uuid4().hex[:8]}@example.com")
    raw_session = new_secret()
    with factory() as db:
        db.add(UserSession(
            token_hash=secret_hash(raw_session),
            csrf_hash=secret_hash(new_secret()),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ))
        db.commit()

    client = TestClient(integration["client"].app, base_url="http://testserver")
    client.cookies.set(get_settings().session_cookie_name, raw_session)

    response = client.get("/api/v1/me")

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "session_expired"


def test_logout_revokes_current_session(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, f"logout-{uuid.uuid4().hex[:8]}@example.com")
    client = TestClient(integration["client"].app, base_url="http://testserver")

    login_response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login_response.status_code == 200, login_response.text
    raw_session = client.cookies.get(get_settings().session_cookie_name)
    assert raw_session is not None
    csrf_token = login_response.json()["csrf_token"]

    logout_response = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert logout_response.status_code == 200, logout_response.text
    assert logout_response.json() == {"ok": True}
    assert client.get("/api/v1/me").status_code == 401
    with factory() as db:
        session = db.get(UserSession, secret_hash(raw_session))
        assert session is not None
        assert session.revoked_at is not None


def test_public_registration_is_not_exposed(integration):
    client = TestClient(integration["client"].app, base_url="http://testserver")

    response = client.post("/api/v1/auth/register", json={})

    assert response.status_code == 404


def test_phone_reveal_rate_limit_is_per_account_not_shared_ip(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"phone-owner-{uuid.uuid4().hex[:8]}@example.com")
    first_user = add_user(factory, f"phone-first-{uuid.uuid4().hex[:8]}@example.com")
    second_user = add_user(factory, f"phone-second-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id, status="active")
    app = integration["client"].app
    shared_ip = ("198.51.100.42", 54000)
    first_client = TestClient(app, base_url="http://testserver", client=shared_ip)
    second_client = TestClient(app, base_url="http://testserver", client=shared_ip)
    first_csrf = login(first_client, first_user.email)
    second_csrf = login(second_client, second_user.email)

    for _ in range(30):
        response = first_client.post(
            f"/api/v1/listings/{listing.id}/phone-reveal",
            headers={"X-CSRF-Token": first_csrf},
        )
        assert response.status_code == 200, response.text

    blocked = first_client.post(
        f"/api/v1/listings/{listing.id}/phone-reveal",
        headers={"X-CSRF-Token": first_csrf},
    )
    assert blocked.status_code == 429, blocked.text

    shared_ip_user = second_client.post(
        f"/api/v1/listings/{listing.id}/phone-reveal",
        headers={"X-CSRF-Token": second_csrf},
    )
    assert shared_ip_user.status_code == 200, shared_ip_user.text
    assert shared_ip_user.json()["phone"] == listing.contact_phone

    other_ip_client = TestClient(app, base_url="http://testserver", client=("198.51.100.43", 54000))
    other_ip_csrf = login(other_ip_client, first_user.email)
    other_ip = other_ip_client.post(
        f"/api/v1/listings/{listing.id}/phone-reveal",
        headers={"X-CSRF-Token": other_ip_csrf},
    )
    assert other_ip.status_code == 429, other_ip.text


def test_phone_reveal_rate_limit_uses_account_id(monkeypatch):
    from app.api import listings as listings_api
    from starlette.responses import Response

    rate_limits = []
    listing = SimpleNamespace(id=uuid.uuid4(), owner_id=uuid.uuid4(), company_id=None, status="active", contact_phone="+375291234567")
    user = SimpleNamespace(id=uuid.uuid4())

    class StubDb:
        def get(self, model, listing_id):
            return listing

        def add(self, record):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(listings_api, "listing_is_public", lambda db, item: True)
    monkeypatch.setattr(listings_api, "client_ip", lambda request: "203.0.113.42")
    monkeypatch.setattr(
        listings_api,
        "consume_rate_limit",
        lambda db, namespace, subject, limit, period: rate_limits.append((namespace, subject, limit, period)),
    )

    monkeypatch.setattr(listings_api, "_lock_public_active_listing", lambda *args, **kwargs: listing)
    result = listings_api.reveal_phone(
        listing_id=listing.id, request=object(), response=Response(),
        user=user, csrf=SimpleNamespace(token_hash="opaque-test-session"), db=StubDb(),
    )

    assert result == {"phone": listing.contact_phone}
    assert rate_limits == [("phone-reveal", str(user.id), 30, timedelta(hours=1))]
