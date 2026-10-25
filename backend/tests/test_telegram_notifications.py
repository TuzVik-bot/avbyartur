import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.security import hash_password
from app.worker import _run_job, _telegram_link_poll

PASSWORD = "telegram-test-password-123"


def login(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


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


def add_listing(
    factory, owner_id: uuid.UUID, *, title: str = "BMW 320d"
) -> models.Listing:
    listing = models.Listing(
        owner_id=owner_id,
        slug=f"telegram-{uuid.uuid4().hex}",
        status="active",
        revision=2,
        title=title,
        year=2020,
        mileage_km=45_000,
        fuel="diesel",
        transmission="automatic",
        condition="used",
        damaged=False,
        parts_only=False,
        price_amount=Decimal(20000),
        currency="BYN",
        description="A published test listing",
        contact_phone="",
    )
    with factory() as db:
        db.add(listing)
        db.flush()
        db.add(
            models.ListingStatusEvent(
                listing_id=listing.id,
                actor_id=owner_id,
                from_status="draft",
                to_status="active",
                revision=listing.revision,
                reason="telegram_test_publication",
                created_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def link_user(factory, user: models.User, chat_id: int = 4242) -> None:
    with factory() as db:
        row = db.get(models.User, user.id)
        row.telegram_chat_id = chat_id
        row.telegram_linked_at = datetime.now(UTC)
        db.commit()


def add_saved_search(
    factory, user_id: uuid.UUID, *, channel: str = "telegram"
) -> models.SavedSearch:
    search = models.SavedSearch(
        user_id=user_id,
        name="BMW alerts",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        status="active",
        revision=1,
        notifications_enabled=True,
        notification_channel=channel,
        notification_frequency="instant",
        subscription_started_at=datetime.now(UTC) - timedelta(days=2),
    )
    with factory() as db:
        db.add(search)
        db.commit()
        db.refresh(search)
        db.expunge(search)
    return search


def enqueue_match_job(factory, listing: models.Listing) -> uuid.UUID:
    with factory() as db:
        db.add(
            models.WorkerJob(
                job_key=f"saved-search.match:{listing.id}:{listing.revision}",
                kind="saved-search.match",
                payload={
                    "listing_id": str(listing.id),
                    "listing_revision": listing.revision,
                },
                status="queued",
                max_attempts=3,
            )
        )
        db.commit()
        job = db.scalar(
            select(models.WorkerJob)
            .where(models.WorkerJob.kind == "saved-search.match")
            .order_by(models.WorkerJob.created_at.desc(), models.WorkerJob.id.desc())
            .limit(1)
        )
        job.status = "running"
        job.locked_by = "telegram-test-worker"
        job.attempts = 1
        job.lease_until = datetime.now(UTC) + timedelta(minutes=3)
        db.commit()
        return job.id


def test_telegram_account_endpoints_without_configured_bot(integration):
    client: TestClient = integration["client"]
    factory = integration["SessionLocal"]
    user = add_user(factory, f"telegram-owner-{uuid.uuid4().hex[:8]}@example.com")
    csrf = login(client, user.email)

    denied = client.post(
        "/api/v1/me/telegram/link-start", headers={"X-CSRF-Token": csrf}
    )
    assert denied.status_code == 503, denied.text
    assert denied.json()["code"] == "telegram_provider_unconfigured"

    status = client.get("/api/v1/me/telegram")
    assert status.status_code == 200, status.text
    assert status.json() == {
        "linked": False,
        "linked_at": None,
        "bot_username": "",
        "channel_available": False,
    }


def test_telegram_link_start_and_unlink(integration, monkeypatch):
    client: TestClient = integration["client"]
    factory = integration["SessionLocal"]
    user = add_user(factory, f"telegram-user-{uuid.uuid4().hex[:8]}@example.com")
    csrf = login(client, user.email)

    monkeypatch.setattr(
        "app.api.account.get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token=SimpleNamespace(get_secret_value=lambda: "test-token"),
            telegram_bot_username="avtorinok_bot",
        ),
        raising=False,
    )

    started = client.post(
        "/api/v1/me/telegram/link-start", headers={"X-CSRF-Token": csrf}
    )
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["bot_username"] == "avtorinok_bot"
    assert 20 <= len(body["code"]) <= 64

    with factory() as db:
        stored = db.get(models.User, user.id)
        assert stored.telegram_link_code == body["code"]

    unlinked = client.post("/api/v1/me/telegram/unlink", headers={"X-CSRF-Token": csrf})
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["linked"] is False
    with factory() as db:
        stored = db.get(models.User, user.id)
        assert stored.telegram_link_code is None


def test_telegram_saved_search_requires_linked_chat(integration, monkeypatch):
    client: TestClient = integration["client"]
    factory = integration["SessionLocal"]
    user = add_user(factory, f"telegram-sub-{uuid.uuid4().hex[:8]}@example.com")
    csrf = login(client, user.email)
    search = add_saved_search(factory, user.id)

    monkeypatch.setattr(
        "app.api.saved_searches.get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token=SimpleNamespace(get_secret_value=lambda: "test-token"),
            saved_search_mutations_per_hour=60,
        ),
        raising=False,
    )

    response = client.patch(
        f"/api/v1/me/saved-searches/{search.id}",
        json={
            "notifications_enabled": True,
            "notification_channel": "telegram",
            "expected_revision": search.revision,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "telegram_not_linked"

    link_user(factory, user)
    linked = client.patch(
        f"/api/v1/me/saved-searches/{search.id}",
        json={
            "notifications_enabled": True,
            "notification_channel": "telegram",
            "expected_revision": search.revision,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["saved_search"]["notification_channel"] == "telegram"


def test_telegram_outbox_delivery_sends_message_and_materialises_inbox(
    integration, monkeypatch
):
    from app import worker

    factory = integration["SessionLocal"]
    owner = add_user(
        factory, f"telegram-listing-owner-{uuid.uuid4().hex[:8]}@example.com"
    )
    subscriber = add_user(
        factory, f"telegram-subscriber-{uuid.uuid4().hex[:8]}@example.com"
    )
    link_user(factory, subscriber)
    add_listing(factory, owner.id)
    search = add_saved_search(factory, subscriber.id)

    sent: list[tuple[int, str]] = []

    def fake_send(*, api_url, token, chat_id, text, timeout):
        sent.append((chat_id, text))

    monkeypatch.setattr(worker, "send_telegram_message", fake_send)
    monkeypatch.setattr(
        worker,
        "get_email_sender",
        lambda _settings=None: SimpleNamespace(is_configured=False),
        raising=False,
    )
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token=SimpleNamespace(get_secret_value=lambda: "test-token"),
            telegram_api_url="https://api.telegram.org",
            telegram_timeout_seconds=5,
            public_app_url="https://cars.example.test",
        ),
    )

    listing = add_listing(factory, owner.id, title="BMW 320d touring")
    job_id = enqueue_match_job(factory, listing)
    _run_job(job_id, "telegram-test-worker")

    with factory() as db:
        deliver = db.scalar(
            select(models.WorkerJob)
            .where(models.WorkerJob.kind == "notification.deliver")
            .order_by(models.WorkerJob.created_at.desc(), models.WorkerJob.id.desc())
            .limit(1)
        )
        assert deliver is not None
        deliver.status = "running"
        deliver.locked_by = "telegram-test-worker"
        deliver.attempts = 1
        deliver.lease_until = datetime.now(UTC) + timedelta(minutes=3)
        db.commit()
        deliver_id = deliver.id
    _run_job(deliver_id, "telegram-test-worker")

    with factory() as db:
        outbox = db.scalar(
            select(models.NotificationOutbox).where(
                models.NotificationOutbox.saved_search_id == search.id
            )
        )
        assert outbox is not None, "outbox row must exist"
        assert outbox.channel == "telegram"
        assert outbox.status == "delivered", outbox.last_error
        notification = db.scalar(
            select(models.UserNotification).where(
                models.UserNotification.outbox_id == outbox.id
            )
        )
        assert notification is not None

    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == 4242
    assert "BMW 320d touring" in text
    assert "https://cars.example.test/cars" in text


def test_telegram_outbox_without_provider_is_unsupported(integration, monkeypatch):
    from app import worker

    factory = integration["SessionLocal"]
    owner = add_user(factory, f"telegram-owner2-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"telegram-sub2-{uuid.uuid4().hex[:8]}@example.com")
    link_user(factory, subscriber)
    listing = add_listing(factory, owner.id)
    add_saved_search(factory, subscriber.id)

    monkeypatch.setattr(
        worker,
        "get_email_sender",
        lambda _settings=None: SimpleNamespace(is_configured=False),
        raising=False,
    )
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(public_app_url="https://cars.example.test"),
    )

    job_id = enqueue_match_job(factory, listing)
    _run_job(job_id, "telegram-test-worker")

    with factory() as db:
        outbox = db.scalar(
            select(models.NotificationOutbox).where(
                models.NotificationOutbox.channel == "telegram"
            )
        )
        assert outbox is not None
        assert outbox.status == "unsupported"
        assert outbox.last_error == "telegram_provider_unconfigured"


def test_telegram_link_poll_links_chat_for_start_code(integration, monkeypatch):
    from app import worker

    factory = integration["SessionLocal"]
    user = add_user(factory, f"telegram-poll-{uuid.uuid4().hex[:8]}@example.com")
    with factory() as db:
        row = db.get(models.User, user.id)
        code = "poll-code-" + uuid.uuid4().hex
        row.telegram_link_code = code
        db.commit()

    updates = [
        {
            "update_id": 7,
            "message": {"text": f"/start {code}", "chat": {"id": 9991}},
        }
    ]

    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token=SimpleNamespace(get_secret_value=lambda: "test-token"),
            telegram_api_url="https://api.telegram.org",
            telegram_timeout_seconds=5,
            telegram_poll_interval_seconds=0,
        ),
    )
    monkeypatch.setattr(
        worker,
        "fetch_telegram_updates",
        lambda **kwargs: updates if kwargs.get("poll_seconds") == 0 else [],
    )
    monkeypatch.setattr(worker, "_telegram_last_poll", -10_000.0)
    monkeypatch.setattr(worker, "send_telegram_message", lambda **kwargs: None)

    _telegram_link_poll()

    with factory() as db:
        row = db.get(models.User, user.id)
        assert row.telegram_chat_id == 9991
        assert row.telegram_link_code is None
        assert row.telegram_linked_at is not None
