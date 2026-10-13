import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.api.saved_searches import SavedSearchCreate
from app.main import app
from app.security import hash_password


PASSWORD = "saved-search-test-password-123"


def test_saved_search_create_canonicalizes_url_and_derives_filters_from_it():
    payload = SavedSearchCreate(
        name="  Audi   Q5 ",
        url="/cars?year_min=2020&q=Audi&page=3&page_size=50&sort=newest&price_max=25000&currency=USD",
        filters={"q": "Audi", "year_min": "2020", "price_max": 25000, "currency": "USD", "sort": "newest"},
    )

    assert payload.url == "/cars?currency=USD&price_max=25000&q=Audi&sort=newest&year_min=2020"
    assert payload.filters == {"currency": "USD", "price_max": 25000, "q": "Audi", "sort": "newest", "year_min": 2020}
    assert payload.notifications_enabled is False
    assert payload.notification_channel is None


def test_saved_search_create_accepts_semantically_equal_numeric_filters():
    payload = SavedSearchCreate(
        name="Audi under 25k",
        url="/cars?price_max=20000&currency=USD&year_min=2020",
        filters={"price_max": 20000, "currency": "USD", "year_min": "2020"},
    )

    assert payload.filters == {"currency": "USD", "price_max": 20000, "year_min": 2020}


def test_saved_search_create_normalizes_supported_category_filter():
    payload = SavedSearchCreate(
        name="Грузовики",
        url="/trucks?category_code=TRUCKS",
        filters={"category_code": "trucks"},
    )

    assert payload.url == "/trucks?category_code=trucks"
    assert payload.filters == {"category_code": "trucks"}

    with pytest.raises(ValidationError, match="category_code"):
        SavedSearchCreate(name="Самолёты", url="/cars?category_code=aircraft", filters={})


def test_saved_search_create_rejects_different_numeric_filters():
    with pytest.raises(ValidationError, match="contradict"):
        SavedSearchCreate(
            name="Audi under 25k",
            url="/cars?price_max=20000&currency=USD",
            filters={"price_max": 25000, "currency": "USD"},
        )


def test_saved_search_create_rejects_filters_that_contradict_url():
    with pytest.raises(ValidationError, match="contradict"):
        SavedSearchCreate(name="Audi", url="/cars?make_id=audi", filters={"make_id": "bmw"})


def test_saved_search_create_requires_explicit_subscription_after_save():
    with pytest.raises(ValidationError, match="subscribe"):
        SavedSearchCreate(
            name="Audi",
            url="/cars?q=audi",
            filters={"q": "audi"},
            notifications_enabled=True,
            notification_channel="web",
        )


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
            "url": "/cars?currency=USD&price_max=20000&q=bmw",
            "filters": {"q": "bmw", "price_max": "20000", "currency": "USD"},
        },
        headers={"X-CSRF-Token": owner_csrf, "Idempotency-Key": "saved-search-1"},
    )
    assert created.status_code == 200, created.text
    saved = created.json()["saved_search"]
    assert saved["name"] == "BMW under 20k"
    assert saved["status"] == "active"
    assert saved["revision"] == 1
    assert saved["notification"] == {"enabled": False, "channel": None, "frequency": "daily"}

    subscribed = owner_client.patch(
        f"/api/v1/me/saved-searches/{saved['id']}",
        json={"notifications_enabled": True, "notification_channel": "web", "notification_frequency": "daily", "expected_revision": 1},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert subscribed.status_code == 200, subscribed.text
    saved = subscribed.json()["saved_search"]
    assert saved["revision"] == 2
    assert saved["notification"] == {"enabled": True, "channel": "web", "frequency": "daily"}

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
        json={"expected_revision": 2},
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert paused.status_code == 200, paused.text
    assert paused.json()["saved_search"]["status"] == "paused"
    assert paused.json()["saved_search"]["revision"] == 3
    with factory() as db:
        assert db.get(models.SavedSearch, uuid.UUID(saved["id"])).subscription_started_at is None

    stale_resume = owner_client.post(
        f"/api/v1/me/saved-searches/{saved['id']}/resume",
        json={"expected_revision": 2},
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
    assert resumed.json()["saved_search"]["revision"] == 4
    with factory() as db:
        assert db.get(models.SavedSearch, uuid.UUID(saved["id"])).subscription_started_at is not None

    updated = owner_client.patch(
        f"/api/v1/me/saved-searches/{saved['id']}",
        json={
            "url": "/cars?make_id=1",
            "filters": {"make_id": "1"},
            "notifications_enabled": False,
            "notification_channel": None,
            "expected_revision": 4,
        },
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["saved_search"]["revision"] == 5
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


def test_email_subscription_and_resume_require_configured_verified_delivery(
    integration, monkeypatch
):
    from app.identity_models import VerifiedEmailContact
    from app.api import saved_searches

    class MemoryEmailSender:
        is_configured = False

    class Settings:
        public_app_url = "https://cars.example.test"
        saved_search_limit = 20
        saved_search_mutations_per_hour = 60

    sender = MemoryEmailSender()
    settings = Settings()
    monkeypatch.setattr(
        saved_searches, "get_email_sender", lambda _settings=None: sender
    )
    monkeypatch.setattr(
        saved_searches,
        "get_settings",
        lambda: settings,
    )

    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-email-gate-{uuid.uuid4().hex[:8]}@example.com")
    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, owner.email)
    created = client.post(
        "/api/v1/me/saved-searches",
        json={"name": "Email alerts", "url": "/cars?q=audi", "filters": {"q": "audi"}},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "email-gate-create"},
    )
    assert created.status_code == 200, created.text
    saved = created.json()["saved_search"]
    path = f"/api/v1/me/saved-searches/{saved['id']}"
    subscribe = {
        "notifications_enabled": True,
        "notification_channel": "email",
        "notification_frequency": "daily",
        "expected_revision": 1,
    }

    unconfigured = client.patch(path, json=subscribe, headers={"X-CSRF-Token": csrf})
    assert unconfigured.status_code == 422
    assert unconfigured.json()["code"] == "email_delivery_unconfigured"

    sender.is_configured = True
    settings.public_app_url = ""
    missing_public_url = client.patch(path, json=subscribe, headers={"X-CSRF-Token": csrf})
    assert missing_public_url.status_code == 422
    assert missing_public_url.json()["code"] == "email_delivery_unconfigured"
    settings.public_app_url = "https://cars.example.test"
    unverified = client.patch(path, json=subscribe, headers={"X-CSRF-Token": csrf})
    assert unverified.status_code == 422
    assert unverified.json()["code"] == "email_unverified"

    with factory() as db:
        db.add(
            VerifiedEmailContact(
                user_id=owner.id,
                email=owner.email,
                verified_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    subscribed = client.patch(path, json=subscribe, headers={"X-CSRF-Token": csrf})
    assert subscribed.status_code == 200, subscribed.text
    saved = subscribed.json()["saved_search"]

    paused = client.post(
        f"{path}/pause",
        json={"expected_revision": saved["revision"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert paused.status_code == 200, paused.text
    with factory() as db:
        contact = db.scalar(
            select(VerifiedEmailContact).where(
                VerifiedEmailContact.user_id == owner.id,
                VerifiedEmailContact.email == owner.email,
            )
        )
        db.delete(contact)
        db.commit()
    sender.is_configured = False

    resumed = client.post(
        f"{path}/resume",
        json={"expected_revision": paused.json()["saved_search"]["revision"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resumed.status_code == 422
    assert resumed.json()["code"] == "email_delivery_unconfigured"
    sender.is_configured = True
    unverified_resume = client.post(
        f"{path}/resume",
        json={"expected_revision": paused.json()["saved_search"]["revision"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert unverified_resume.status_code == 422
    assert unverified_resume.json()["code"] == "email_unverified"
    with factory() as db:
        db.add(
            VerifiedEmailContact(
                user_id=owner.id,
                email=owner.email,
                verified_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    resumed_ok = client.post(
        f"{path}/resume",
        json={"expected_revision": paused.json()["saved_search"]["revision"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert resumed_ok.status_code == 200, resumed_ok.text
    assert resumed_ok.json()["saved_search"]["status"] == "active"
    with factory() as db:
        current = db.get(models.SavedSearch, uuid.UUID(saved["id"]))
        assert current.status == "active"
        assert current.notifications_enabled is True
        assert current.subscription_started_at is not None


@pytest.mark.parametrize("action", ["pause", "unsubscribe"])
def test_pausing_or_unsubscribing_cancels_queued_batch_and_delivery_job(
    integration, action
):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-pause-batch-{uuid.uuid4().hex[:8]}@example.com")
    saved_search = models.SavedSearch(
        user_id=owner.id,
        name="BMW daily",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        status="active",
        revision=1,
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="daily",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        outbox = models.NotificationOutbox(
            dedupe_key=f"pause-batch:{uuid.uuid4()}",
            saved_search_id=saved_search.id,
            user_id=owner.id,
            listing_id=None,
            channel="web",
            status="queued",
            payload={"batch": True},
            attempts=0,
            available_at=datetime.now(timezone.utc),
        )
        db.add(outbox)
        db.flush()
        job = models.WorkerJob(
            kind="notification.deliver",
            job_key=f"notification.deliver:{outbox.id}",
            payload={"outbox_id": str(outbox.id)},
            status="queued",
            attempts=0,
            max_attempts=5,
        )
        db.add(job)
        db.commit()

    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, owner.email)
    path = f"/api/v1/me/saved-searches/{saved_search.id}"
    if action == "pause":
        response = client.post(
            f"{path}/pause",
            json={"expected_revision": 1},
            headers={"X-CSRF-Token": csrf},
        )
    else:
        response = client.patch(
            path,
            json={
                "notifications_enabled": False,
                "notification_channel": None,
                "expected_revision": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 200, response.text
    with factory() as db:
        current_outbox = db.get(models.NotificationOutbox, outbox.id)
        current_job = db.get(models.WorkerJob, job.id)
        current_search = db.get(models.SavedSearch, saved_search.id)
        assert current_outbox.status == "cancelled"
        assert current_job.status == "failed"
        assert current_job.last_error == "notification_batch_cancelled"
        assert current_search.subscription_started_at is None


@pytest.mark.parametrize(
    "changes",
    [
        {"notification_frequency": "daily"},
        {"url": "/cars?q=audi", "filters": {"q": "audi"}},
    ],
    ids=["frequency-change", "search-change"],
)
@pytest.mark.parametrize("job_status", ["queued", "running"])
def test_changing_legacy_weekly_subscription_cancels_queued_single_listing_delivery(
    integration, changes, job_status
):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"saved-weekly-legacy-{uuid.uuid4().hex[:8]}@example.com")
    saved_search = models.SavedSearch(
        user_id=owner.id,
        name="Legacy BMW weekly",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        status="active",
        revision=1,
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="weekly",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    listing = models.Listing(
        owner_id=owner.id,
        slug=f"legacy-weekly-{uuid.uuid4().hex}",
        status="active",
        revision=1,
        title="BMW 320d",
        make_name_snapshot="BMW",
        model_name_snapshot="3 Series",
        year=2020,
        mileage_km=45_000,
        fuel="diesel",
        transmission="automatic",
        drive="rear",
        condition="used",
        damaged=False,
        parts_only=False,
        price_amount=Decimal("20000"),
        currency="USD",
        description="A published legacy notification test listing",
        contact_phone="",
    )
    with factory() as db:
        db.add(saved_search)
        db.add(listing)
        db.flush()
        outbox = models.NotificationOutbox(
            dedupe_key=f"legacy-weekly:{uuid.uuid4()}",
            saved_search_id=saved_search.id,
            user_id=owner.id,
            listing_id=listing.id,
            channel="web",
            status="queued",
            payload={"title": "Новое объявление", "body": listing.title, "url": "/cars"},
            attempts=0,
            available_at=datetime.now(timezone.utc),
        )
        db.add(outbox)
        db.flush()
        job = models.WorkerJob(
            kind="notification.deliver",
            job_key=f"notification.deliver:{outbox.id}",
            payload={"outbox_id": str(outbox.id)},
            status=job_status,
            locked_by="notification-test-worker" if job_status == "running" else None,
            lease_until=(
                datetime.now(timezone.utc) + timedelta(minutes=3)
                if job_status == "running"
                else None
            ),
            attempts=0,
            max_attempts=5,
        )
        db.add(job)
        db.commit()

    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, owner.email)
    updated = client.patch(
        f"/api/v1/me/saved-searches/{saved_search.id}",
        json={**changes, "expected_revision": 1},
        headers={"X-CSRF-Token": csrf},
    )

    assert updated.status_code == 200, updated.text
    with factory() as db:
        current_outbox = db.get(models.NotificationOutbox, outbox.id)
        current_job = db.get(models.WorkerJob, job.id)
        assert current_outbox.status == "cancelled"
        assert current_outbox.last_error == "notification_preference_changed"
        assert current_job.status == "failed"
        assert current_job.last_error == "notification_preference_changed"
        assert current_job.locked_by is None
        assert current_job.lease_until is None


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
    assert mismatch.json()["code"] == "validation_error"


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
