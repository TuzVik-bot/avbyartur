"""Runtime quota changes are versioned and actually affect application limits."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import pytest

from app.models import AuditEvent, User
from app.security import hash_password

PASSWORD = "runtime-settings-test-password-123"


def client_for(integration, role="admin"):
    user = User(email=f"settings-{uuid.uuid4().hex}@example.com", display_name="Настройки", role=role,
                status="active", password_hash=hash_password(PASSWORD))
    with integration["SessionLocal"]() as db:
        db.add(user); db.commit(); db.refresh(user); db.expunge(user)
    client = TestClient(integration["client"].app)
    login = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client, {"X-CSRF-Token": login.json()["csrf_token"]}


def change(value, expected_revision=0, **extra):
    return {"value": value, "expected_revision": expected_revision, "reason": "Изменение согласованной квоты",
            "current_password": PASSWORD, "confirmation": "UPDATE_SETTING", **extra}


def test_runtime_setting_changes_have_audit_and_reject_stale_updates(integration):
    client, headers = client_for(integration)
    response = client.get("/api/v1/admin/settings")
    assert response.status_code == 200, response.text
    settings = {row["key"]: row for row in response.json()["items"]}
    assert settings["private_listing_quota"]["value"] == 5
    assert settings["company_listing_quota"]["value"] == 50
    assert settings["private_listing_quota"]["revision"] == 0
    endpoint = "/api/v1/admin/settings/private_listing_quota"
    assert client.patch(endpoint, json=change(2)).status_code == 403
    assert client.patch(endpoint, json=change(2, current_password="wrong"), headers=headers).status_code == 401
    result = client.patch(endpoint, json=change(2), headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["setting"]["value"] == 2
    assert result.json()["setting"]["revision"] == 1
    assert client.patch(endpoint, json=change(4), headers=headers).status_code == 409
    with integration["SessionLocal"]() as db:
        from app.runtime_settings import runtime_limit
        assert runtime_limit(db, "private_listing_quota") == 2
        assert runtime_limit(db, "company_listing_quota") == 50
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == "runtime_setting_updated")).all()
        assert len(events) == 1
        assert events[0].details["key"] == "private_listing_quota"
        assert events[0].details["before"] == 5 and events[0].details["after"] == 2


def test_runtime_settings_accept_only_bounded_supported_values(integration):
    client, headers = client_for(integration)
    endpoint = "/api/v1/admin/settings/private_listing_quota"
    for value in [0, -1, 10001, "5", True]:
        assert client.patch(endpoint, json=change(value), headers=headers).status_code == 422
    assert client.patch("/api/v1/admin/settings/session_secret", json=change(4), headers=headers).status_code == 404
    assert client.patch(endpoint, json=change(3, reason=" "), headers=headers).status_code == 422


def test_runtime_settings_are_not_exposed_to_regular_users(integration):
    client, headers = client_for(integration, role="user")
    assert client.get("/api/v1/admin/settings").status_code == 403
    assert client.patch("/api/v1/admin/settings/private_listing_quota", json=change(3), headers=headers).status_code == 403


def test_lowered_saved_search_limit_blocks_new_records_without_hiding_existing_ones(integration):
    owner, owner_headers = client_for(integration, role="user")
    for index in range(2):
        response = owner.post("/api/v1/me/saved-searches", json={"name": f"Поиск {index}", "url": "/cars", "filters": {}},
                              headers={**owner_headers, "Idempotency-Key": f"runtime-saved-{index}"})
        assert response.status_code == 200, response.text
    admin, admin_headers = client_for(integration)
    response = admin.patch("/api/v1/admin/settings/saved_search_limit", json=change(1), headers=admin_headers)
    assert response.status_code == 200, response.text
    created = owner.post("/api/v1/me/saved-searches", json={"name": "За пределом лимита", "url": "/cars", "filters": {}},
                         headers={**owner_headers, "Idempotency-Key": "runtime-saved-rejected"})
    assert created.status_code == 409
    assert created.json()["code"] == "saved_search_limit"
    listing = owner.get("/api/v1/me/saved-searches")
    assert listing.status_code == 200 and len(listing.json()["items"]) == 2


def test_runtime_setting_database_rejects_invalid_values_keys_and_revisions(integration):
    from app.runtime_settings import RuntimeSetting

    for key, value, revision in [("session_secret", 2, 1), ("private_listing_quota", 0, 1),
                                 ("company_listing_quota", 10001, 1), ("saved_search_limit", 5, 0)]:
        with integration["SessionLocal"]() as db:
            db.add(RuntimeSetting(key=key, value=value, revision=revision))
            with pytest.raises(IntegrityError):
                db.commit()


def test_runtime_setting_audit_explains_setting_identity_and_value_change(integration):
    client, headers = client_for(integration)
    updated = client.patch("/api/v1/admin/settings/private_listing_quota", json=change(2), headers=headers)
    assert updated.status_code == 200, updated.text
    response = client.get("/api/v1/admin/audit", params={"entity_type": "runtime_setting"})
    assert response.status_code == 200, response.text
    details = response.json()["items"][0]["details"]
    assert details["key"] == "private_listing_quota"
    assert details["before"] == 5 and details["after"] == 2
    with integration["SessionLocal"]() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.action == "runtime_setting_updated"))
        event.details = {"key": "session_secret", "before": "hidden-before", "after": "hidden-after", "reason": "Безопасная причина"}
        db.commit()
    scrubbed = client.get("/api/v1/admin/audit", params={"entity_type": "runtime_setting"})
    assert "hidden-before" not in scrubbed.text and "hidden-after" not in scrubbed.text
    assert "session_secret" not in scrubbed.text


def test_environment_quota_values_have_same_bounds_as_runtime_overrides():
    from app.config import Settings
    from pydantic import ValidationError
    for key in ("private_listing_quota", "company_listing_quota", "saved_search_limit"):
        for value in (0, -1, 10001):
            with pytest.raises(ValidationError):
                Settings(_env_file=None, **{key: value})


def test_runtime_limit_rejects_invalid_explicit_fallback():
    from app.runtime_settings import runtime_limit
    for fallback in (0, -1, 10001, True):
        with pytest.raises(RuntimeError):
            runtime_limit(None, "private_listing_quota", fallback=fallback)
