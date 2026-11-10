import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app import models
from app.identity_models import VerifiedEmailContact
from tests.test_saved_search_notifications import add_listing, add_user


def test_saved_search_email_is_sent_without_holding_row_locks(integration, monkeypatch):
    from app import worker

    factory = integration["SessionLocal"]
    owner = add_user(factory, f"lock-owner-{uuid.uuid4().hex[:8]}@example.com")
    subscriber = add_user(factory, f"lock-subscriber-{uuid.uuid4().hex[:8]}@example.com")
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
        db.add(VerifiedEmailContact(
            user_id=subscriber.id, email=subscriber.email, verified_at=datetime.now(timezone.utc),
        ))
        db.add(saved_search)
        db.flush()
        outbox = models.NotificationOutbox(
            dedupe_key=f"lock-test:{uuid.uuid4()}",
            saved_search_id=saved_search.id,
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
        db.add(outbox)
        db.commit()
        outbox_id, saved_search_id = outbox.id, saved_search.id

    locked_during_send: list[str] = []

    class LockProbingSender:
        is_configured = True

        def send_email(self, recipient, subject, body, *, idempotency_key):
            with factory() as probe:
                for model, row_id in (
                    (models.SavedSearch, saved_search_id),
                    (models.User, subscriber.id),
                    (models.Listing, listing.id),
                    (models.NotificationOutbox, outbox_id),
                ):
                    row = probe.scalar(
                        select(model.id).where(model.id == row_id).with_for_update(skip_locked=True)
                    )
                    if row is None:
                        locked_during_send.append(model.__tablename__)
                probe.rollback()

    monkeypatch.setattr(worker, "get_email_sender", lambda _settings=None: LockProbingSender())
    monkeypatch.setattr(
        worker, "get_settings", lambda: SimpleNamespace(public_app_url="https://cars.example.test")
    )

    worker._deliver_notification(outbox_id)

    assert locked_during_send == []
    with factory() as db:
        delivered = db.get(models.NotificationOutbox, outbox_id)
        assert delivered.status == "delivered"
        assert delivered.locked_by is None
