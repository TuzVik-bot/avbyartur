import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.auth import _public_session_id
from app.config import get_settings
from app.models import User, UserSession
from app.security import hash_password, new_secret, secret_hash

PASSWORD = "session-management-test-password"


def add_user(factory, email: str) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def add_session(factory, user_id, *, expires_at=None, revoked_at=None) -> str:
    raw_session = new_secret()
    with factory() as db:
        db.add(
            UserSession(
                token_hash=secret_hash(raw_session),
                csrf_hash=secret_hash(new_secret()),
                user_id=user_id,
                expires_at=expires_at or datetime.now(timezone.utc) + timedelta(days=2),
                revoked_at=revoked_at,
            )
        )
        db.commit()
    return raw_session


def client_for(integration) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver")


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def request_headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def test_session_list_contains_only_owned_live_sessions_and_marks_current(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, f"sessions-{uuid.uuid4().hex[:8]}@example.com")
    another_user = add_user(factory, f"other-{uuid.uuid4().hex[:8]}@example.com")
    active_other = add_session(factory, user.id)
    expired = add_session(factory, user.id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    revoked = add_session(factory, user.id, revoked_at=datetime.now(timezone.utc))
    foreign = add_session(factory, another_user.id)
    client = client_for(integration)
    login(client, user.email)

    response = client.get("/api/v1/me/sessions")

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "no-store"
    items = response.json()["items"]
    assert len(items) == 2
    assert sum(item["is_current"] for item in items) == 1
    assert next(item for item in items if item["is_current"])["id"]
    assert all(item["created_at"] for item in items)
    serialized = response.text
    current_raw = client.cookies.get(get_settings().session_cookie_name)
    current_csrf = client.cookies.get("avtorinok_csrf")
    assert current_raw is not None
    assert current_csrf is not None
    assert current_raw not in serialized
    assert current_csrf not in serialized
    now = datetime.now(timezone.utc)
    with factory() as db:
        live_owned_rows = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        ).all()
        expected_ids = {_public_session_id(row) for row in live_owned_rows}
        current_row = db.get(UserSession, secret_hash(current_raw))
        foreign_row = db.get(UserSession, secret_hash(foreign))
        assert current_row is not None and foreign_row is not None
        current_id = _public_session_id(current_row)
        foreign_id = _public_session_id(foreign_row)
        secret_hashes = {
            db.get(UserSession, secret_hash(raw)).token_hash
            for raw in (active_other, expired, revoked, foreign)
        }
        csrf_hashes = {
            row.csrf_hash
            for row in db.query(UserSession).filter(UserSession.user_id == user.id).all()
        }
    returned_ids = {item["id"] for item in items}
    assert returned_ids == expected_ids
    assert {item["id"] for item in items if item["is_current"]} == {current_id}
    assert foreign_id not in returned_ids
    assert not any(value in serialized for value in secret_hashes | csrf_hashes)


def test_delete_revokes_only_owned_session_and_stale_session_cannot_logout(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, f"delete-{uuid.uuid4().hex[:8]}@example.com")
    foreign_user = add_user(factory, f"delete-foreign-{uuid.uuid4().hex[:8]}@example.com")
    current_client = client_for(integration)
    current_csrf = login(current_client, user.email)
    other_client = client_for(integration)
    other_csrf = login(other_client, user.email)
    foreign_client = client_for(integration)
    foreign_csrf = login(foreign_client, foreign_user.email)
    listed = current_client.get("/api/v1/me/sessions").json()["items"]
    other_id = next(item["id"] for item in listed if not item["is_current"])
    other_raw = other_client.cookies.get(get_settings().session_cookie_name)

    foreign_delete = foreign_client.delete(
        f"/api/v1/me/sessions/{other_id}", headers=request_headers(foreign_csrf)
    )
    assert foreign_delete.status_code == 404
    assert other_client.get("/api/v1/me").status_code == 200

    deleted = current_client.delete(
        f"/api/v1/me/sessions/{other_id}", headers=request_headers(current_csrf)
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.headers.get("cache-control") == "no-store"
    assert current_client.get("/api/v1/me").status_code == 200
    assert other_client.get("/api/v1/me").status_code == 401
    stale_logout = other_client.post(
        "/api/v1/auth/logout", headers=request_headers(other_csrf), json={}
    )
    assert stale_logout.status_code == 401
    with factory() as db:
        revoked_row = db.get(UserSession, secret_hash(other_raw))
        assert revoked_row is not None and revoked_row.revoked_at is not None

    unknown = current_client.delete(
        f"/api/v1/me/sessions/{new_secret()}", headers=request_headers(current_csrf)
    )
    assert unknown.status_code == 404


def test_revoke_others_keeps_current_and_only_revokes_other_live_sessions(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, f"others-{uuid.uuid4().hex[:8]}@example.com")
    expired_raw = add_session(factory, user.id, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    old_revoked_raw = add_session(factory, user.id, revoked_at=datetime.now(timezone.utc))
    client = client_for(integration)
    csrf = login(client, user.email)
    second_client = client_for(integration)
    second_csrf = login(second_client, user.email)

    response = client.post(
        "/api/v1/me/sessions/revoke-others", headers=request_headers(csrf), json={}
    )

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == "no-store"
    assert response.json() == {"revoked_count": 1}
    assert client.get("/api/v1/me").status_code == 200
    assert second_client.get("/api/v1/me").status_code == 401
    assert second_client.post(
        "/api/v1/auth/logout", headers=request_headers(second_csrf), json={}
    ).status_code == 401
    with factory() as db:
        expired = db.get(UserSession, secret_hash(expired_raw))
        old_revoked = db.get(UserSession, secret_hash(old_revoked_raw))
        assert expired is not None and expired.revoked_at is None
        assert old_revoked is not None and old_revoked.revoked_at is not None


def test_all_session_management_writes_require_csrf(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, f"csrf-{uuid.uuid4().hex[:8]}@example.com")
    client = client_for(integration)
    login(client, user.email)
    current = next(
        item for item in client.get("/api/v1/me/sessions").json()["items"] if item["is_current"]
    )

    revoke_others = client.post("/api/v1/me/sessions/revoke-others", json={})
    revoke_one = client.delete(f"/api/v1/me/sessions/{current['id']}")

    assert revoke_others.status_code == 403
    assert revoke_one.status_code == 403
