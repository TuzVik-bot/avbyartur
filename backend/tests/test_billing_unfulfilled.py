"""A provider-confirmed payment is always recorded, even when it cannot be fulfilled."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Response
from sqlalchemy import select
from test_billing import (
    FakePaymentProvider,
    add_company,
    add_listing,
    add_tariff,
    add_user,
    billing_client,
    callback_body,
)

from app import models
from app.api import billing as billing_api
from app.api import monitoring as monitoring_api
from app.billing_services import count_paid_unfulfilled_orders


def _pending_order(
    factory,
    *,
    user,
    tariff,
    listing=None,
    company=None,
    expires_in=timedelta(minutes=30),
):
    key = uuid.uuid4().hex
    order = models.BillingOrder(
        user_id=user.id,
        listing_id=listing.id if listing else None,
        company_id=company.id if company else None,
        tariff_id=tariff.id,
        service_code=tariff.service_code,
        tariff_code=tariff.code,
        tariff_revision=tariff.revision,
        amount=tariff.amount,
        currency=tariff.currency,
        duration_days=tariff.duration_days,
        listing_quota=tariff.listing_quota,
        provider="test",
        provider_reference=f"pay-{key}",
        idempotency_key_digest=hashlib.sha256(key.encode()).hexdigest(),
        request_digest=hashlib.sha256((key + "-request").encode()).hexdigest(),
        status="pending",
        expires_at=datetime.now(timezone.utc) + expires_in,
    )
    with factory() as db:
        db.add(order)
        db.flush()
        db.add(
            models.PaymentAttempt(
                order_id=order.id,
                attempt_number=1,
                provider="test",
                provider_reference=order.provider_reference,
                amount=order.amount,
                currency=order.currency,
                status="pending",
            )
        )
        db.commit()
        db.refresh(order)
        db.expunge(order)
    return order


def _set_status(factory, model, row_id, status: str) -> None:
    with factory() as db:
        db.get(model, row_id).status = status
        db.commit()


def _expired_case(factory):
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    return _pending_order(
        factory,
        user=user,
        tariff=tariff,
        listing=listing,
        expires_in=timedelta(minutes=-5),
    )


def _inactive_listing_case(factory):
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    order = _pending_order(
        factory, user=user, tariff=add_tariff(factory), listing=listing
    )
    _set_status(factory, models.Listing, listing.id, "paused")
    return order


def _unapproved_company_case(factory):
    owner = add_user(factory, "billing-unfulfilled-dealer")
    company = add_company(factory, owner.id)
    tariff = add_tariff(
        factory, service_code="dealer_package", amount="50.00", listing_quota=7
    )
    order = _pending_order(factory, user=owner, tariff=tariff, company=company)
    _set_status(factory, models.Company, company.id, "blocked")
    return order


def _overlap_case(factory):
    user = add_user(factory)
    listing = add_listing(factory, user.id)
    tariff = add_tariff(factory)
    order = _pending_order(factory, user=user, tariff=tariff, listing=listing)
    now = datetime.now(timezone.utc)
    other = _pending_order(factory, user=user, tariff=tariff, listing=listing)
    with factory() as db:
        db.get(models.BillingOrder, other.id).status = "paid"
        db.add(
            models.ListingPromotion(
                order_id=other.id,
                listing_id=listing.id,
                company_id=None,
                service_code=tariff.service_code,
                tariff_code=tariff.code,
                tariff_revision=tariff.revision,
                amount=tariff.amount,
                currency=tariff.currency,
                duration_days=tariff.duration_days,
                listing_quota=None,
                status="active",
                starts_at=now,
                ends_at=now + timedelta(days=7),
            )
        )
        db.commit()
    return order


@pytest.mark.parametrize(
    ("build_case", "reason"),
    [
        (_expired_case, "payment_order_expired"),
        (_inactive_listing_case, "listing_not_promotable"),
        (_unapproved_company_case, "company_not_available"),
        (_overlap_case, "promotion_overlap"),
    ],
)
def test_unfulfillable_success_callback_is_recorded_as_paid_unfulfilled(
    integration, monkeypatch, build_case, reason
):
    factory = integration["SessionLocal"]
    logged = []
    monkeypatch.setattr(
        billing_api,
        "log_event",
        lambda _logger, level, event, **fields: logged.append((level, event, fields)),
    )
    order = build_case(factory)
    client = billing_client(integration, FakePaymentProvider())
    event_id = f"evt-unfulfilled-{uuid.uuid4().hex[:8]}"

    response = client.post(
        "/api/v1/billing/callbacks/test",
        content=callback_body(order, event_id=event_id),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid"
    with factory() as db:
        stored = db.get(models.BillingOrder, order.id)
        assert stored.status == "paid"
        assert stored.paid_at is not None
        attempt = db.scalar(
            select(models.PaymentAttempt).where(
                models.PaymentAttempt.order_id == order.id
            )
        )
        assert attempt.status == "succeeded"
        event = db.scalar(
            select(models.PaymentCallbackEvent).where(
                models.PaymentCallbackEvent.provider_event_id == event_id
            )
        )
        assert event is not None and event.order_id == order.id
        assert (
            db.scalar(
                select(models.ListingPromotion).where(
                    models.ListingPromotion.order_id == order.id
                )
            )
            is None
        )
        audits = db.scalars(
            select(models.AuditEvent).where(
                models.AuditEvent.entity_id == order.id,
                models.AuditEvent.action == "paid_unfulfilled",
            )
        ).all()
        assert [audit.details["reason"] for audit in audits] == [reason]
        assert count_paid_unfulfilled_orders(db) == 1
        snapshot = monitoring_api.monitoring_snapshot(
            admin=None, db=db, response=Response()
        )
        assert {
            "code": "payment_paid_unfulfilled",
            "severity": "high",
            "count": 1,
        } in snapshot["alerts"]
    assert [
        (event, fields["order_id"], fields["reason"])
        for _level, event, fields in logged
    ] == [
        ("payment_paid_unfulfilled", str(order.id), reason),
    ]

    replay = client.post(
        "/api/v1/billing/callbacks/test",
        content=callback_body(order, event_id=event_id),
    )

    assert replay.status_code == 200, replay.text
    assert replay.json()["duplicate"] is True
    assert len(logged) == 1
