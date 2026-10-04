import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.main import app
from app.security import hash_password
from app.services import enqueue_saved_search_match
from app.worker import _run_job


PASSWORD = "saved-search-notification-password-123"


def test_saved_search_email_content_uses_same_origin_absolute_link_and_plain_text():
    from app.notification_service import saved_search_email_content

    subject, body = saved_search_email_content(
        {"body": "Audi A4\r\nInjected text", "url": "/cars?q=audi"},
        "https://cars.example.test",
    )

    assert subject == "Новое объявление по сохранённому поиску"
    assert "Audi A4 Injected text" in body
    assert "https://cars.example.test/cars?q=audi" in body


@pytest.mark.parametrize("search_url", ["https://phishing.example/", "//phishing.example/", "cars?q=audi"])
def test_saved_search_email_content_rejects_non_site_links(search_url):
    from app.notification_service import saved_search_email_content

    with pytest.raises(ValueError, match="invalid_notification_url"):
        saved_search_email_content({"body": "Audi A4", "url": search_url}, "https://cars.example.test")


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


def add_listing(factory, owner_id: uuid.UUID, *, title: str = "BMW 320d") -> models.Listing:
    listing = models.Listing(
        owner_id=owner_id,
        slug=f"notification-{uuid.uuid4().hex}",
        status="active",
        revision=2,
        title=title,
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
        description="A published test listing",
        contact_phone="",
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def run_job(factory, job_id: uuid.UUID) -> None:
    with factory() as db:
        job = db.get(models.WorkerJob, job_id)
        job.status = "running"
        job.locked_by = "notification-test-worker"
        job.attempts = 1
        job.lease_until = datetime.now(timezone.utc) + timedelta(minutes=3)
        db.commit()
    _run_job(job_id, "notification-test-worker")


def test_web_saved_search_match_is_delivered_idempotently(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"notification-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"notification-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id)
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="BMW under 25k",
        search_url="/cars?q=bmw&price_max=25000&currency=USD",
        filters={"q": "bmw", "price_max": "25000", "currency": "USD"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="instant",
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        enqueue_saved_search_match(db, listing)
        db.commit()
        db.refresh(saved_search)
        match_job = db.scalar(select(models.WorkerJob).where(models.WorkerJob.kind == "saved-search.match", models.WorkerJob.payload["listing_id"].as_string() == str(listing.id)))
        assert match_job is not None
        match_job_id = match_job.id

    run_job(factory, match_job_id)
    with factory() as db:
        outbox = db.scalar(select(models.NotificationOutbox).where(models.NotificationOutbox.saved_search_id == saved_search.id))
        assert outbox is not None
        assert outbox.channel == "web"
        assert outbox.status == "queued"
        delivery_job = db.scalar(select(models.WorkerJob).where(models.WorkerJob.kind == "notification.deliver", models.WorkerJob.payload["outbox_id"].as_string() == str(outbox.id)))
        assert delivery_job is not None
        delivery_job_id = delivery_job.id

    run_job(factory, delivery_job_id)
    run_job(factory, delivery_job_id)
    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, subscriber.email)
    response = client.get("/api/v1/me/notifications")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["unread_count"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["saved_search_id"] == str(saved_search.id)
    assert payload["items"][0]["listing_id"] == str(listing.id)
    notification_id = payload["items"][0]["id"]
    marked = client.post(
        f"/api/v1/me/notifications/{notification_id}/read",
        headers={"X-CSRF-Token": csrf},
    )
    assert marked.status_code == 200, marked.text
    assert client.get("/api/v1/me/notifications?unread_only=true").json()["items"] == []
    with factory() as db:
        assert db.scalar(select(models.UserNotification.id).where(models.UserNotification.user_id == subscriber.id)) is not None
        assert db.scalar(select(models.NotificationOutbox.status).where(models.NotificationOutbox.saved_search_id == saved_search.id)) == "delivered"


def test_email_saved_search_is_retained_as_unsupported_without_delivery(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"email-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"email-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id, title="Audi A4")
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="Audi alerts",
        search_url="/cars?q=audi",
        filters={"q": "audi"},
        notifications_enabled=True,
        notification_channel="email",
        notification_frequency="instant",
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        enqueue_saved_search_match(db, listing)
        db.commit()
        match_job = db.scalar(select(models.WorkerJob).where(models.WorkerJob.kind == "saved-search.match", models.WorkerJob.payload["listing_id"].as_string() == str(listing.id)))
        assert match_job is not None
        match_job_id = match_job.id
    run_job(factory, match_job_id)
    with factory() as db:
        outbox = db.scalar(select(models.NotificationOutbox).where(models.NotificationOutbox.saved_search_id == saved_search.id))
        assert outbox is not None
        assert outbox.status == "unsupported"
        assert outbox.last_error == "email_provider_unconfigured"
        assert db.scalar(select(models.WorkerJob.id).where(models.WorkerJob.kind == "notification.deliver", models.WorkerJob.payload["outbox_id"].as_string() == str(outbox.id))) is None
        assert db.scalar(select(models.UserNotification.id).where(models.UserNotification.user_id == subscriber.id)) is None


def test_configured_email_saved_search_delivers_only_to_verified_contact(integration, monkeypatch):
    from app.identity_models import VerifiedEmailContact
    import app.worker as worker

    class MemoryEmailSender:
        is_configured = True

        def __init__(self):
            self.sent = []

        def send_email(self, recipient, subject, body, *, idempotency_key):
            self.sent.append((recipient, subject, body, idempotency_key))

    sender = MemoryEmailSender()
    monkeypatch.setattr(worker, "get_email_sender", lambda _settings=None: sender, raising=False)
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(public_app_url="https://cars.example.test"),
    )
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"email-delivery-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"email-delivery-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id, title="Audi A4")
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="Audi alerts",
        search_url="/cars?q=audi",
        filters={"q": "audi"},
        notifications_enabled=True,
        notification_channel="email",
        notification_frequency="instant",
    )
    with factory() as db:
        db.add(VerifiedEmailContact(user_id=subscriber.id, email=subscriber.email, verified_at=datetime.now(timezone.utc)))
        db.add(saved_search)
        db.flush()
        enqueue_saved_search_match(db, listing)
        db.commit()
        match_job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "saved-search.match",
                models.WorkerJob.payload["listing_id"].as_string() == str(listing.id),
            )
        )
        assert match_job is not None
        match_job_id = match_job.id

    run_job(factory, match_job_id)
    with factory() as db:
        outbox = db.scalar(
            select(models.NotificationOutbox).where(
                models.NotificationOutbox.saved_search_id == saved_search.id,
            )
        )
        assert outbox is not None
        assert outbox.status == "queued"
        delivery_job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "notification.deliver",
                models.WorkerJob.payload["outbox_id"].as_string() == str(outbox.id),
            )
        )
        assert delivery_job is not None
        delivery_job_id = delivery_job.id

    run_job(factory, delivery_job_id)

    assert len(sender.sent) == 1
    recipient, subject, body, dedupe_key = sender.sent[0]
    assert recipient == subscriber.email
    assert subject == "Новое объявление по сохранённому поиску"
    assert "Audi A4" in body
    assert "https://cars.example.test/cars?q=audi" in body
    with factory() as db:
        outbox = db.scalar(
            select(models.NotificationOutbox).where(
                models.NotificationOutbox.saved_search_id == saved_search.id,
            )
        )
        assert outbox.status == "delivered"
        assert outbox.last_error is None
        assert dedupe_key == outbox.dedupe_key


def test_saved_search_match_is_suppressed_for_non_matching_listing(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"nomatch-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"nomatch-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id, title="Toyota Corolla")
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="Honda only",
        search_url="/cars?q=honda",
        filters={"q": "honda"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="instant",
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        enqueue_saved_search_match(db, listing)
        db.commit()
        match_job = db.scalar(select(models.WorkerJob).where(models.WorkerJob.kind == "saved-search.match", models.WorkerJob.payload["listing_id"].as_string() == str(listing.id)))
        assert match_job is not None
        match_job_id = match_job.id
    run_job(factory, match_job_id)
    with factory() as db:
        assert db.scalar(select(models.NotificationOutbox.id).where(models.NotificationOutbox.saved_search_id == saved_search.id)) is None
