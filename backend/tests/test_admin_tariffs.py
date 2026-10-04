"""Owner-managed tariffs stay explicit, versioned and isolated from order snapshots."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent, BillingOrder, BillingTariff, Listing, User
from app.security import hash_password

PASSWORD = "tariff-admin-test-password-123"


def client_for(integration, role="admin"):
    user = User(
        email=f"tariff-{uuid.uuid4().hex}@example.com",
        display_name="Управляющий тарифами",
        password_hash=hash_password(PASSWORD),
        role=role,
        status="active",
    )
    with integration["SessionLocal"]() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    client = TestClient(integration["client"].app)
    login = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client, {"X-CSRF-Token": login.json()["csrf_token"]}, user


def create_body(**changes):
    return {
        "code": "bump-7-days",
        "service_code": "bump",
        "name": "Поднять объявление на 7 дней",
        "amount": "12.34",
        "currency": "BYN",
        "duration_days": 7,
        "listing_quota": None,
        "status": "disabled",
        "reason": "Тариф и цена утверждены владельцем",
        "confirmation": "CREATE_TARIFF",
        "current_password": PASSWORD,
        **changes,
    }


def update_body(tariff, **changes):
    return {
        "name": "Поднять объявление на 30 дней",
        "amount": "25.67",
        "currency": "BYN",
        "duration_days": 30,
        "listing_quota": None,
        "status": "active",
        "expected_revision": tariff["revision"],
        "reason": "Владелец согласовал новую цену и длительность",
        "confirmation": "UPDATE_TARIFF",
        "current_password": PASSWORD,
        **changes,
    }


def create_tariff(client, headers, **changes):
    response = client.post("/api/v1/admin/tariffs", json=create_body(**changes), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["tariff"]


def test_tariff_management_is_admin_only_and_starts_without_fake_prices(integration):
    guest = TestClient(integration["client"].app)
    assert guest.get("/api/v1/admin/tariffs").status_code == 401

    for role in ("user", "moderator"):
        client, headers, _ = client_for(integration, role)
        assert client.get("/api/v1/admin/tariffs").status_code == 403
        assert client.post("/api/v1/admin/tariffs", json=create_body(), headers=headers).status_code == 403
        target = f"/api/v1/admin/tariffs/{uuid.uuid4()}"
        assert client.patch(target, json=update_body({"revision": 1}), headers=headers).status_code == 403
        delete = {"expected_revision": 1, "reason": "Проверка прав", "confirmation": "DELETE_TARIFF", "current_password": PASSWORD}
        assert client.request("DELETE", target, json=delete, headers=headers).status_code == 403

    client, _, _ = client_for(integration)
    response = client.get("/api/v1/admin/tariffs")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 25}


def test_tariff_creation_requires_csrf_step_up_and_exact_owner_input(integration):
    client, headers, _ = client_for(integration)
    endpoint = "/api/v1/admin/tariffs"

    assert client.post(endpoint, json=create_body()).status_code == 403
    assert client.post(endpoint, json=create_body(current_password="wrong"), headers=headers).status_code == 401
    assert client.post(endpoint, json=create_body(confirmation=""), headers=headers).status_code == 422
    assert client.post(endpoint, json=create_body(reason="  "), headers=headers).status_code == 422
    for amount in ("0.00", "12.345", "10000000000.00", 12.34):
        assert client.post(endpoint, json=create_body(amount=amount), headers=headers).status_code == 422
    assert client.post(endpoint, json=create_body(service_code="bump", listing_quota=10), headers=headers).status_code == 422

    tariff = create_tariff(client, headers)
    assert tariff["amount"] == "12.34"
    assert tariff["status"] == "disabled"
    assert tariff["revision"] == 1
    assert client.get("/api/v1/billing/tariffs").json() == []
    audit_response = client.get("/api/v1/admin/audit", params={"entity_type": "billing_tariff"})
    assert audit_response.status_code == 200, audit_response.text
    audit_item = audit_response.json()["items"][0]
    assert audit_item["action"] == "billing_tariff_created"
    assert audit_item["details"]["reason"] == "Тариф и цена утверждены владельцем"

    with integration["SessionLocal"]() as db:
        row = db.get(BillingTariff, uuid.UUID(tariff["id"]))
        assert row is not None and row.amount == Decimal("12.34")
        events = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == row.id)).all()
        assert len(events) == 1
        assert events[0].action == "billing_tariff_created"
        assert events[0].details["reason"] == "Тариф и цена утверждены владельцем"
        assert PASSWORD not in str(events[0].details)


def test_dealer_package_requires_owner_defined_capacity(integration):
    client, headers, _ = client_for(integration)
    invalid = create_body(code="dealer-package", service_code="dealer_package", status="active", listing_quota=None)
    assert client.post("/api/v1/admin/tariffs", json=invalid, headers=headers).status_code == 422

    tariff = create_tariff(
        client, headers, code="dealer-package", service_code="dealer_package", name="Пакет на 50 объявлений",
        status="active", listing_quota=50,
    )
    assert tariff["listing_quota"] == 50
    public = client.get("/api/v1/billing/tariffs")
    assert public.status_code == 200, public.text
    assert public.json()[0]["listing_quota"] == 50


def test_tariff_update_is_versioned_and_does_not_rewrite_order_snapshot(integration):
    client, headers, admin = client_for(integration)
    tariff = create_tariff(client, headers, status="active")
    endpoint = f"/api/v1/admin/tariffs/{tariff['id']}"
    listing = Listing(
        owner_id=admin.id,
        slug=f"tariff-{uuid.uuid4().hex}",
        title="Объявление для снимка заказа",
        description="Тестовая запись",
        contact_phone="+375291234567",
        status="active",
        revision=1,
    )
    with integration["SessionLocal"]() as db:
        db.add(listing)
        db.commit()
        listing_id = listing.id

    blocked_checkout = client.post(
        "/api/v1/billing/orders",
        json={"listing_id": str(listing_id), "tariff_id": tariff["id"]},
        headers={**headers, "Idempotency-Key": "tariff-checkout-stays-disabled"},
    )
    assert blocked_checkout.status_code == 503, blocked_checkout.text
    assert blocked_checkout.json()["code"] == "commerce_provider_unconfigured"

    with integration["SessionLocal"]() as db:
        order = BillingOrder(
            user_id=admin.id,
            listing_id=listing_id,
            company_id=None,
            tariff_id=uuid.UUID(tariff["id"]),
            service_code="bump",
            tariff_code=tariff["code"],
            tariff_revision=1,
            amount=Decimal("12.34"),
            currency="BYN",
            duration_days=7,
            listing_quota=None,
            provider="test-disabled",
            provider_reference=None,
            idempotency_key_digest=hashlib.sha256(b"tariff-snapshot").hexdigest(),
            request_digest=hashlib.sha256(b"tariff-snapshot-request").hexdigest(),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(order)
        db.commit()
        order_id = order.id

    assert client.patch(endpoint, json=update_body(tariff)).status_code == 403
    assert client.patch(endpoint, json=update_body(tariff, current_password="wrong"), headers=headers).status_code == 401
    assert client.patch(endpoint, json=update_body(tariff, expected_revision=0), headers=headers).status_code == 409
    assert client.patch(endpoint, json=update_body(tariff, code="different-code"), headers=headers).status_code == 422
    assert client.patch(endpoint, json=update_body(tariff, service_code="top"), headers=headers).status_code == 422

    updated = client.patch(endpoint, json=update_body(tariff, status="disabled"), headers=headers)
    assert updated.status_code == 200, updated.text
    assert updated.json()["changed"] is True
    saved = updated.json()["tariff"]
    assert saved["revision"] == 2
    assert saved["amount"] == "25.67"
    assert saved["duration_days"] == 30
    assert saved["code"] == tariff["code"] and saved["service_code"] == "bump"
    assert client.get("/api/v1/billing/tariffs").json() == []

    with integration["SessionLocal"]() as db:
        order = db.get(BillingOrder, order_id)
        saved_row = db.get(BillingTariff, uuid.UUID(tariff["id"]))
        assert saved_row.amount == Decimal("25.67") and saved_row.revision == 2
        assert order is not None
        assert order.tariff_code == tariff["code"] and order.tariff_revision == 1
        assert order.amount == Decimal("12.34") and order.duration_days == 7
        event = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == saved_row.id, AuditEvent.action == "billing_tariff_updated"))
        assert event is not None
        assert event.details["before"]["amount"] == "12.34"
        assert event.details["after"]["amount"] == "25.67"
        event.details = {
            **event.details,
            "before": {**event.details["before"], "password": "never-return-tariff-password", "token": "never-return-tariff-token"},
            "after": {**event.details["after"], "password": "never-return-new-password", "token": "never-return-new-token"},
        }
        db.commit()

    audit_response = client.get("/api/v1/admin/audit", params={"entity_type": "billing_tariff"})
    assert audit_response.status_code == 200, audit_response.text
    updated_event = next(item for item in audit_response.json()["items"] if item["action"] == "billing_tariff_updated")
    before = updated_event["details"]["before"]
    after = updated_event["details"]["after"]
    assert before == {
        "code": "bump-7-days", "service_code": "bump", "name": "Поднять объявление на 7 дней",
        "amount": "12.34", "currency": "BYN", "duration_days": 7, "listing_quota": None, "status": "active",
    }
    assert after == {
        "code": "bump-7-days", "service_code": "bump", "name": "Поднять объявление на 30 дней",
        "amount": "25.67", "currency": "BYN", "duration_days": 30, "listing_quota": None, "status": "disabled",
    }
    assert updated_event["details"]["reason"] == "Владелец согласовал новую цену и длительность"
    assert "never-return" not in audit_response.text

    with integration["SessionLocal"]() as db:
        db.add(AuditEvent(
            actor_id=admin.id, entity_type="user", entity_id=admin.id, action="admin_user_updated",
            details={"reason": "Существующий формат аудита", "to_status": "blocked", "before": {"password": "never-return-user-password"}},
        ))
        db.commit()
    existing_audit = client.get("/api/v1/admin/audit", params={"entity_type": "user", "entity_id": str(admin.id)})
    assert existing_audit.status_code == 200, existing_audit.text
    assert existing_audit.json()["items"][0]["details"] == {"reason": "Существующий формат аудита", "to_status": "blocked"}
    assert "never-return-user-password" not in existing_audit.text


def test_tariff_delete_requires_confirmation_and_refuses_referenced_history(integration):
    client, headers, admin = client_for(integration)
    tariff = create_tariff(client, headers)
    listing = Listing(
        owner_id=admin.id,
        slug=f"tariff-history-{uuid.uuid4().hex}",
        title="Историческое объявление",
        description="Тестовая запись",
        contact_phone="+375291234567",
        status="active",
        revision=1,
    )
    with integration["SessionLocal"]() as db:
        db.add(listing)
        db.flush()
        db.add(BillingOrder(
            user_id=admin.id, listing_id=listing.id, company_id=None, tariff_id=uuid.UUID(tariff["id"]),
            service_code="bump", tariff_code=tariff["code"], tariff_revision=1, amount=Decimal("12.34"),
            currency="BYN", duration_days=7, listing_quota=None, provider="test", provider_reference=None,
            idempotency_key_digest=hashlib.sha256(b"tariff-delete-history").hexdigest(),
            request_digest=hashlib.sha256(b"tariff-delete-history-request").hexdigest(), status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ))
        db.commit()

    endpoint = f"/api/v1/admin/tariffs/{tariff['id']}"
    delete_body = {"expected_revision": 1, "reason": "Проверка сохранения истории", "confirmation": "DELETE_TARIFF", "current_password": PASSWORD}
    assert client.request("DELETE", endpoint, json=delete_body).status_code == 403
    assert client.request("DELETE", endpoint, json={**delete_body, "expected_revision": 0}, headers=headers).status_code == 409
    response = client.request("DELETE", endpoint, json=delete_body, headers=headers)
    assert response.status_code == 409 and response.json()["code"] == "tariff_referenced"
    with integration["SessionLocal"]() as db:
        assert db.get(BillingTariff, uuid.UUID(tariff["id"])) is not None


def test_unused_tariff_can_be_deleted_with_audited_reason_and_revision(integration):
    client, headers, _ = client_for(integration)
    tariff = create_tariff(client, headers)
    endpoint = f"/api/v1/admin/tariffs/{tariff['id']}"
    body = {"expected_revision": 1, "reason": "Удаление ошибочно заведённого тарифа", "confirmation": "DELETE_TARIFF", "current_password": PASSWORD}
    assert client.request("DELETE", endpoint, json={**body, "confirmation": "DELETE"}, headers=headers).status_code == 422
    response = client.request("DELETE", endpoint, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True}
    assert client.get("/api/v1/admin/tariffs").json()["items"] == []
    with integration["SessionLocal"]() as db:
        event = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(tariff["id"]), AuditEvent.action == "billing_tariff_deleted"))
        assert event is not None
        assert event.details["reason"] == body["reason"]
        assert event.details["revision"] == 1
