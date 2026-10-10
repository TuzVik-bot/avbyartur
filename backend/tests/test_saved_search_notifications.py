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


def test_saved_search_digest_email_contains_bounded_listing_links_and_total():
    from app.notification_service import saved_search_digest_email_content

    subject, body = saved_search_digest_email_content(
        {
            "search_url": "/cars?q=audi",
            "listings": [
                {"id": "1", "title": "Audi A4", "url": "/cars/audi-a4"},
                {"id": "2", "title": "Audi Q5", "url": "/cars/audi-q5"},
            ],
        },
        "https://cars.example.test",
        27,
    )

    assert subject == "Новое объявление по сохранённому поиску"
    assert "Найдено объявлений: 27" in body
    assert "https://cars.example.test/cars/audi-a4" in body
    assert "https://cars.example.test/cars/audi-q5" in body
    assert "Ещё объявлений: 25" in body
    assert "https://cars.example.test/cars?q=audi" in body


def test_saved_search_digest_email_rejects_external_listing_links():
    from app.notification_service import saved_search_digest_email_content

    with pytest.raises(ValueError, match="invalid_notification_url"):
        saved_search_digest_email_content(
            {
                "search_url": "/cars",
                "listings": [{"id": "1", "title": "Audi", "url": "//phishing.example"}],
            },
            "https://cars.example.test",
            1,
        )


@pytest.mark.parametrize(
    "search_url",
    ["//phishing.example/cars", "https://phishing.example/cars", "/cars#fragment", "/account"],
)
def test_saved_search_digest_email_rejects_invalid_search_links(search_url):
    from app.notification_service import saved_search_digest_email_content

    with pytest.raises(ValueError, match="invalid_notification_url"):
        saved_search_digest_email_content(
            {
                "search_url": search_url,
                "listings": [{"id": "1", "title": "Audi", "url": "/cars/audi"}],
            },
            "https://cars.example.test",
            1,
        )


def test_saved_search_filters_ignore_pagination_for_legacy_urls():
    from types import SimpleNamespace

    from app.notification_service import saved_search_filters

    assert saved_search_filters(SimpleNamespace(search_url="/cars?q=audi&page=3&page_size=50")) == {"q": "audi"}


def test_saved_search_filters_preserve_non_car_category_and_details():
    from app.notification_service import saved_search_filters

    saved_search = SimpleNamespace(
        search_url="/wheels?category_code=wheels&details=%7B%22diameter_in%22%3A17%7D"
    )

    assert saved_search_filters(saved_search) == {
        "category_code": "wheels",
        "details": {"diameter_in": 17},
    }


def test_category_digest_email_uses_category_search_url():
    from app.notification_service import saved_search_digest_email_content

    subject, body = saved_search_digest_email_content(
        {
            "search_url": "/tires?category_code=tires&season=winter",
            "listings": [{"id": str(uuid.uuid4()), "title": "Winter tires", "url": "/tires/winter-set/id-1"}],
        },
        "https://cars.example.test",
        1,
    )

    assert subject == "Новое объявление по сохранённому поиску"
    assert "https://cars.example.test/tires?category_code=tires&season=winter" in body


def test_daily_delivery_uses_0900_minsk_and_category_listing_url():
    from app.worker import _listing_url, _next_notification_at

    instant = datetime(2026, 10, 10, 5, 30, tzinfo=timezone.utc)
    before_nine = datetime(2026, 10, 10, 5, 59, tzinfo=timezone.utc)
    at_nine = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)

    assert _next_notification_at(instant, "instant") == instant
    assert _next_notification_at(before_nine, "daily") == datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
    assert _next_notification_at(at_nine, "daily") == datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)
    assert _next_notification_at(instant, "weekly").weekday() == 0
    assert _next_notification_at(instant, "weekly").hour == 0
    assert _listing_url(SimpleNamespace(category_code="trucks", slug="volvo-fh", id="listing-1")) == "/trucks/volvo-fh/listing-1"


def test_saved_search_delivery_snapshot_ignores_name_only_revision_change():
    from app.worker import _saved_search_delivery_snapshot

    shared = {
        "id": uuid.uuid4(),
        "status": "active",
        "notifications_enabled": True,
        "notification_channel": "email",
        "notification_frequency": "instant",
        "search_url": "/cars?q=audi",
        "subscription_started_at": datetime(2026, 10, 8, tzinfo=timezone.utc),
    }
    before = SimpleNamespace(revision=1, name="Audi alerts", **shared)
    after = SimpleNamespace(revision=2, name="My Audi alerts", **shared)

    assert _saved_search_delivery_snapshot(before, {"q": "audi"}) == (
        _saved_search_delivery_snapshot(after, {"q": "audi"})
    )


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


def add_listing(
    factory,
    owner_id: uuid.UUID,
    *,
    title: str = "BMW 320d",
    published_at: datetime | None = None,
) -> models.Listing:
    published_at = published_at or datetime.now(timezone.utc) - timedelta(days=1)
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
        db.flush()
        db.add(models.ListingStatusEvent(
            listing_id=listing.id,
            actor_id=owner_id,
            from_status="draft",
            to_status="active",
            revision=listing.revision,
            reason="notification_test_publication",
            created_at=published_at,
        ))
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
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="instant",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
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
    assert payload["items"][0]["total_count"] == 1
    assert payload["items"][0]["listings"] == [{
        "id": str(listing.id),
        "title": listing.title,
        "url": f"/cars/{listing.slug}/{listing.slug}/{listing.id}",
    }]
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


def test_daily_saved_search_matches_dedupe_into_one_delivered_digest(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"daily-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"daily-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    listings = [
        add_listing(factory, owner.id, title="BMW 320d"),
        add_listing(factory, owner.id, title="BMW X5"),
    ]
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="BMW digest",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="daily",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        match_job_ids = []
        for listing in listings:
            enqueue_saved_search_match(db, listing)
            job = db.scalar(
                select(models.WorkerJob).where(
                    models.WorkerJob.kind == "saved-search.match",
                    models.WorkerJob.payload["listing_id"].as_string() == str(listing.id),
                )
            )
            assert job is not None
            match_job_ids.append(job.id)
        db.commit()

    for job_id in match_job_ids:
        run_job(factory, job_id)

    with factory() as db:
        batches = db.scalars(
            select(models.SavedSearchNotificationBatch).where(
                models.SavedSearchNotificationBatch.saved_search_id == saved_search.id,
            )
        ).all()
        assert len(batches) == 1
        outbox = db.get(models.NotificationOutbox, batches[0].outbox_id)
        assert outbox is not None
        assert outbox.listing_id is None
        assert outbox.payload["notification_frequency"] == "daily"
        assert outbox.payload["filters"] == {"q": "bmw"}
        assert outbox.payload["search_url"] == saved_search.search_url
        assert outbox.payload["total_count"] == 2
        assert {item["id"] for item in outbox.payload["listings"]} == {str(item.id) for item in listings}
        assert db.scalar(
            select(models.SavedSearchNotificationMatch.id).where(
                models.SavedSearchNotificationMatch.saved_search_id == saved_search.id,
                models.SavedSearchNotificationMatch.listing_id == listings[0].id,
            )
        ) is not None
        delivery_job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "notification.deliver",
                models.WorkerJob.payload["outbox_id"].as_string() == str(outbox.id),
            )
        )
        assert delivery_job is not None
        delivery_job_id = delivery_job.id

    run_job(factory, delivery_job_id)
    run_job(factory, delivery_job_id)
    with factory() as db:
        inbox = db.scalars(select(models.UserNotification).where(models.UserNotification.user_id == subscriber.id)).all()
        assert len(inbox) == 1
        assert inbox[0].listing_id is None
        assert inbox[0].total_count == 2
        assert {item["id"] for item in inbox[0].listings} == {str(item.id) for item in listings}
        assert inbox[0].url == saved_search.search_url
        assert db.scalar(select(models.NotificationOutbox.status).where(models.NotificationOutbox.saved_search_id == saved_search.id)) == "delivered"


def test_daily_email_saved_search_sends_one_digest_with_both_publications(
    integration, monkeypatch
):
    from app.identity_models import VerifiedEmailContact
    import app.worker as worker

    class MemoryEmailSender:
        is_configured = True

        def __init__(self):
            self.sent = []

        def send_email(self, recipient, subject, body, *, idempotency_key):
            self.sent.append((recipient, subject, body, idempotency_key))

    sender = MemoryEmailSender()
    monkeypatch.setattr(
        worker, "get_email_sender", lambda _settings=None: sender, raising=False
    )
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(public_app_url="https://cars.example.test"),
    )
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"daily-email-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(
        factory, f"daily-email-subscriber-{uuid.uuid4().hex[:8]}@example.com"
    )
    listings = [
        add_listing(factory, owner.id, title="BMW 320d"),
        add_listing(factory, owner.id, title="BMW X5"),
    ]
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="BMW daily email",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="email",
        notification_frequency="daily",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    with factory() as db:
        db.add(
            VerifiedEmailContact(
                user_id=subscriber.id,
                email=subscriber.email,
                verified_at=datetime.now(timezone.utc),
            )
        )
        db.add(saved_search)
        db.flush()
        match_job_ids = []
        for listing in listings:
            enqueue_saved_search_match(db, listing)
            job = db.scalar(
                select(models.WorkerJob).where(
                    models.WorkerJob.kind == "saved-search.match",
                    models.WorkerJob.payload["listing_id"].as_string() == str(listing.id),
                )
            )
            assert job is not None
            match_job_ids.append(job.id)
        db.commit()

    for job_id in match_job_ids:
        run_job(factory, job_id)

    with factory() as db:
        batches = db.scalars(
            select(models.SavedSearchNotificationBatch).where(
                models.SavedSearchNotificationBatch.saved_search_id == saved_search.id,
            )
        ).all()
        assert len(batches) == 1
        outbox = db.get(models.NotificationOutbox, batches[0].outbox_id)
        assert outbox is not None
        assert outbox.payload["total_count"] == 2
        assert {item["id"] for item in outbox.payload["listings"]} == {
            str(listing.id) for listing in listings
        }
        outbox_id = outbox.id
        delivery_job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "notification.deliver",
                models.WorkerJob.payload["outbox_id"].as_string() == str(outbox_id),
            )
        )
        assert delivery_job is not None
        delivery_job_id = delivery_job.id

    run_job(factory, delivery_job_id)
    run_job(factory, delivery_job_id)

    assert len(sender.sent) == 1
    recipient, subject, body, dedupe_key = sender.sent[0]
    assert recipient == subscriber.email
    assert subject == "Новое объявление по сохранённому поиску"
    assert "Найдено объявлений: 2" in body
    for listing in listings:
        listing_url = f"https://cars.example.test/cars/{listing.slug}/{listing.slug}/{listing.id}"
        assert listing.title in body
        assert listing_url in body
    with factory() as db:
        outbox = db.get(models.NotificationOutbox, outbox_id)
        assert outbox.status == "delivered"
        assert outbox.last_error is None
        assert dedupe_key == outbox.dedupe_key


def test_saved_search_does_not_notify_for_publication_before_subscription(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"pre-subscription-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(
        factory, f"pre-subscription-subscriber-{uuid.uuid4().hex[:8]}@example.com"
    )
    published_at = datetime.now(timezone.utc) - timedelta(days=3)
    listing = add_listing(
        factory, owner.id, title="BMW 320d", published_at=published_at
    )
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="BMW after signup",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="instant",
        subscription_started_at=published_at + timedelta(days=1),
    )
    with factory() as db:
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
        assert db.scalar(
            select(models.NotificationOutbox.id).where(
                models.NotificationOutbox.saved_search_id == saved_search.id,
            )
        ) is None
        assert db.scalar(
            select(models.SavedSearchNotificationMatch.id).where(
                models.SavedSearchNotificationMatch.saved_search_id == saved_search.id,
                models.SavedSearchNotificationMatch.listing_id == listing.id,
            )
        ) is None
        assert db.scalar(
            select(models.UserNotification.id).where(
                models.UserNotification.user_id == subscriber.id,
            )
        ) is None


def test_saved_search_uses_original_publication_after_reapproval(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"reapproval-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(
        factory, f"reapproval-subscriber-{uuid.uuid4().hex[:8]}@example.com"
    )
    first_publication = datetime.now(timezone.utc) - timedelta(days=3)
    listing = add_listing(
        factory, owner.id, title="BMW 320d", published_at=first_publication
    )
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="BMW after signup",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="instant",
        subscription_started_at=first_publication + timedelta(days=1),
    )
    with factory() as db:
        current_listing = db.get(models.Listing, listing.id)
        db.add(saved_search)
        db.add(
            models.ListingStatusEvent(
                listing_id=listing.id,
                actor_id=owner.id,
                from_status="draft",
                to_status="active",
                revision=current_listing.revision,
                reason="notification_test_reapproval",
                created_at=first_publication + timedelta(days=2),
            )
        )
        db.flush()
        enqueue_saved_search_match(db, current_listing)
        job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "saved-search.match",
                models.WorkerJob.payload["listing_id"].as_string() == str(listing.id),
            )
        )
        assert job is not None
        job_id = job.id
        db.commit()

    run_job(factory, job_id)

    with factory() as db:
        assert db.scalar(
            select(models.NotificationOutbox.id).where(
                models.NotificationOutbox.saved_search_id == saved_search.id,
            )
        ) is None
        assert db.scalar(
            select(models.SavedSearchNotificationMatch.id).where(
                models.SavedSearchNotificationMatch.saved_search_id == saved_search.id,
                models.SavedSearchNotificationMatch.listing_id == listing.id,
            )
        ) is None


def test_daily_batch_slot_can_be_reused_after_search_change(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"batch-update-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"batch-update-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    first_listing = add_listing(factory, owner.id, title="BMW 320d")
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="BMW digest",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="daily",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        enqueue_saved_search_match(db, first_listing)
        first_job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "saved-search.match",
                models.WorkerJob.payload["listing_id"].as_string() == str(first_listing.id),
            )
        )
        assert first_job is not None
        first_job_id = first_job.id
        db.commit()
    run_job(factory, first_job_id)

    client = TestClient(app, base_url="http://testserver")
    csrf = login(client, subscriber.email)
    updated = client.patch(
        f"/api/v1/me/saved-searches/{saved_search.id}",
        json={"url": "/cars?q=audi", "filters": {"q": "audi"}, "expected_revision": 1},
        headers={"X-CSRF-Token": csrf},
    )
    assert updated.status_code == 200, updated.text
    second_listing = add_listing(
        factory,
        owner.id,
        title="Audi A4",
        published_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    with factory() as db:
        enqueue_saved_search_match(db, second_listing)
        second_job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "saved-search.match",
                models.WorkerJob.payload["listing_id"].as_string() == str(second_listing.id),
            )
        )
        assert second_job is not None
        second_job_id = second_job.id
        db.commit()
    run_job(factory, second_job_id)

    with factory() as db:
        batches = db.scalars(
            select(models.SavedSearchNotificationBatch).where(
                models.SavedSearchNotificationBatch.saved_search_id == saved_search.id,
                models.SavedSearchNotificationBatch.channel == "web",
            )
        ).all()
        assert len(batches) == 1
        replacement = db.get(models.NotificationOutbox, batches[0].outbox_id)
        assert replacement is not None
        assert replacement.listing_id is None
        assert replacement.status == "queued"
        assert replacement.payload["search_url"] == "/cars?q=audi"
        assert replacement.payload["total_count"] == 1
        assert replacement.payload["listings"][0]["id"] == str(second_listing.id)
        outboxes = db.scalars(
            select(models.NotificationOutbox).where(
                models.NotificationOutbox.saved_search_id == saved_search.id,
            )
        ).all()
        old = next(row for row in outboxes if row.id != replacement.id)
        assert old.status == "cancelled"


def test_legacy_weekly_subscription_processes_a_queued_match_job(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"weekly-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"weekly-subscriber-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, owner.id, title="BMW 320d")
    saved_search = models.SavedSearch(
        user_id=subscriber.id,
        name="Legacy weekly BMW",
        search_url="/cars?q=bmw",
        filters={"q": "bmw"},
        notifications_enabled=True,
        notification_channel="web",
        notification_frequency="weekly",
        subscription_started_at=None,
    )
    with factory() as db:
        db.add(saved_search)
        db.flush()
        enqueue_saved_search_match(db, listing)
        job = db.scalar(
            select(models.WorkerJob).where(
                models.WorkerJob.kind == "saved-search.match",
                models.WorkerJob.payload["listing_id"].as_string() == str(listing.id),
            )
        )
        assert job is not None
        match_job_id = job.id
        db.commit()

    run_job(factory, match_job_id)

    with factory() as db:
        outbox = db.scalar(
            select(models.NotificationOutbox).where(
                models.NotificationOutbox.saved_search_id == saved_search.id,
            )
        )
        assert outbox is not None
        assert outbox.status == "queued"
        assert outbox.available_at.weekday() == 0
        assert outbox.available_at.hour == 0


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
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
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
    monkeypatch.setattr(
        worker, "get_email_sender", lambda _settings=None: sender, raising=False
    )
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
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
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


@pytest.mark.parametrize(
    ("search_change", "should_send"),
    [
        pytest.param("name", True, id="name-only-update-does-not-cancel"),
        pytest.param("filter", False, id="filter-change-cancels"),
        pytest.param("channel", False, id="channel-change-cancels"),
        pytest.param("subscription", False, id="subscription-change-cancels"),
        pytest.param("combined", False, id="existing-combined-race-still-cancels"),
    ],
)
def test_email_saved_search_rechecks_search_before_provider_send(
    integration, monkeypatch, search_change, should_send
):
    from app.identity_models import VerifiedEmailContact
    import app.worker as worker

    class MemoryEmailSender:
        is_configured = True

        def __init__(self):
            self.sent = []

        def send_email(self, recipient, subject, body, *, idempotency_key):
            self.sent.append((recipient, subject, body, idempotency_key))

    sender = MemoryEmailSender()
    monkeypatch.setattr(
        worker, "get_email_sender", lambda _settings=None: sender, raising=False
    )
    monkeypatch.setattr(
        worker,
        "get_settings",
        lambda: SimpleNamespace(public_app_url="https://cars.example.test"),
    )
    factory = integration["SessionLocal"]
    owner = add_user(factory, f"email-race-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(
        factory, f"email-race-subscriber-{uuid.uuid4().hex[:8]}@example.com"
    )
    listing = add_listing(factory, owner.id, title="Audi A4")
    saved_search_id = uuid.uuid4()
    saved_search = models.SavedSearch(
        id=saved_search_id,
        user_id=subscriber.id,
        name="Audi alerts",
        search_url="/cars?q=audi",
        filters={"q": "audi"},
        status="active",
        revision=1,
        notifications_enabled=True,
        notification_channel="email",
        notification_frequency="instant",
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    outbox = models.NotificationOutbox(
        dedupe_key=f"email-race:{uuid.uuid4()}",
        saved_search_id=saved_search_id,
        user_id=subscriber.id,
        listing_id=listing.id,
        channel="email",
        status="queued",
        payload={
            "title": "Audi alert",
            "body": listing.title,
            "url": "/cars?q=audi",
            "listing_revision": listing.revision,
            "notification_frequency": "instant",
            "search_url": "/cars?q=audi",
            "filters": {"q": "audi"},
        },
        attempts=0,
        available_at=datetime.now(timezone.utc),
    )
    with factory() as db:
        db.add(
            VerifiedEmailContact(
                user_id=subscriber.id,
                email=subscriber.email,
                verified_at=datetime.now(timezone.utc),
            )
        )
        db.add(saved_search)
        db.flush()
        db.add(outbox)
        db.commit()

    real_session_local = worker.SessionLocal
    session_calls = 0

    def change_search_before_final_guard():
        nonlocal session_calls
        session_calls += 1
        if session_calls == 2:
            with real_session_local() as db:
                current_outbox = db.get(models.NotificationOutbox, outbox.id)
                current_search = db.get(models.SavedSearch, saved_search_id)
                assert current_outbox.status == "running"
                if search_change == "name":
                    current_search.name = "Renamed Audi alerts"
                elif search_change == "filter":
                    current_search.search_url = "/cars?q=toyota"
                    current_search.filters = {"q": "toyota"}
                elif search_change == "channel":
                    current_search.notification_channel = "web"
                elif search_change == "subscription":
                    current_search.subscription_started_at = datetime.now(timezone.utc)
                else:
                    current_search.search_url = "/cars?q=toyota"
                    current_search.filters = {"q": "toyota"}
                    current_search.subscription_started_at = datetime.now(timezone.utc)
                current_search.revision += 1
                db.commit()
        return real_session_local()

    monkeypatch.setattr(worker, "SessionLocal", change_search_before_final_guard)
    worker._deliver_notification(outbox.id)

    assert session_calls == 2
    with factory() as db:
        current_outbox = db.get(models.NotificationOutbox, outbox.id)
        if should_send:
            assert len(sender.sent) == 1
            assert current_outbox.status == "delivered"
            assert current_outbox.last_error is None
            assert db.get(models.SavedSearch, saved_search_id).name == "Renamed Audi alerts"
        else:
            assert sender.sent == []
            assert current_outbox.status == "cancelled"
            assert current_outbox.last_error == "notification_preference_changed"


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
        subscription_started_at=datetime.now(timezone.utc) - timedelta(days=2),
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
