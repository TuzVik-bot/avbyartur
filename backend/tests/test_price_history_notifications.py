import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import (
    Company,
    Favorite,
    Listing,
    ListingPriceEvent,
    NotificationOutbox,
    User,
    UserNotification,
)
from app.profile_identity_models import UserNotificationPreferences
from app.security import hash_password


PASSWORD = "price-history-test-password-123"


def _add_user(factory, label: str, *, role: str = "user") -> tuple[User, str]:
    email = f"{label}-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name=label,
            password_hash=hash_password(PASSWORD),
            role=role,
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user, email


def _add_listing(factory, owner_id, *, status: str = "active", amount="15000.00", currency="USD") -> Listing:
    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            slug=f"price-history-{uuid.uuid4().hex}",
            status=status,
            revision=1,
            submitted_revision=1 if status == "pending_review" else None,
            title="Mazda 3, 2018",
            description="A listing used for price history integration coverage.",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
            make_name_snapshot="Mazda",
            model_name_snapshot="3",
            year=2018,
            price_amount=amount,
            currency=currency,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _client(integration) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver")


def _login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def _set_submitted_revision(factory, listing_id, revision: int) -> None:
    with factory() as db:
        listing = db.get(Listing, listing_id)
        listing.status = "pending_review"
        listing.submitted_revision = revision
        db.commit()


def _approve(client: TestClient, csrf: str, listing_id, revision: int):
    response = client.post(
        f"/api/v1/moderation/listings/{listing_id}/approve",
        json={"expected_revision": revision},
        headers=_csrf(csrf),
    )
    assert response.status_code == 200, response.text
    return response.json()["listing"]


def _queue_price_drop(integration, label: str, *, with_company: bool = False):
    factory = integration["SessionLocal"]
    owner, owner_email = _add_user(factory, f"{label}-owner")
    moderator, moderator_email = _add_user(factory, f"{label}-moderator", role="moderator")
    buyer, buyer_email = _add_user(factory, f"{label}-buyer")
    listing = _add_listing(factory, owner.id, status="pending_review", amount="12000.00", currency="BYN")
    company_id = None
    if with_company:
        with factory() as db:
            company = Company(
                owner_id=owner.id,
                name=f"{label} company",
                slug=f"{label}-{uuid.uuid4().hex}",
                unp=f"{uuid.uuid4().int % 1_000_000_000:09d}",
                address="Минск",
                phone="+375291234567",
                status="approved",
            )
            db.add(company)
            db.flush()
            listing_row = db.get(Listing, listing.id)
            listing_row.company_id = company.id
            company_id = company.id
            db.commit()

    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner_email)
    moderator_client = _client(integration)
    moderator_csrf = _login(moderator_client, moderator_email)
    buyer_client = _client(integration)
    buyer_csrf = _login(buyer_client, buyer_email)
    published = _approve(moderator_client, moderator_csrf, listing.id, 1)
    assert buyer_client.put(f"/api/v1/me/favorites/{listing.id}", headers=_csrf(buyer_csrf)).status_code == 200
    _set_alert(buyer_client, buyer_csrf, listing.id, True)
    edited = owner_client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": published["revision"], "price": {"amount": "10000.00", "currency": "BYN"}},
        headers=_csrf(owner_csrf),
    )
    assert edited.status_code == 200, edited.text
    _set_submitted_revision(factory, listing.id, edited.json()["listing"]["revision"])
    _approve(moderator_client, moderator_csrf, listing.id, edited.json()["listing"]["revision"])

    with factory() as db:
        outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.price_event_id.is_not(None),
                NotificationOutbox.listing_id == listing.id,
            )
        )
        assert outbox is not None
        outbox_id = outbox.id
    return {
        "factory": factory,
        "listing_id": listing.id,
        "buyer_id": buyer.id,
        "company_id": company_id,
        "outbox_id": outbox_id,
    }


def _set_alert(client: TestClient, csrf: str, listing_id, enabled: bool):
    response = client.put(
        f"/api/v1/me/favorites/{listing_id}/price-drop-alert",
        json={"enabled": enabled},
        headers=_csrf(csrf),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_favorite_price_drop_alert_requires_explicit_opt_in_and_can_be_unsubscribed(integration):
    factory = integration["SessionLocal"]
    owner, _ = _add_user(factory, "price-owner")
    buyer, buyer_email = _add_user(factory, "price-buyer")
    listing = _add_listing(factory, owner.id)
    client = _client(integration)
    csrf = _login(client, buyer_email)
    favorite_path = f"/api/v1/me/favorites/{listing.id}"
    alert_path = f"{favorite_path}/price-drop-alert"

    assert client.put(favorite_path, headers=_csrf(csrf)).status_code == 200
    favorite = client.get("/api/v1/me/favorites").json()["items"][0]
    assert favorite["price_drop_notifications_enabled"] is False

    enabled = client.put(alert_path, json={"enabled": True}, headers=_csrf(csrf))
    assert enabled.status_code == 200, enabled.text
    assert enabled.json() == {"enabled": True}
    favorite = client.get("/api/v1/me/favorites").json()["items"][0]
    assert favorite["price_drop_notifications_enabled"] is True

    disabled = client.put(alert_path, json={"enabled": False}, headers=_csrf(csrf))
    assert disabled.status_code == 200, disabled.text
    assert disabled.json() == {"enabled": False}
    favorite = client.get("/api/v1/me/favorites").json()["items"][0]
    assert favorite["price_drop_notifications_enabled"] is False

    client.delete(favorite_path, headers=_csrf(csrf))
    assert client.put(alert_path, json={"enabled": True}, headers=_csrf(csrf)).status_code == 404


def test_only_approved_price_changes_create_history_and_same_currency_drops_notify_once(integration):
    factory = integration["SessionLocal"]
    owner, owner_email = _add_user(factory, "price-publisher")
    moderator, moderator_email = _add_user(factory, "price-moderator", role="moderator")
    buyer, buyer_email = _add_user(factory, "price-opted-in")
    quiet_buyer, quiet_email = _add_user(factory, "price-not-opted-in")
    listing = _add_listing(factory, owner.id, status="pending_review")
    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner_email)
    moderator_client = _client(integration)
    moderator_csrf = _login(moderator_client, moderator_email)
    buyer_client = _client(integration)
    buyer_csrf = _login(buyer_client, buyer_email)
    quiet_client = _client(integration)
    quiet_csrf = _login(quiet_client, quiet_email)

    before_publication = buyer_client.get(f"/api/v1/listings/{listing.id}/price-history")
    assert before_publication.status_code == 404

    published = _approve(moderator_client, moderator_csrf, listing.id, 1)
    assert published["status"] == "active"
    first_history = buyer_client.get(f"/api/v1/listings/{listing.id}/price-history")
    assert first_history.status_code == 200, first_history.text
    assert [
        (item["event_type"], item["amount"], item["currency"], item["previous_amount"])
        for item in first_history.json()["items"]
    ] == [("published", "15000.00", "USD", None)]

    for client, csrf in ((buyer_client, buyer_csrf), (quiet_client, quiet_csrf), (owner_client, owner_csrf)):
        assert client.put(f"/api/v1/me/favorites/{listing.id}", headers=_csrf(csrf)).status_code == 200
    _set_alert(buyer_client, buyer_csrf, listing.id, True)
    _set_alert(owner_client, owner_csrf, listing.id, True)

    changed_currency = owner_client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": published["revision"], "price": {"amount": "12000.00", "currency": "BYN"}},
        headers=_csrf(owner_csrf),
    )
    assert changed_currency.status_code == 200, changed_currency.text
    _set_submitted_revision(factory, listing.id, changed_currency.json()["listing"]["revision"])
    after_currency_change = _approve(
        moderator_client, moderator_csrf, listing.id, changed_currency.json()["listing"]["revision"]
    )
    with factory() as db:
        assert db.scalar(
            select(func.count(NotificationOutbox.id)).where(NotificationOutbox.listing_id == listing.id)
        ) == 0

    lower_same_currency = owner_client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": after_currency_change["revision"], "price": {"amount": "11000.00", "currency": "BYN"}},
        headers=_csrf(owner_csrf),
    )
    assert lower_same_currency.status_code == 200, lower_same_currency.text
    _set_submitted_revision(factory, listing.id, lower_same_currency.json()["listing"]["revision"])
    approved_drop = _approve(
        moderator_client, moderator_csrf, listing.id, lower_same_currency.json()["listing"]["revision"]
    )
    assert approved_drop["status"] == "active"

    with factory() as db:
        events = db.scalars(
            select(ListingPriceEvent).where(ListingPriceEvent.listing_id == listing.id).order_by(ListingPriceEvent.revision)
        ).all()
        assert [(row.event_type, str(row.price_amount), row.currency) for row in events] == [
            ("published", "15000.00", "USD"),
            ("changed", "12000.00", "BYN"),
            ("changed", "11000.00", "BYN"),
        ]
        outboxes = db.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.price_event_id.is_not(None),
                NotificationOutbox.listing_id == listing.id,
            )
        ).all()
        assert len(outboxes) == 1
        assert outboxes[0].user_id == buyer.id
        assert outboxes[0].listing_id == listing.id
        assert outboxes[0].payload["url"] == f"/cars/{listing.slug}/{listing.slug}/{listing.id}"
        assert "12000.00 BYN" in outboxes[0].payload["body"]
        assert "11000.00 BYN" in outboxes[0].payload["body"]
        outbox_id = outboxes[0].id

    from app.worker import _deliver_notification

    _deliver_notification(outbox_id)
    _deliver_notification(outbox_id)
    inbox = buyer_client.get("/api/v1/me/notifications").json()["items"]
    assert len(inbox) == 1
    assert inbox[0]["listing_id"] == str(listing.id)
    assert "11000.00 BYN" in inbox[0]["body"]
    assert quiet_client.get("/api/v1/me/notifications").json()["items"] == []
    assert owner_client.get("/api/v1/me/notifications").json()["items"] == []
    with factory() as db:
        assert db.scalar(
            select(func.count(UserNotification.id)).where(UserNotification.user_id == buyer.id)
        ) == 1
        assert db.scalar(select(NotificationOutbox.status).where(NotificationOutbox.id == outbox_id)) == "delivered"


def test_legacy_active_listing_records_silent_baseline_before_first_seller_edit(integration):
    factory = integration["SessionLocal"]
    owner, owner_email = _add_user(factory, "legacy-price-owner")
    moderator, moderator_email = _add_user(factory, "legacy-price-moderator", role="moderator")
    buyer, buyer_email = _add_user(factory, "legacy-price-buyer")
    listing = _add_listing(factory, owner.id, status="active", amount="15000.00", currency="USD")

    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner_email)
    moderator_client = _client(integration)
    moderator_csrf = _login(moderator_client, moderator_email)
    buyer_client = _client(integration)
    buyer_csrf = _login(buyer_client, buyer_email)
    assert buyer_client.put(
        f"/api/v1/me/favorites/{listing.id}", headers=_csrf(buyer_csrf)
    ).status_code == 200
    _set_alert(buyer_client, buyer_csrf, listing.id, True)

    edited = owner_client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": listing.revision, "price": {"amount": "13000.00", "currency": "USD"}},
        headers=_csrf(owner_csrf),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["listing"]["status"] == "draft"

    with factory() as db:
        events = db.scalars(
            select(ListingPriceEvent)
            .where(ListingPriceEvent.listing_id == listing.id)
            .order_by(ListingPriceEvent.revision)
        ).all()
        assert [(event.event_type, str(event.price_amount), event.currency, event.previous_price_amount) for event in events] == [
            ("baseline", "15000.00", "USD", None)
        ]
        assert db.scalar(
            select(func.count(NotificationOutbox.id)).where(NotificationOutbox.listing_id == listing.id)
        ) == 0

    edited_revision = edited.json()["listing"]["revision"]
    _set_submitted_revision(factory, listing.id, edited_revision)
    _approve(moderator_client, moderator_csrf, listing.id, edited_revision)

    with factory() as db:
        events = db.scalars(
            select(ListingPriceEvent)
            .where(ListingPriceEvent.listing_id == listing.id)
            .order_by(ListingPriceEvent.revision)
        ).all()
        assert [event.event_type for event in events] == ["baseline", "changed"]
        assert str(events[1].previous_price_amount) == "15000.00"
        assert str(events[1].price_amount) == "13000.00"
        outbox = db.scalar(select(NotificationOutbox).where(NotificationOutbox.listing_id == listing.id))
        assert outbox is not None
        assert outbox.price_event_id == events[1].id


def test_price_drop_delivery_rechecks_opt_in_and_listing_visibility(integration):
    factory = integration["SessionLocal"]
    owner, owner_email = _add_user(factory, "price-visibility-owner")
    moderator, moderator_email = _add_user(factory, "price-visibility-moderator", role="moderator")
    buyer, buyer_email = _add_user(factory, "price-visibility-buyer")
    listing = _add_listing(factory, owner.id, status="pending_review", amount="12000.00", currency="BYN")
    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner_email)
    moderator_client = _client(integration)
    moderator_csrf = _login(moderator_client, moderator_email)
    buyer_client = _client(integration)
    buyer_csrf = _login(buyer_client, buyer_email)

    published = _approve(moderator_client, moderator_csrf, listing.id, 1)
    assert buyer_client.put(f"/api/v1/me/favorites/{listing.id}", headers=_csrf(buyer_csrf)).status_code == 200
    _set_alert(buyer_client, buyer_csrf, listing.id, True)
    edited = owner_client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": published["revision"], "price": {"amount": "10000.00", "currency": "BYN"}},
        headers=_csrf(owner_csrf),
    )
    assert edited.status_code == 200, edited.text
    _set_submitted_revision(factory, listing.id, edited.json()["listing"]["revision"])
    _approve(moderator_client, moderator_csrf, listing.id, edited.json()["listing"]["revision"])

    with factory() as db:
        outbox = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.price_event_id.is_not(None),
                NotificationOutbox.listing_id == listing.id,
            )
        )
        assert outbox is not None
        outbox_id = outbox.id
        favorite = db.scalar(select(Favorite).where(Favorite.user_id == buyer.id, Favorite.listing_id == listing.id))
        favorite.price_drop_notifications_enabled = False
        listing_row = db.get(Listing, listing.id)
        listing_row.status = "paused"
        db.commit()

    from app.worker import _deliver_notification

    _deliver_notification(outbox_id)
    with factory() as db:
        outbox = db.get(NotificationOutbox, outbox_id)
        assert outbox.status == "cancelled"
        assert outbox.last_error == "price_drop_no_longer_eligible"
        assert db.scalar(
            select(func.count(UserNotification.id)).where(UserNotification.user_id == buyer.id)
        ) == 0


def test_pause_and_resume_without_a_price_change_do_not_add_history(integration):
    factory = integration["SessionLocal"]
    owner, owner_email = _add_user(factory, "price-resume-owner")
    moderator, moderator_email = _add_user(factory, "price-resume-moderator", role="moderator")
    listing = _add_listing(factory, owner.id, status="pending_review")
    owner_client = _client(integration)
    owner_csrf = _login(owner_client, owner_email)
    moderator_client = _client(integration)
    moderator_csrf = _login(moderator_client, moderator_email)
    published = _approve(moderator_client, moderator_csrf, listing.id, 1)

    paused = owner_client.post(
        f"/api/v1/listings/{listing.id}/pause",
        json={"expected_revision": published["revision"]},
        headers=_csrf(owner_csrf),
    )
    assert paused.status_code == 200, paused.text
    paused_listing = paused.json()["listing"]
    resumed = owner_client.post(
        f"/api/v1/listings/{listing.id}/resume",
        json={"expected_revision": paused_listing["revision"]},
        headers=_csrf(owner_csrf),
    )
    assert resumed.status_code == 200, resumed.text

    with factory() as db:
        history = db.scalars(
            select(ListingPriceEvent)
            .where(ListingPriceEvent.listing_id == listing.id)
            .order_by(ListingPriceEvent.revision)
        ).all()
        assert [(event.event_type, str(event.price_amount), event.currency) for event in history] == [
            ("published", "15000.00", "USD")
        ]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("favorite_removed", "price_drop_no_longer_eligible"),
        ("recipient_disabled", "price_drop_no_longer_eligible"),
        ("global_web_disabled", "price_drop_web_disabled"),
        ("company_unapproved", "price_drop_no_longer_eligible"),
    ],
)
def test_price_drop_delivery_rechecks_recipient_and_company_state(integration, mutation, expected_error):
    state = _queue_price_drop(
        integration,
        f"price-{mutation}",
        with_company=mutation == "company_unapproved",
    )
    factory = state["factory"]
    with factory() as db:
        if mutation == "favorite_removed":
            favorite = db.scalar(
                select(Favorite).where(
                    Favorite.user_id == state["buyer_id"],
                    Favorite.listing_id == state["listing_id"],
                )
            )
            assert favorite is not None
            db.delete(favorite)
        elif mutation == "recipient_disabled":
            recipient = db.get(User, state["buyer_id"])
            recipient.status = "disabled"
        elif mutation == "global_web_disabled":
            db.add(
                UserNotificationPreferences(
                    user_id=state["buyer_id"],
                    web_enabled=False,
                    email_enabled=True,
                    revision=1,
                )
            )
        elif mutation == "company_unapproved":
            company = db.get(Company, state["company_id"])
            company.status = "pending"
        db.commit()

    from app.worker import _deliver_notification

    _deliver_notification(state["outbox_id"])
    with factory() as db:
        outbox = db.get(NotificationOutbox, state["outbox_id"])
        assert outbox.status == "cancelled"
        assert outbox.last_error == expected_error
        assert db.scalar(
            select(func.count(UserNotification.id)).where(UserNotification.user_id == state["buyer_id"])
        ) == 0

