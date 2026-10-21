"""Commerce contract tests using only a deterministic payment provider."""

from __future__ import annotations

import hashlib
import hmac
import json
import runpy
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from app import models
from app.db import get_db
from app.main import app
from app.billing_services import (
    CallbackPayload,
    CheckoutResult,
    DisabledPaymentProvider,
    HmacPaymentProvider,
    InvalidPaymentSignature,
    OrderTarget,
    activate_paid_order,
    create_order_checkout,
    get_payment_provider,
    process_payment_callback,
)
from app.runtime_settings import RuntimeSetting
from app.security import hash_password
from app.services import quota_limit


PASSWORD = "billing-test-password-123"
_AUTO_LISTING_QUOTA = object()


class FakePaymentProvider:
    name = "test"
    is_configured = True

    def __init__(self) -> None:
        self.checkouts: list[tuple[uuid.UUID, str]] = []

    def create_checkout(self, order: models.BillingOrder, *, idempotency_key: str) -> CheckoutResult:
        self.checkouts.append((order.id, idempotency_key))
        return CheckoutResult(
            provider=self.name,
            provider_reference=f"pay-{order.id}",
            checkout_url=f"https://pay.invalid/{order.id}",
        )

    def verify_callback(self, raw_body: bytes, signature: str | None) -> CallbackPayload:
        body = json.loads(raw_body)
        return CallbackPayload(
            provider=self.name,
            provider_event_id=body["event_id"],
            provider_reference=body["provider_reference"],
            status=body["status"],
            amount=Decimal(str(body["amount"])),
            currency=body["currency"],
            event_type=body.get("event_type", "payment.updated"),
        )


def add_user(factory, label: str = "billing-user") -> models.User:
    user = models.User(
        email=f"{label}-{uuid.uuid4().hex[:10]}@example.com",
        display_name=label,
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


def add_listing(factory, owner_id: uuid.UUID, *, status: str = "active") -> models.Listing:
    listing = models.Listing(
        owner_id=owner_id,
        slug=f"billing-{uuid.uuid4().hex}",
        title="Billing test listing",
        description="Billing test listing",
        contact_phone="+375291234567",
        status=status,
        revision=1,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def add_tariff(
    factory,
    *,
    service_code: str = "bump",
    amount: str = "12.50",
    listing_quota: int | None | object = _AUTO_LISTING_QUOTA,
) -> models.BillingTariff:
    if listing_quota is _AUTO_LISTING_QUOTA:
        listing_quota = 100 if service_code == "dealer_package" else None
    tariff = models.BillingTariff(
        code=f"{service_code}-{uuid.uuid4().hex[:8]}",
        service_code=service_code,
        name=f"{service_code} test tariff",
        amount=Decimal(amount),
        currency="BYN",
        duration_days=7,
        listing_quota=listing_quota,
        status="active",
        revision=1,
    )
    with factory() as db:
        db.add(tariff)
        db.commit()
        db.refresh(tariff)
        db.expunge(tariff)
    return tariff


def add_company(factory, owner_id: uuid.UUID) -> models.Company:
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    company = models.Company(
        owner_id=owner_id,
        name=f"Billing Dealer {suffix}",
        slug=f"billing-dealer-{suffix}",
        unp=str(suffix),
        address="Minsk",
        phone="+375291234567",
        status="approved",
        revision=1,
    )
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        db.expunge(company)
    return company


def callback_body(
    order: models.BillingOrder,
    *,
    event_id: str,
    amount: str | None = None,
    currency: str | None = None,
    status: str = "succeeded",
) -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "provider_reference": order.provider_reference,
            "status": status,
            "amount": amount if amount is not None else str(order.amount),
            "currency": currency if currency is not None else order.currency,
        },
        separators=(",", ":"),
    ).encode()


def create_checkout(db, user, listing, tariff, provider, key: str):
    return create_order_checkout(
        db,
        user=user,
        target=OrderTarget(listing_id=listing.id),
        tariff_id=tariff.id,
        idempotency_key=key,
        provider=provider,
    )


def billing_client(integration, provider=None) -> TestClient:
    # Exercise the same middleware, exception handlers, and router registry as
    # the actual FastAPI app. The integration fixture supplies the disposable
    # database dependency; provider overrides are reset between test cases.
    test_app = app
    factory = integration["SessionLocal"]

    def override_db():
        with factory() as db:
            yield db

    test_app.dependency_overrides[get_db] = override_db
    if provider is not None:
        test_app.dependency_overrides[get_payment_provider] = lambda: provider
    else:
        test_app.dependency_overrides.pop(get_payment_provider, None)
    return TestClient(test_app, base_url="http://testserver")


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_disabled_provider_never_fakes_checkout(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)

    with factory() as db:
        with pytest.raises(HTTPException) as raised:
            create_checkout(db, user, listing, tariff, DisabledPaymentProvider(), "disabled-checkout")
    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "commerce_provider_unconfigured"
    with factory() as db:
        assert db.scalar(select(models.BillingOrder.id)) is None
        assert db.scalar(select(models.PaymentAttempt.id)) is None


def test_billing_routes_scope_orders_and_expose_only_owner_configured_prices(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, "billing-route-owner")
    other = add_user(factory, "billing-route-other")
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    provider = FakePaymentProvider()
    client = billing_client(integration, provider)
    other_client = billing_client(integration, provider)

    tariffs = client.get("/api/v1/billing/tariffs")
    assert tariffs.status_code == 200, tariffs.text
    assert [row["id"] for row in tariffs.json()] == [str(tariff.id)]

    csrf = login(client, user.email)
    login(other_client, other.email)
    payload = {"listing_id": str(listing.id), "tariff_id": str(tariff.id)}
    missing_csrf = client.post(
        "/api/v1/billing/orders", json=payload, headers={"Idempotency-Key": "route-no-csrf"},
    )
    assert missing_csrf.status_code == 403

    created = client.post(
        "/api/v1/billing/orders",
        json=payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "route-checkout"},
    )
    assert created.status_code == 200, created.text
    order = created.json()["order"]
    assert created.json()["checkout_url"] == f"https://pay.invalid/{order['id']}"
    replay = client.post(
        "/api/v1/billing/orders",
        json=payload,
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "route-checkout"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["order"]["id"] == order["id"]

    detail = client.get(f"/api/v1/billing/orders/{order['id']}")
    assert detail.status_code == 200, detail.text
    assert "checkout_url" not in detail.json()
    history = client.get("/api/v1/billing/orders")
    assert history.status_code == 200, history.text
    assert [row["id"] for row in history.json()["items"]] == [order["id"]]
    assert other_client.get(f"/api/v1/billing/orders/{order['id']}").status_code == 404

    raw = json.dumps(
        {
            "event_id": "evt-route",
            "provider_reference": order["provider_reference"],
            "status": "succeeded",
            "amount": order["amount"],
            "currency": order["currency"],
        },
        separators=(",", ":"),
    )
    callback = client.post("/api/v1/billing/callbacks/test", content=raw)
    assert callback.status_code == 200, callback.text
    assert callback.json() == {"received": True, "duplicate": False, "order_id": order["id"], "status": "paid"}
    callback_replay = client.post("/api/v1/billing/callbacks/test", content=raw)
    assert callback_replay.status_code == 200, callback_replay.text
    assert callback_replay.json()["duplicate"] is True


def test_default_route_provider_returns_503_without_recording_checkout(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory, "billing-disabled-route")
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    client = billing_client(integration)
    csrf = login(client, user.email)
    response = client.post(
        "/api/v1/billing/orders",
        json={"listing_id": str(listing.id), "tariff_id": str(tariff.id)},
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "disabled-route"},
    )
    assert response.status_code == 503
    with factory() as db:
        assert db.scalar(select(models.BillingOrder.id)) is None
        assert db.scalar(select(models.PaymentAttempt.id)) is None


def test_payment_callback_body_limit_is_enforced_before_parsing(integration):
    client = billing_client(integration, FakePaymentProvider())
    response = client.post(
        "/api/v1/billing/callbacks/test",
        content=b"{" + b" " * (64 * 1024) + b"}",
    )
    assert response.status_code == 413


def test_order_commercial_snapshot_is_immutable(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    with factory() as db:
        checkout = create_checkout(db, user, listing, tariff, FakePaymentProvider(), "immutable-order")
        db.commit()
        order_id = checkout.order.id

    with factory() as db:
        order = db.get(models.BillingOrder, order_id)
        order.amount = Decimal("1.00")
        with pytest.raises(ValueError, match="commercial snapshot fields are immutable"):
            db.flush()
        db.rollback()


def test_checkout_snapshots_tariff_and_callback_activates_once(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    provider = FakePaymentProvider()

    with factory() as db:
        checkout = create_checkout(db, user, listing, tariff, provider, "checkout-1")
        db.commit()
        order_id = checkout.order.id
        assert checkout.order.amount == Decimal("12.50")
        assert checkout.order.duration_days == 7
        assert checkout.order.tariff_revision == tariff.revision
        assert checkout.order.status == "pending"
        assert checkout.order.provider_reference == f"pay-{checkout.order.id}"
        assert checkout.checkout_url == f"https://pay.invalid/{checkout.order.id}"

    with factory() as db:
        order = db.get(models.BillingOrder, order_id)
        result = process_payment_callback(
            db, provider=provider, raw_body=callback_body(order, event_id="evt-1"), signature=None,
        )
        db.commit()
        assert result.order.status == "paid"
        promotion = db.scalar(select(models.ListingPromotion).where(models.ListingPromotion.order_id == order_id))
        assert promotion is not None
        assert promotion.status == "active"

    with factory() as db:
        order = db.get(models.BillingOrder, order_id)
        replay = process_payment_callback(
            db, provider=provider, raw_body=callback_body(order, event_id="evt-1"), signature=None,
        )
        db.commit()
        assert replay.duplicate is True
        assert len(db.scalars(select(models.ListingPromotion).where(models.ListingPromotion.order_id == order_id)).all()) == 1
        assert len(db.scalars(select(models.PaymentCallbackEvent).where(models.PaymentCallbackEvent.provider_event_id == "evt-1")).all()) == 1


def test_callback_validates_amount_and_currency(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    provider = FakePaymentProvider()
    with factory() as db:
        checkout = create_checkout(db, user, listing, tariff, provider, "checkout-mismatch")
        db.commit()

    for kwargs, expected_code in (({"amount": "99.00"}, "payment_amount_mismatch"),
                                  ({"currency": "USD"}, "payment_currency_mismatch")):
        with factory() as db:
            order = db.get(models.BillingOrder, checkout.order.id)
            raw = callback_body(order, event_id=f"evt-{expected_code}", **kwargs)
            with pytest.raises(HTTPException) as raised:
                process_payment_callback(db, provider=provider, raw_body=raw, signature=None)
            assert raised.value.status_code == 409
            assert raised.value.detail["code"] == expected_code


def test_hmac_callback_rejects_missing_or_invalid_signature():
    provider = HmacPaymentProvider(name="hmac-test", secret=b"test-secret")
    raw = b'{"event_id":"evt","provider_reference":"pay","status":"succeeded","amount":"1.00","currency":"BYN"}'
    for signature in (None, "0" * 64):
        with pytest.raises(InvalidPaymentSignature):
            provider.verify_callback(raw, signature)
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    parsed = provider.verify_callback(raw, signature)
    assert parsed.provider_event_id == "evt"
    assert parsed.amount == Decimal("1.00")


def test_callback_event_id_cannot_be_replayed_with_changed_payload(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    provider = FakePaymentProvider()
    with factory() as db:
        checkout = create_checkout(db, user, listing, tariff, provider, "callback-replay")
        db.commit()
    with factory() as db:
        order = db.get(models.BillingOrder, checkout.order.id)
        process_payment_callback(db, provider=provider, raw_body=callback_body(order, event_id="evt-replay"), signature=None)
        db.commit()
    with factory() as db:
        order = db.get(models.BillingOrder, checkout.order.id)
        changed = callback_body(order, event_id="evt-replay", amount="13.00")
        with pytest.raises(HTTPException) as raised:
            process_payment_callback(db, provider=provider, raw_body=changed, signature=None)
        assert raised.value.status_code == 409
        assert raised.value.detail["code"] == "provider_event_replay_conflict"


def make_paid_order(user, listing, tariff, key: str) -> models.BillingOrder:
    return models.BillingOrder(
        user_id=user.id,
        listing_id=listing.id,
        company_id=None,
        tariff_id=tariff.id,
        service_code=tariff.service_code,
        tariff_code=tariff.code,
        tariff_revision=tariff.revision,
        amount=tariff.amount,
        currency=tariff.currency,
        duration_days=tariff.duration_days,
        provider="test",
        idempotency_key_digest=hashlib.sha256(key.encode()).hexdigest(),
        request_digest=hashlib.sha256((key + "-request").encode()).hexdigest(),
        status="paid",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )


def test_activation_prevents_same_service_overlap_and_allows_other_services(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    bump = add_tariff(factory, service_code="bump")
    highlight = add_tariff(factory, service_code="highlight")
    with factory() as db:
        first = make_paid_order(user, listing, bump, "manual-1")
        second = make_paid_order(user, listing, bump, "manual-2")
        third = make_paid_order(user, listing, highlight, "manual-3")
        db.add_all([first, second, third])
        db.flush()
        activate_paid_order(db, first)
        db.commit()
        with pytest.raises(HTTPException) as raised:
            activate_paid_order(db, second)
        assert raised.value.status_code == 409
        assert raised.value.detail["code"] == "promotion_overlap"
        promotion = activate_paid_order(db, third)
        db.commit()
        assert promotion.service_code == "highlight"


def test_order_idempotency_is_scoped_to_same_target_and_tariff(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    first_listing = add_listing(factory, user.id)
    second_listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    provider = FakePaymentProvider()
    with factory() as db:
        first = create_checkout(db, user, first_listing, tariff, provider, "same-key")
        db.commit()
    with factory() as db:
        replay = create_checkout(db, user, first_listing, tariff, provider, "same-key")
        db.commit()
        assert replay.order.id == first.order.id
        assert replay.checkout_url == first.checkout_url
    with factory() as db:
        with pytest.raises(HTTPException) as raised:
            create_checkout(db, user, second_listing, tariff, provider, "same-key")
        assert raised.value.status_code == 409
        assert raised.value.detail["code"] == "idempotency_key_reused"


def test_out_of_order_failure_does_not_downgrade_paid_order(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    provider = FakePaymentProvider()
    with factory() as db:
        checkout = create_checkout(db, user, listing, tariff, provider, "out-of-order")
        db.commit()
    with factory() as db:
        order = db.get(models.BillingOrder, checkout.order.id)
        first_failure = process_payment_callback(
            db,
            provider=provider,
            raw_body=callback_body(order, event_id="evt-failed-first", status="failed"),
            signature=None,
        )
        db.commit()
        assert first_failure.order.status == "failed"
    with factory() as db:
        order = db.get(models.BillingOrder, checkout.order.id)
        success = process_payment_callback(
            db,
            provider=provider,
            raw_body=callback_body(order, event_id="evt-paid", status="succeeded"),
            signature=None,
        )
        db.commit()
        assert success.order.status == "paid"
    with factory() as db:
        order = db.get(models.BillingOrder, checkout.order.id)
        failure = process_payment_callback(
            db, provider=provider, raw_body=callback_body(order, event_id="evt-late-fail", status="failed"), signature=None,
        )
        db.commit()
        assert failure.order.status == "paid"
        assert failure.event.outcome == "ignored"


def test_dealer_package_uses_company_scope_and_company_promotion(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, "billing-dealer-owner")
    outsider = add_user(factory, "billing-dealer-outsider")
    company = add_company(factory, owner.id)
    tariff = add_tariff(factory, service_code="dealer_package", amount="50.00", listing_quota=7)
    provider = FakePaymentProvider()

    with factory() as db:
        with pytest.raises(HTTPException) as raised:
            create_order_checkout(
                db,
                user=outsider,
                target=OrderTarget(company_id=company.id),
                tariff_id=tariff.id,
                idempotency_key="foreign-company-package",
                provider=provider,
            )
        assert raised.value.status_code == 403

    with factory() as db:
        checkout = create_order_checkout(
            db,
            user=owner,
            target=OrderTarget(company_id=company.id),
            tariff_id=tariff.id,
            idempotency_key="owner-company-package",
            provider=provider,
        )
        db.commit()
    with factory() as db:
        order = db.get(models.BillingOrder, checkout.order.id)
        result = process_payment_callback(
            db,
            provider=provider,
            raw_body=callback_body(order, event_id="evt-company-package"),
            signature=None,
        )
        db.commit()
        assert result.order.status == "paid"
        promotion = db.scalar(
            select(models.ListingPromotion).where(models.ListingPromotion.order_id == order.id)
        )
        assert promotion.company_id == company.id
        assert promotion.listing_id is None
        assert promotion.service_code == "dealer_package"
        assert order.listing_quota == 7
        assert promotion.listing_quota == 7


def test_dealer_package_checkout_requires_an_explicit_configured_capacity(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, "billing-capacity-owner")
    company = add_company(factory, owner.id)
    tariff = add_tariff(factory, service_code="dealer_package", listing_quota=None)

    with factory() as db:
        with pytest.raises(HTTPException) as raised:
            create_order_checkout(
                db,
                user=owner,
                target=OrderTarget(company_id=company.id),
                tariff_id=tariff.id,
                idempotency_key="missing-package-capacity",
                provider=FakePaymentProvider(),
            )

    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "billing_tariff_capacity_unavailable"


def test_dealer_package_capacity_is_owner_configured_public_and_immutable(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory, "billing-capacity-snapshot-owner")
    company = add_company(factory, owner.id)
    tariff = add_tariff(factory, service_code="dealer_package", listing_quota=7)
    provider = FakePaymentProvider()
    client = billing_client(integration, provider)

    public_tariffs = client.get("/api/v1/billing/tariffs")
    assert public_tariffs.status_code == 200, public_tariffs.text
    public_tariff = next(row for row in public_tariffs.json() if row["id"] == str(tariff.id))
    assert public_tariff["listing_quota"] == 7

    csrf = login(client, owner.email)
    client_capacity = client.post(
        "/api/v1/billing/orders",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "client-cannot-set-package-capacity"},
        json={"company_id": str(company.id), "tariff_id": str(tariff.id), "listing_quota": 999},
    )
    assert client_capacity.status_code == 422, client_capacity.text

    checkout = client.post(
        "/api/v1/billing/orders",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "package-capacity-snapshot"},
        json={"company_id": str(company.id), "tariff_id": str(tariff.id)},
    )
    assert checkout.status_code == 200, checkout.text
    order_payload = checkout.json()["order"]
    assert order_payload["listing_quota"] == 7
    order_id = order_payload["id"]

    with factory() as db:
        order = db.get(models.BillingOrder, uuid.UUID(order_id))
        with pytest.raises(ValueError, match="snapshot fields are immutable"):
            order.listing_quota = 8
            db.flush()

    with factory() as db:
        tariff_row = db.get(models.BillingTariff, tariff.id)
        tariff_row.listing_quota = 12
        order = db.get(models.BillingOrder, uuid.UUID(order_id))
        result = process_payment_callback(
            db,
            provider=provider,
            raw_body=callback_body(order, event_id="evt-package-capacity-snapshot"),
            signature=None,
        )
        db.commit()
        assert result.order.listing_quota == 7
        promotion = db.scalar(
            select(models.ListingPromotion).where(models.ListingPromotion.order_id == order.id)
        )
        assert promotion.listing_quota == 7
        with pytest.raises(ValueError, match="snapshot fields are immutable"):
            promotion.listing_quota = 8
            db.flush()


def test_effective_company_quota_uses_max_active_package_then_base_after_expiry(integration, monkeypatch):
    factory = integration["SessionLocal"]
    owner = add_user(factory, "billing-capacity-limit-owner")
    company = add_company(factory, owner.id)
    now = datetime.now(timezone.utc)

    with factory() as db:
        db.add(RuntimeSetting(key="company_listing_quota", value=2, revision=1))
        package_rows = []
        for index, capacity in enumerate((5, 7)):
            tariff = models.BillingTariff(
                code=f"dealer-package-quota-{index}-{uuid.uuid4().hex[:8]}",
                service_code="dealer_package",
                name="Synthetic package quota test",
                amount=Decimal("50.00"),
                currency="BYN",
                duration_days=7,
                listing_quota=capacity,
                status="active",
                revision=1,
            )
            db.add(tariff)
            db.flush()
            order = models.BillingOrder(
                user_id=owner.id,
                company_id=company.id,
                listing_id=None,
                tariff_id=tariff.id,
                service_code="dealer_package",
                tariff_code=tariff.code,
                tariff_revision=tariff.revision,
                amount=tariff.amount,
                currency=tariff.currency,
                duration_days=tariff.duration_days,
                listing_quota=capacity,
                provider="test",
                idempotency_key_digest=hashlib.sha256(f"capacity-{index}".encode()).hexdigest(),
                request_digest=hashlib.sha256(f"capacity-request-{index}".encode()).hexdigest(),
                status="paid",
                expires_at=now + timedelta(days=1),
                paid_at=now,
            )
            db.add(order)
            db.flush()
            promotion = models.ListingPromotion(
                order_id=order.id,
                company_id=company.id,
                listing_id=None,
                service_code="dealer_package",
                tariff_code=tariff.code,
                tariff_revision=tariff.revision,
                amount=tariff.amount,
                currency=tariff.currency,
                duration_days=tariff.duration_days,
                listing_quota=capacity,
                status="active",
                starts_at=now - timedelta(minutes=1),
                ends_at=now + timedelta(days=7),
            )
            db.add(promotion)
            package_rows.append(promotion)
        db.flush()

        assert quota_limit(company, db) == 7

        class AfterPackageExpiry:
            @staticmethod
            def now(tz=None):
                return now + timedelta(days=8)

        monkeypatch.setattr("app.services.datetime", AfterPackageExpiry)
        assert quota_limit(company, db) == 2


def test_listing_completion_migration_adds_capacity_and_database_snapshot_guard(integration):
    factory = integration["SessionLocal"]
    migration_path = Path(__file__).resolve().parents[1] / "alembic/versions/0017_listing_completion.py"
    upgrade = runpy.run_path(str(migration_path))["upgrade"]

    with integration["engine"].begin() as connection:
        connection.execute(text("DROP TRIGGER IF EXISTS trg_billing_order_snapshot_immutable ON billing_orders"))
        connection.execute(text("DROP FUNCTION IF EXISTS guard_billing_order_snapshot_update()"))
        for table_name, constraint_name in (
            ("billing_tariffs", "ck_billing_tariff_listing_quota"),
            ("billing_orders", "ck_billing_order_listing_quota"),
            ("listing_promotions", "ck_listing_promotion_listing_quota"),
        ):
            connection.execute(text(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}"))
            connection.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS listing_quota"))
        with Operations.context(MigrationContext.configure(connection)):
            upgrade()
            upgrade()

        for table_name, constraint_name in (
            ("billing_tariffs", "ck_billing_tariff_listing_quota"),
            ("billing_orders", "ck_billing_order_listing_quota"),
            ("listing_promotions", "ck_listing_promotion_listing_quota"),
        ):
            assert "listing_quota" in {column["name"] for column in inspect(connection).get_columns(table_name)}
            assert constraint_name in {
                item.get("name") for item in inspect(connection).get_check_constraints(table_name)
            }
        assert connection.scalar(text(
            "SELECT 1 FROM pg_trigger WHERE tgname = 'trg_billing_order_snapshot_immutable' AND NOT tgisinternal"
        )) == 1

    owner = add_user(factory, "billing-migration-capacity-owner")
    company = add_company(factory, owner.id)
    tariff = add_tariff(factory, service_code="dealer_package", listing_quota=7)
    with factory() as db:
        checkout = create_order_checkout(
            db,
            user=owner,
            target=OrderTarget(company_id=company.id),
            tariff_id=tariff.id,
            idempotency_key="migration-package-capacity",
            provider=FakePaymentProvider(),
        )
        db.commit()
        order_id = checkout.order.id

    with pytest.raises(DBAPIError, match="billing order snapshot fields are immutable"):
        with integration["engine"].begin() as connection:
            connection.execute(
                text("UPDATE billing_orders SET listing_quota = 8 WHERE id = :order_id"),
                {"order_id": order_id},
            )


def test_paid_duplicate_activation_is_serialized_by_target_lock(integration):
    factory = integration["SessionLocal"]
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    with factory() as db:
        orders = [make_paid_order(user, listing, tariff, f"race-{index}") for index in range(2)]
        db.add_all(orders)
        db.commit()
        order_ids = [order.id for order in orders]
    gate = Barrier(2)

    def activate(order_id):
        with factory() as db:
            gate.wait(timeout=5)
            order = db.get(models.BillingOrder, order_id)
            try:
                promotion = activate_paid_order(db, order)
                db.commit()
                return promotion.id, None
            except HTTPException as exc:
                db.rollback()
                return None, exc.detail["code"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(activate, order_ids))
    assert sum(promotion_id is not None for promotion_id, _code in outcomes) == 1
    assert [code for _promotion_id, code in outcomes].count("promotion_overlap") == 1
