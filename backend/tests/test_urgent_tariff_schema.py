import pytest
from pydantic import ValidationError

from app.admin_tariff_schemas import AdminTariffCreateInput
from app.billing_schemas import BillingOrderOut


def create_payload(**overrides):
    return {
        "code": "urgent-1-day",
        "service_code": "urgent",
        "name": "Срочно на день",
        "amount": "1.00",
        "currency": "BYN",
        "duration_days": 1,
        "listing_quota": None,
        "status": "disabled",
        "reason": "Пилотная настройка тарифа",
        "confirmation": "CREATE_TARIFF",
        "current_password": "test-password",
        **overrides,
    }


def test_urgent_tariff_is_owner_configured_without_seeded_price_or_quota():
    tariff = AdminTariffCreateInput.model_validate(create_payload())

    assert tariff.service_code == "urgent"
    assert tariff.amount == 1
    assert tariff.status == "disabled"
    assert tariff.listing_quota is None


def test_urgent_tariff_cannot_be_given_company_listing_quota():
    with pytest.raises(ValidationError, match="Listing quota is only available for dealer packages"):
        AdminTariffCreateInput.model_validate(create_payload(listing_quota=10))


def test_billing_order_contract_accepts_urgent_service_code():
    from datetime import UTC, datetime
    from uuid import uuid4

    order = BillingOrderOut.model_validate({
        "id": uuid4(), "listing_id": uuid4(), "company_id": None,
        "service_code": "urgent", "tariff_code": "urgent-1-day", "tariff_revision": 1,
        "amount": "1.00", "currency": "BYN", "duration_days": 1, "listing_quota": None,
        "provider": "disabled", "provider_reference": None, "status": "pending",
        "expires_at": datetime.now(UTC), "paid_at": None, "created_at": datetime.now(UTC),
    })

    assert order.service_code == "urgent"
