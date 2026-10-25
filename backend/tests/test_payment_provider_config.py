import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.billing_services import (
    ConfiguredPaymentProvider,
    DisabledPaymentProvider,
    get_payment_provider,
)
from app.main import app
from app.models import BillingOrder


def make_order() -> BillingOrder:
    return BillingOrder(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        tariff_id=uuid.uuid4(),
        listing_id=uuid.uuid4(),
        company_id=None,
        service_code="highlight",
        tariff_code="highlight-7",
        tariff_revision=2,
        amount=Decimal("12.50"),
        currency="BYN",
        duration_days=7,
        listing_quota=None,
        provider="highlight",
        provider_reference=None,
        idempotency_key_digest="0" * 64,
        request_digest="1" * 64,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def test_configured_provider_builds_https_checkout_from_template():
    provider = ConfiguredPaymentProvider(
        name="bepaid",
        secret=b"callback-secret",
        checkout_url_template="https://checkout.example.test/pay?order={order_id}&amount={amount}&currency={currency}&desc={description}",
    )
    order = make_order()
    result = provider.create_checkout(order, idempotency_key="key-1")
    assert result.provider == "bepaid"
    assert result.provider_reference == str(order.id)
    assert str(order.id) in result.checkout_url
    assert "amount=12.50" in result.checkout_url
    assert "currency=BYN" in result.checkout_url
    assert result.checkout_url.startswith("https://checkout.example.test/pay?")


def test_configured_provider_requires_order_id_placeholder():
    with pytest.raises(ValueError, match="order_id"):
        ConfiguredPaymentProvider(
            name="bepaid",
            secret=b"callback-secret",
            checkout_url_template="https://checkout.example.test/pay?amount={amount}",
        )


def test_factory_defaults_to_disabled_without_settings(monkeypatch):
    from app.config import get_settings

    for key in (
        "PAYMENT_PROVIDER_NAME",
        "PAYMENT_CALLBACK_SECRET",
        "PAYMENT_CHECKOUT_URL_TEMPLATE",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    try:
        provider = get_payment_provider()
        assert isinstance(provider, DisabledPaymentProvider)
        assert provider.is_configured is False
    finally:
        get_settings.cache_clear()


def test_factory_enables_provider_with_full_settings(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("PAYMENT_PROVIDER_NAME", "bepaid")
    monkeypatch.setenv("PAYMENT_CALLBACK_SECRET", "callback-secret")
    monkeypatch.setenv(
        "PAYMENT_CHECKOUT_URL_TEMPLATE",
        "https://checkout.example.test/pay?order={order_id}",
    )
    get_settings.cache_clear()
    try:
        provider = get_payment_provider()
        assert isinstance(provider, ConfiguredPaymentProvider)
        assert provider.is_configured is True
        assert provider.name == "bepaid"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_factory_falls_back_to_disabled_on_bad_template(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("PAYMENT_PROVIDER_NAME", "bepaid")
    monkeypatch.setenv("PAYMENT_CALLBACK_SECRET", "callback-secret")
    monkeypatch.setenv(
        "PAYMENT_CHECKOUT_URL_TEMPLATE",
        "https://checkout.example.test/pay?amount={amount}",
    )
    get_settings.cache_clear()
    try:
        provider = get_payment_provider()
        assert isinstance(provider, DisabledPaymentProvider)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_capabilities_endpoint_reflects_provider(integration):
    from app.billing_services import get_payment_provider as factory

    client: TestClient = integration["client"]
    app.dependency_overrides[factory] = lambda: ConfiguredPaymentProvider(
        name="bepaid",
        secret=b"callback-secret",
        checkout_url_template="https://checkout.example.test/pay?order={order_id}",
    )
    try:
        enabled = client.get("/api/v1/billing/capabilities")
        assert enabled.status_code == 200, enabled.text
        assert enabled.json() == {"orders_enabled": True, "provider": "bepaid"}
    finally:
        app.dependency_overrides.pop(factory, None)

    disabled = client.get("/api/v1/billing/capabilities")
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["orders_enabled"] is False
    assert disabled.json()["provider"] is None
