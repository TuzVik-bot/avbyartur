import uuid

from fastapi.testclient import TestClient

from app import models
from app.main import app
from app.security import hash_password


PASSWORD = "saved-search-test-password-123"


def add_user(factory, email: str) -> models.User:
    user = models.User(
        email=email,
        display_name=email.split("@", 1)[0],
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


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_saved_search_crud_is_owner_scoped_and_revision_checked(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-owner-{uuid.uuid4().hex[:8]}@example.com")
    other = add_user(factory, f"saved-other-{uuid.uuid4().hex[:8]}@example.com")
    owner_client = TestClient(app, base_url="http://testserver")
    other_client = TestClient(app, base_url="http://testserver")
    owner_csrf = login(owner_client, owner.email)
    other_csrf = login(other_client, other.email)

    missing_key = owner_client.post(
        "/api/v1/me/saved-searches",
        json={"name": "BMW", "url": "/cars?q=bmw", "filters": {"q": "bmw"}},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert missing_key.status_code == 422
    assert missing_key.json()["code"] == "idempotency_required"

    created = owner_client.post(
        "/api/v1/me/saved-searches",
        json={
            "name": "  BMW   under 20k ",
            "url": "/cars?q=bmw&price_max=20000&currency=USD",
            "filters": {"q": "bmw", "price_max": "20000", "currency": "USD"},
            "notifications_enabled": True,
            "notification_channel": "email",
            "notification_frequency": "daily",
        },
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "saved-search-1"},
    )
    assert created.status_code == 200, created.text
    saved = created.json()["saved_search"]
    assert saved["name"] == "BMW under 20k"
    assert saved["status"] == "active"
    assert saved["revision"] == 1
    assert saved["notification"] == {"enabled": True, "channel": "email", "frequency": "daily"}

    replay = owner_client.post(
        "/api/v1/me/saved-searches",
        json={"name": "different payload", "url": "/cars", "filters": {}},
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "saved-search-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["saved_search"]["id"] == saved["id"]
    assert replay.json()["saved_search"]["name"] == saved["name"]

    foreign_patch = other_client.patch(
        f"/api/v1/me/saved-searches/{saved['id']}",
        json={"name": "stolen", "expected_revision": 1},
        headers={"X-CSRF-Token": other_csrf},
    )
    assert foreign_patch.status_code == 404

    no_csrf = owner_client.patch(
        f"/api/v1/me/saved-searches/{saved['id']}",
        json={"name": "renamed", "expected_revision": 1},
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["code"] == "csrf_failed"

    paused = owner_client.post(
        f"/api/v1/me/saved-searches/{saved['id']}/pause",
        json={"expected_revision": 1},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["saved_search"]["status"] == "paused"
    assert paused.json()["saved_search"]["revision"] == 2

    stale_resume = owner_client.post(
        f"/api/v1/me/saved-searches/{saved['id']}/resume",
        json={"expected_revision": 1},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert stale_resume.status_code == 409
    assert stale_resume.json()["code"] == "revision_conflict"

    resumed = owner_client.post(
        f"/api/v1/me/saved-searches/{saved['id']}/resume",
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["saved_search"]["status"] == "active"
    assert resumed.json()["saved_search"]["revision"] == 3

    updated = owner_client.patch(
        f"/api/v1/me/saved-searches/{saved['id']}",
        json={
            "url": "/cars?make_id=1",
            "filters": {"make_id": "1"},
            "notifications_enabled": False,
            "notification_channel": None,
            "expected_revision": 3,
        },
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["saved_search"]["revision"] == 4
    assert updated.json()["saved_search"]["notifications_enabled"] is False

    listed = owner_client.get("/api/v1/me/saved-searches")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [saved["id"]]

    deleted = owner_client.delete(
        f"/api/v1/me/saved-searches/{saved['id']}",
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert owner_client.get("/api/v1/me/saved-searches").json()["items"] == []


def test_saved_search_rejects_external_urls_unknown_filters_and_invalid_notification(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-validation-{uuid.uuid4().hex[:8]}@example.com")
    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, owner.email)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "saved-validation"}

    for payload in (
        {"name": "External", "url": "https://example.invalid/cars", "filters": {}},
        {"name": "Unknown", "url": "/cars", "filters": {"sql": "select 1"}},
        {
            "name": "No channel",
            "url": "/cars",
            "filters": {},
            "notifications_enabled": True,
        },
    ):
        response = client.post("/api/v1/me/saved-searches", json=payload, headers=headers)
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "validation_error"


def test_saved_search_rejects_mismatched_url_and_filters_on_create_and_update(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-mismatch-{uuid.uuid4().hex[:8]}@example.com")
    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, owner.email)
    headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "saved-mismatch"}

    created = client.post(
        "/api/v1/me/saved-searches",
        json={"name": "Cars", "url": "/cars?q=toyota", "filters": {"q": "toyota"}},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    saved_id = created.json()["saved_search"]["id"]

    for payload in (
        {"url": "/cars?q=honda", "filters": {"q": "toyota"}},
        {"url": "/cars?q=honda", "filters": {"q": "honda", "fuel": "diesel"}},
    ):
        response = client.patch(
            f"/api/v1/me/saved-searches/{saved_id}",
            json={**payload, "expected_revision": 1},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "invalid_category_filter"

    mismatch = client.post(
        "/api/v1/me/saved-searches",
        json={"name": "Wrong", "url": "/cars?q=toyota", "filters": {"q": "honda"}},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "saved-mismatch-create"},
    )
    assert mismatch.status_code == 422, mismatch.text
    assert mismatch.json()["code"] == "invalid_category_filter"


def test_saved_search_limit_is_enforced(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-limit-{uuid.uuid4().hex[:8]}@example.com")
    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, owner.email)

    from app.api import saved_searches

    class LimitedSettings:
        saved_search_limit = 1
        saved_search_mutations_per_hour = 60

    monkeypatch.setattr(saved_searches, "get_settings", lambda: LimitedSettings())
    first = client.post(
        "/api/v1/me/saved-searches",
        json={"name": "First", "url": "/cars", "filters": {}},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "saved-limit-1"},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/me/saved-searches",
        json={"name": "Second", "url": "/cars?q=skoda", "filters": {"q": "skoda"}},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "saved-limit-2"},
    )
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "saved_search_limit"
