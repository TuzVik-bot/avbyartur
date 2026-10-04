"""Real PostgreSQL/API regressions for tariff revision and audit invariants."""

import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent, BillingOrder, BillingTariff, Listing, User
from app.security import hash_password


# These owner-entered amounts are explicit synthetic test fixtures, not catalog prices.
PASSWORD = "tariff-concurrency-admin-test-password"


def _admin_client(integration):
    user = User(
        email=f"tariff-concurrency-{uuid.uuid4().hex}@example.com",
        display_name="Synthetic tariff concurrency admin",
        password_hash=hash_password(PASSWORD),
        role="admin",
        status="active",
    )
    with integration["SessionLocal"]() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        admin_id = user.id
        email = user.email

    client = TestClient(integration["client"].app)
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client, {"X-CSRF-Token": login.json()["csrf_token"]}, admin_id


def _create_body(**changes):
    return {
        "code": f"synthetic-bump-{uuid.uuid4().hex[:16]}",
        "service_code": "bump",
        "name": "Synthetic test tariff",
        "amount": "12.34",
        "currency": "BYN",
        "duration_days": 7,
        "listing_quota": None,
        "status": "disabled",
        "reason": "Explicit synthetic tariff concurrency fixture",
        "confirmation": "CREATE_TARIFF",
        "current_password": PASSWORD,
        **changes,
    }


def _update_body(tariff, **changes):
    return {
        "name": tariff["name"],
        "amount": tariff["amount"],
        "currency": tariff["currency"],
        "duration_days": tariff["duration_days"],
        "listing_quota": tariff["listing_quota"],
        "status": tariff["status"],
        "expected_revision": tariff["revision"],
        "reason": "Synthetic tariff update regression fixture",
        "confirmation": "UPDATE_TARIFF",
        "current_password": PASSWORD,
        **changes,
    }


def _create_tariff(client, headers):
    response = client.post("/api/v1/admin/tariffs", json=_create_body(), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["tariff"]


def _tariff_audit_events(db, tariff_id):
    return db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == "billing_tariff", AuditEvent.entity_id == tariff_id)
    ).all()


def test_noop_tariff_update_preserves_revision_and_adds_no_audit(integration):
    client, headers, _ = _admin_client(integration)
    tariff = _create_tariff(client, headers)

    response = client.patch(
        f"/api/v1/admin/tariffs/{tariff['id']}",
        json=_update_body(tariff),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is False
    assert response.json()["tariff"]["revision"] == 1
    with integration["SessionLocal"]() as db:
        saved = db.get(BillingTariff, uuid.UUID(tariff["id"]))
        events = _tariff_audit_events(db, saved.id)
        assert saved.revision == 1
        assert [event.action for event in events] == ["billing_tariff_created"]


def test_replayed_applied_update_is_stale_and_keeps_order_snapshot(integration):
    client, headers, admin_id = _admin_client(integration)
    tariff = _create_tariff(client, headers)
    listing = Listing(
        owner_id=admin_id,
        slug=f"tariff-replay-{uuid.uuid4().hex}",
        title="Synthetic snapshot test listing",
        description="Synthetic order-history fixture",
        contact_phone="+375291234567",
        status="active",
        revision=1,
    )
    with integration["SessionLocal"]() as db:
        db.add(listing)
        db.flush()
        order = BillingOrder(
            user_id=admin_id,
            listing_id=listing.id,
            company_id=None,
            tariff_id=uuid.UUID(tariff["id"]),
            service_code="bump",
            tariff_code=tariff["code"],
            tariff_revision=1,
            amount=Decimal("12.34"),
            currency="BYN",
            duration_days=7,
            listing_quota=None,
            provider="synthetic-disabled-test",
            provider_reference=None,
            idempotency_key_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            request_digest=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(order)
        db.commit()
        order_id = order.id

    endpoint = f"/api/v1/admin/tariffs/{tariff['id']}"
    applied_request = _update_body(
        tariff,
        name="Synthetic tariff revised once",
        amount="23.45",
        duration_days=14,
        reason="Synthetic first application",
    )
    first = client.patch(endpoint, json=applied_request, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["changed"] is True
    assert first.json()["tariff"]["revision"] == 2

    replay = client.patch(endpoint, json=applied_request, headers=headers)
    assert replay.status_code == 409, replay.text
    assert replay.json()["code"] == "revision_conflict"

    with integration["SessionLocal"]() as db:
        saved = db.get(BillingTariff, uuid.UUID(tariff["id"]))
        order = db.get(BillingOrder, order_id)
        events = _tariff_audit_events(db, saved.id)
        assert saved.revision == 2
        assert saved.name == "Synthetic tariff revised once"
        assert saved.amount == Decimal("23.45")
        assert order.tariff_code == tariff["code"]
        assert order.tariff_revision == 1
        assert order.amount == Decimal("12.34")
        assert order.currency == "BYN"
        assert order.duration_days == 7
        assert [event.action for event in events].count("billing_tariff_updated") == 1
        update_event = next(event for event in events if event.action == "billing_tariff_updated")
        assert update_event.details["revision"] == 2
        assert update_event.details["after"]["amount"] == "23.45"


def test_two_global_admins_racing_same_revision_have_one_audited_winner(integration):
    first_client, first_headers, first_admin_id = _admin_client(integration)
    second_client, second_headers, second_admin_id = _admin_client(integration)
    assert first_admin_id != second_admin_id
    tariff = _create_tariff(first_client, first_headers)
    endpoint = f"/api/v1/admin/tariffs/{tariff['id']}"
    rendezvous = Barrier(2, timeout=5)

    attempts = (
        (
            first_client,
            first_headers,
            first_admin_id,
            {
                "name": "Synthetic update proposed by admin one",
                "amount": "22.11",
                "duration_days": 21,
                "reason": "Synthetic concurrent proposal one",
            },
        ),
        (
            second_client,
            second_headers,
            second_admin_id,
            {
                "name": "Synthetic update proposed by admin two",
                "amount": "33.22",
                "duration_days": 31,
                "reason": "Synthetic concurrent proposal two",
            },
        ),
    )

    def submit(attempt):
        client, headers, admin_id, changes = attempt
        rendezvous.wait()
        response = client.patch(
            endpoint,
            json=_update_body(tariff, expected_revision=1, **changes),
            headers=headers,
        )
        return admin_id, response

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="tariff-update") as pool:
        futures = [pool.submit(submit, attempt) for attempt in attempts]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(response.status_code for _, response in results) == [200, 409]
    winner_id, winner_response = next((admin_id, response) for admin_id, response in results if response.status_code == 200)
    loser_response = next(response for _, response in results if response.status_code == 409)
    assert winner_response.json()["changed"] is True
    assert winner_response.json()["tariff"]["revision"] == 2
    assert loser_response.json()["code"] == "revision_conflict"

    with integration["SessionLocal"]() as db:
        saved = db.get(BillingTariff, uuid.UUID(tariff["id"]))
        events = _tariff_audit_events(db, saved.id)
        update_events = [event for event in events if event.action == "billing_tariff_updated"]
        assert saved.revision == 2
        assert len(update_events) == 1
        assert update_events[0].actor_id == winner_id
        assert update_events[0].details["revision"] == 2
        assert update_events[0].details["after"]["name"] == saved.name
        assert update_events[0].details["after"]["amount"] == format(saved.amount, ".2f")
