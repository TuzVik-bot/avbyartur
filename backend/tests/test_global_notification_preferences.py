"""Global opt-out must suppress worker delivery after jobs were enqueued."""

from sqlalchemy import select

from app import models
from app.profile_identity_models import UserNotificationPreferences
from app.services import enqueue_saved_search_match
from test_saved_search_notifications import add_user, add_listing, run_job


def test_global_web_optout_suppresses_materialized_notification(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, "global-owner@example.com")
    subscriber = add_user(factory, "global-subscriber@example.com")
    listing = add_listing(factory, owner.id, title="Audi A4")
    with factory() as db:
        db.add(models.SavedSearch(user_id=subscriber.id, name="Автомобили", search_url="/cars", filters={},
                                  notifications_enabled=True, notification_channel="web", notification_frequency="instant"))
        db.flush(); enqueue_saved_search_match(db, listing); db.commit()
        match_id = db.scalar(select(models.WorkerJob.id).where(models.WorkerJob.kind == "saved-search.match"))
    run_job(factory, match_id)
    with factory() as db:
        delivery_id = db.scalar(select(models.WorkerJob.id).where(models.WorkerJob.kind == "notification.deliver"))
        db.add(UserNotificationPreferences(user_id=subscriber.id, web_enabled=False, email_enabled=True, revision=1))
        db.commit()
    assert delivery_id is not None
    run_job(factory, delivery_id)
    with factory() as db:
        assert db.scalar(select(models.UserNotification).where(models.UserNotification.user_id == subscriber.id)) is None
        outbox = db.scalar(select(models.NotificationOutbox).where(models.NotificationOutbox.user_id == subscriber.id))
        assert outbox.status == "unsupported" and outbox.last_error == "web_preference_disabled"
