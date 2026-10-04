import sys
import uuid

import pytest

from app import cli
from app.models import AuditEvent, User, UserSession
from app.security import hash_password


PASSWORD = "cli-test-password-123"


def add_user(factory, *, role: str = "user", status: str = "active") -> User:
    user = User(
        email=f"cli-{uuid.uuid4().hex}@example.com",
        display_name="CLI test user",
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


def set_status(monkeypatch, user_id: uuid.UUID, status: str, actor_id: uuid.UUID, reason: str) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "avtorinok-admin",
            "set-user-status",
            "--user-id",
            str(user_id),
            "--status",
            status,
            "--actor-id",
            str(actor_id),
            "--reason",
            reason,
        ],
    )
    return cli.main()


def test_status_command_requires_an_explicit_actor(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(
        sys,
        "argv",
        ["avtorinok-admin", "set-user-status", "--user-id", str(user_id), "--status", "blocked", "--reason", "fraud"],
    )
    monkeypatch.setattr(cli, "SessionLocal", lambda: pytest.fail("database must not be opened"))

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2


def test_status_command_rejects_blank_reason_without_opening_database(monkeypatch, capsys):
    monkeypatch.setattr(cli, "SessionLocal", lambda: pytest.fail("database must not be opened"))

    result = set_status(monkeypatch, uuid.uuid4(), "blocked", uuid.uuid4(), "  \t")

    assert result == 2
    assert "non-empty reason" in capsys.readouterr().err


def test_status_command_authorizes_audit_logs_and_revokes_sessions(integration, monkeypatch, capsys):
    factory = integration["SessionLocal"]
    target = add_user(factory)
    admin = add_user(factory, role="admin")
    inactive_admin = add_user(factory, role="admin", status="blocked")
    ordinary_user = add_user(factory)
    client = integration["client"]

    login = client.post("/api/v1/auth/login", json={"email": target.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    assert client.get("/api/v1/me").status_code == 200
    monkeypatch.setattr(cli, "SessionLocal", factory)

    assert set_status(monkeypatch, target.id, "blocked", ordinary_user.id, "policy violation") == 2
    assert "active admin" in capsys.readouterr().err
    assert set_status(monkeypatch, target.id, "blocked", inactive_admin.id, "policy violation") == 2
    assert "active admin" in capsys.readouterr().err

    reason = "Repeated fraudulent listing reports"
    assert set_status(monkeypatch, target.id, "blocked", admin.id, f"  {reason}  ") == 0
    assert client.get("/api/v1/me").status_code == 401
    with factory() as db:
        blocked_user = db.get(User, target.id)
        old_sessions = db.query(UserSession).filter(UserSession.user_id == target.id).all()
        block_event = db.query(AuditEvent).filter(
            AuditEvent.entity_type == "user", AuditEvent.entity_id == target.id
        ).one()
        assert blocked_user.status == "blocked"
        assert old_sessions and all(session.revoked_at is not None for session in old_sessions)
        assert block_event.actor_id == admin.id
        assert block_event.action == "blocked"
        assert block_event.details == {"reason": reason}

    assert set_status(monkeypatch, target.id, "active", admin.id, "Review completed") == 0
    assert client.get("/api/v1/me").status_code == 401
    with factory() as db:
        events = db.query(AuditEvent).filter(
            AuditEvent.entity_type == "user", AuditEvent.entity_id == target.id
        ).order_by(AuditEvent.created_at, AuditEvent.action).all()
        assert [(event.action, event.details["reason"]) for event in events] == [
            ("blocked", reason),
            ("unblocked", "Review completed"),
        ]
        assert all(event.actor_id == admin.id for event in events)

    renewed_login = client.post("/api/v1/auth/login", json={"email": target.email, "password": PASSWORD})
    assert renewed_login.status_code == 200, renewed_login.text
    assert client.get("/api/v1/me").status_code == 200
