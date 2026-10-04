"""Administrative access, reauthentication, audit and concurrency contracts."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent, User, UserSession
from app.cli import change_user_status
from app.security import hash_password

PASSWORD = "admin-management-test-password-123"


def add_user(factory, role="user", status="active", display_name="Участник"):
    user = User(
        email=f"admin-management-{uuid.uuid4().hex}@example.com",
        display_name=display_name,
        password_hash=hash_password(PASSWORD),
        role=role,
        status=status,
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def signed_client(integration, user):
    client = TestClient(integration["client"].app)
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def change_body(user, **changes):
    return {
        "role": user.role,
        "status": user.status,
        "expected_role": user.role,
        "expected_status": user.status,
        "reason": "Проверка обращения с подтверждённой причиной",
        "confirmation": "UPDATE_USER",
        "current_password": PASSWORD,
        **changes,
    }


def test_user_directory_requires_admin_and_returns_only_safe_paginated_fields(integration):
    factory = integration["SessionLocal"]
    admin = add_user(factory, role="admin")
    moderator = add_user(factory, role="moderator")
    ordinary = add_user(factory)
    guest = TestClient(integration["client"].app)
    assert guest.get("/api/v1/admin/users").status_code == 401
    for user in [moderator, ordinary]:
        client, _ = signed_client(integration, user)
        assert client.get("/api/v1/admin/users").status_code == 403
        assert client.get("/api/v1/admin/audit").status_code == 403
        assert client.get("/api/v1/admin/operations").status_code == 403
    client, _ = signed_client(integration, admin)
    response = client.get("/api/v1/admin/users", params={"page_size": 1, "role": "user"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["total"] == 1
    assert result["page"] == 1 and result["page_size"] == 1
    assert result["items"][0]["id"] == str(ordinary.id)
    assert set(result["items"][0]) == {"id", "email", "display_name", "role", "status", "created_at"}
    assert "password_hash" not in response.text
    assert "phone_e164" not in response.text
    assert PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/admin/users", params={"q": ordinary.email}).json()["total"] == 1
    assert client.get("/api/v1/admin/users", params={"page": 0}).status_code == 422


def test_block_requires_csrf_reauthentication_and_confirmation_and_revokes_sessions(integration):
    factory = integration["SessionLocal"]
    admin = add_user(factory, role="admin")
    target = add_user(factory)
    target_client, _ = signed_client(integration, target)
    client, headers = signed_client(integration, admin)
    endpoint = f"/api/v1/admin/users/{target.id}"
    body = change_body(target, status="blocked")
    assert client.patch(endpoint, json=body).status_code == 403
    bad_password = client.patch(endpoint, json={**body, "current_password": "wrong"}, headers=headers)
    assert bad_password.status_code == 401
    assert client.patch(endpoint, json={**body, "confirmation": ""}, headers=headers).status_code == 422
    assert client.patch(endpoint, json={**body, "reason": "   "}, headers=headers).status_code == 422
    response = client.patch(endpoint, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["changed"] is True
    assert response.json()["user"]["status"] == "blocked"
    assert target_client.get("/api/v1/me").status_code in {401, 403}
    with factory() as db:
        sessions = db.scalars(select(UserSession).where(UserSession.user_id == target.id)).all()
        assert sessions and all(s.revoked_at is not None for s in sessions)
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == target.id)).all()
        event = next(e for e in events if e.action == "admin_user_updated")
        assert event.actor_id == admin.id
        assert event.details["reason"] == body["reason"]
        assert event.details["from_status"] == "active"
        assert event.details["to_status"] == "blocked"
        assert "current_password" not in event.details


def test_role_changes_revoke_existing_sessions_and_stale_changes_are_rejected(integration):
    factory = integration["SessionLocal"]
    admin = add_user(factory, role="admin")
    target = add_user(factory)
    old_client, _ = signed_client(integration, target)
    client, headers = signed_client(integration, admin)
    endpoint = f"/api/v1/admin/users/{target.id}"
    body = change_body(target, role="moderator")
    first = client.patch(endpoint, json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["user"]["role"] == "moderator"
    assert old_client.get("/api/v1/me").status_code == 401
    second = client.patch(endpoint, json=change_body(target, status="blocked"), headers=headers)
    assert second.status_code == 409
    assert second.json()["code"] == "revision_conflict"
    with factory() as db:
        assert db.get(User, target.id).status == "active"
        assert db.get(User, target.id).role == "moderator"


def test_admin_cannot_remove_own_privileges_and_last_admin_stays_active(integration):
    admin = add_user(integration["SessionLocal"], role="admin")
    client, headers = signed_client(integration, admin)
    for changes in [{"status": "blocked"}, {"role": "user"}]:
        response = client.patch(f"/api/v1/admin/users/{admin.id}", json=change_body(admin, **changes), headers=headers)
        assert response.status_code == 409
    assert client.get("/api/v1/admin/users").status_code == 200


def test_noop_does_not_revoke_sessions_or_duplicate_audit(integration):
    factory = integration["SessionLocal"]
    admin = add_user(factory, role="admin")
    target = add_user(factory)
    target_client, _ = signed_client(integration, target)
    client, headers = signed_client(integration, admin)
    response = client.patch(f"/api/v1/admin/users/{target.id}", json=change_body(target), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["changed"] is False
    assert target_client.get("/api/v1/me").status_code == 200
    with factory() as db:
        assert db.scalars(select(AuditEvent).where(AuditEvent.entity_id == target.id)).all() == []


def test_concurrent_admin_demotions_cannot_remove_the_entire_admin_set(integration):
    factory = integration["SessionLocal"]
    first = add_user(factory, role="admin")
    second = add_user(factory, role="admin")
    first_client, first_headers = signed_client(integration, first)
    second_client, second_headers = signed_client(integration, second)
    ready = Barrier(2)

    def demote(client, headers, target):
        ready.wait(timeout=10)
        return client.patch(
            f"/api/v1/admin/users/{target.id}",
            json=change_body(target, role="user"), headers=headers,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(demote, first_client, first_headers, second)
        b = pool.submit(demote, second_client, second_headers, first)
        outcomes = [a.result(timeout=20), b.result(timeout=20)]
    assert outcomes.count(200) == 1
    assert all(status in {200, 401, 403, 409} for status in outcomes)
    with factory() as db:
        remaining = db.scalars(select(User).where(User.role == "admin", User.status == "active")).all()
        assert len(remaining) == 1


def test_cli_cannot_bypass_last_admin_or_self_block_protection(integration):
    factory = integration["SessionLocal"]
    first = add_user(factory, role="admin")
    with factory() as db:
        with pytest.raises(ValueError):
            change_user_status(db, first.id, "blocked", first.id, "Проверка защитного ограничения")
    second = add_user(factory, role="admin")
    with factory() as db:
        with pytest.raises(ValueError):
            change_user_status(db, second.id, "blocked", second.id, "Проверка защитного ограничения")
    with factory() as db:
        assert db.get(User, first.id).status == "active"
        assert db.get(User, second.id).status == "active"


def test_admin_audit_redacts_unknown_sensitive_details_and_operations_are_bounded(integration):
    factory = integration["SessionLocal"]
    admin = add_user(factory, role="admin")
    target = add_user(factory)
    with factory() as db:
        db.add(AuditEvent(actor_id=admin.id, entity_type="user", entity_id=target.id, action="test_event", details={
            "reason": "Безопасная причина", "password": "never-display-this", "token": "secret-token",
            "phone": "+375291234567", "nested": {"session_secret": "sensitive"},
        }))
        db.commit()
    client, _ = signed_client(integration, admin)
    response = client.get("/api/v1/admin/audit", params={"entity_type": "user", "entity_id": str(target.id)})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["details"] == {"reason": "Безопасная причина"}
    for secret in ["never-display-this", "secret-token", "+375291234567", "sensitive"]:
        assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    operations = client.get("/api/v1/admin/operations")
    assert operations.status_code == 200, operations.text
    result = operations.json()
    assert result["users_by_status"] == {"active": 2}
    assert result["listings_by_status"] == {}
    assert result["jobs_by_status"] == {}
    assert isinstance(result["capabilities"]["sms_login_enabled"], bool)
    assert "database_url" not in operations.text
    assert "session_secret" not in operations.text
