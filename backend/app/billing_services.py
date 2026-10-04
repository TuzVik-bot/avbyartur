"""Provider-neutral commerce contracts with a deliberately closed default."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.dealer_services import MANAGER_ROLES, resolve_company_for_user
from app.models import (
    AuditEvent,
    BillingOrder,
    BillingTariff,
    Company,
    Listing,
    ListingPromotion,
    PaymentAttempt,
    PaymentCallbackEvent,
    User,
)
from app.services import fail, lock_owner, require_owned_listing


ORDER_TTL = timedelta(minutes=30)
SUPPORTED_SERVICES = frozenset({"bump", "highlight", "top", "dealer_package"})
CALLBACK_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


class PaymentProviderUnavailable(Exception):
    """The adapter has no working checkout or callback transport."""


class InvalidPaymentSignature(Exception):
    """The raw callback body did not authenticate for this provider."""


class InvalidPaymentCallback(Exception):
    """The callback body did not match the provider-neutral event contract."""


@dataclass(frozen=True)
class OrderTarget:
    listing_id: UUID | None = None
    company_id: UUID | None = None

    def __post_init__(self) -> None:
        if (self.listing_id is None) == (self.company_id is None):
            raise ValueError("Exactly one billing target is required")


@dataclass(frozen=True)
class CheckoutResult:
    provider: str
    provider_reference: str
    checkout_url: str


@dataclass(frozen=True)
class CallbackPayload:
    provider: str
    provider_event_id: str
    provider_reference: str
    status: str
    amount: Decimal
    currency: str
    event_type: str = "payment.updated"


@dataclass(frozen=True)
class OrderCheckout:
    order: BillingOrder
    attempt: PaymentAttempt | None
    checkout_url: str | None


@dataclass(frozen=True)
class CallbackResult:
    order: BillingOrder
    event: PaymentCallbackEvent
    duplicate: bool


class PaymentProvider(Protocol):
    name: str
    is_configured: bool

    def create_checkout(self, order: BillingOrder, *, idempotency_key: str) -> CheckoutResult: ...

    def verify_callback(self, raw_body: bytes, signature: str | None) -> CallbackPayload: ...


class DisabledPaymentProvider:
    """Default adapter: payment capability is explicitly unavailable."""

    name = "disabled"
    is_configured = False

    def create_checkout(self, order: BillingOrder, *, idempotency_key: str) -> CheckoutResult:
        raise PaymentProviderUnavailable("Payment provider is not configured")

    def verify_callback(self, raw_body: bytes, signature: str | None) -> CallbackPayload:
        raise PaymentProviderUnavailable("Payment provider is not configured")


class HmacPaymentProvider:
    """Small callback verifier for an explicitly injected provider adapter.

    It intentionally has no checkout implementation and is not selected by the
    application default. A real provider must define its own payload contract.
    """

    is_configured = True

    def __init__(self, *, name: str, secret: bytes) -> None:
        if not name or len(name) > 40 or not secret:
            raise ValueError("A provider name and non-empty callback secret are required")
        self.name = name
        self._secret = bytes(secret)

    def create_checkout(self, order: BillingOrder, *, idempotency_key: str) -> CheckoutResult:
        raise PaymentProviderUnavailable("This callback-only provider cannot create checkout sessions")

    def verify_callback(self, raw_body: bytes, signature: str | None) -> CallbackPayload:
        provided = (signature or "").strip()
        if provided.startswith("sha256="):
            provided = provided[7:]
        expected = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()
        if not provided or not hmac.compare_digest(expected, provided.lower()):
            raise InvalidPaymentSignature
        try:
            body = json.loads(raw_body)
            if not isinstance(body, dict):
                raise InvalidPaymentCallback
            event_id = body["event_id"]
            reference = body["provider_reference"]
            status = body["status"]
            amount = Decimal(str(body["amount"]))
            currency = body["currency"]
            event_type = body.get("event_type", "payment.updated")
        except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError) as exc:
            raise InvalidPaymentCallback from exc
        if (
            not isinstance(event_id, str)
            or not 1 <= len(event_id) <= 180
            or not isinstance(reference, str)
            or not 1 <= len(reference) <= 180
            or not isinstance(status, str)
            or status not in CALLBACK_STATUSES
            or not amount.is_finite()
            or amount <= 0
            or currency not in {"BYN", "USD"}
            or not isinstance(event_type, str)
            or not 1 <= len(event_type) <= 80
        ):
            raise InvalidPaymentCallback
        return CallbackPayload(
            provider=self.name,
            provider_event_id=event_id,
            provider_reference=reference,
            status=status,
            amount=amount,
            currency=currency,
            event_type=event_type,
        )


def get_payment_provider() -> PaymentProvider:
    """Dependency seam; stays closed until an owner-selected adapter is wired."""

    return DisabledPaymentProvider()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _request_digest(target: OrderTarget, tariff_id: UUID) -> str:
    target_value = str(target.listing_id or target.company_id)
    payload = f"billing-order:v1:{target_value}:{tariff_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def _provider_ready(provider: PaymentProvider) -> None:
    if not provider.is_configured:
        fail(503, "commerce_provider_unconfigured", "Payment provider is not configured")
    if not provider.name or len(provider.name) > 40:
        fail(503, "commerce_provider_unconfigured", "Payment provider is not configured")


def _authorize_target(
    db: Session,
    *,
    user: User,
    target: OrderTarget,
    service_code: str,
    lock: bool,
) -> tuple[Listing | None, Company | None]:
    if service_code == "dealer_package":
        if target.company_id is None or target.listing_id is not None:
            fail(422, "invalid_billing_target", "A dealer package requires a company target")
        company, _role = resolve_company_for_user(
            db,
            user,
            allowed_roles=MANAGER_ROLES,
            require_approved=True,
            lock=lock,
        )
        if company.id != target.company_id:
            fail(404, "not_found", "Company not found")
        return None, company

    if target.listing_id is None or target.company_id is not None:
        fail(422, "invalid_billing_target", "This service requires a listing target")
    listing = require_owned_listing(db, target.listing_id, user, lock=lock)
    if listing.status != "active":
        fail(409, "listing_not_promotable", "Only an active listing can receive a paid service")
    return listing, None


def _target_conditions(target: OrderTarget):
    if target.listing_id is not None:
        return ListingPromotion.listing_id == target.listing_id
    return ListingPromotion.company_id == target.company_id


def _order_target_conditions(target: OrderTarget):
    if target.listing_id is not None:
        return BillingOrder.listing_id == target.listing_id
    return BillingOrder.company_id == target.company_id


def _assert_target_available(
    db: Session,
    *,
    target: OrderTarget,
    service_code: str,
    now: datetime,
    ignore_order_id: UUID | None = None,
) -> None:
    active = db.scalar(
        select(ListingPromotion.id).where(
            _target_conditions(target),
            ListingPromotion.service_code == service_code,
            ListingPromotion.status == "active",
            ListingPromotion.ends_at > now,
        ).limit(1)
    )
    pending_query = select(BillingOrder.id).where(
            _order_target_conditions(target),
            BillingOrder.service_code == service_code,
            BillingOrder.status == "pending",
            BillingOrder.expires_at > now,
        )
    if ignore_order_id is not None:
        pending_query = pending_query.where(BillingOrder.id != ignore_order_id)
    pending = db.scalar(pending_query.limit(1))
    if active is not None or pending is not None:
        fail(409, "promotion_overlap", "This service is already active or has a pending checkout")


def _checkout_url_is_safe(value: str) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(ord(char) < 32 for char in value):
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def create_order_checkout(
    db: Session,
    *,
    user: User,
    target: OrderTarget,
    tariff_id: UUID,
    idempotency_key: str,
    provider: PaymentProvider,
) -> OrderCheckout:
    """Reserve the target/service and snapshot a tariff behind an enabled provider."""

    _provider_ready(provider)
    key = idempotency_key.strip()
    if not key or len(key) > 120:
        fail(422, "invalid_idempotency_key", "Idempotency-Key must contain 1 to 120 characters")

    # Locking the active account serializes duplicate checkouts even when the
    # same key is accidentally submitted with different target IDs.
    actor = lock_owner(db, user.id)
    existing = db.scalar(
        select(BillingOrder).where(
            BillingOrder.user_id == actor.id,
            BillingOrder.idempotency_key_digest == hashlib.sha256(key.encode()).hexdigest(),
        ).with_for_update()
    )
    request_digest = _request_digest(target, tariff_id)
    if existing is not None:
        if existing.request_digest != request_digest:
            fail(409, "idempotency_key_reused", "This Idempotency-Key was used for a different order")
        now = _now()
        if existing.status == "pending" and existing.expires_at <= now:
            existing.status = "expired"
            db.flush()
        attempt = db.scalar(
            select(PaymentAttempt)
            .where(PaymentAttempt.order_id == existing.id)
            .order_by(PaymentAttempt.attempt_number.desc())
        )
        return OrderCheckout(
            order=existing,
            attempt=attempt,
            checkout_url=attempt.checkout_url if existing.status == "pending" and attempt else None,
        )

    tariff = db.scalar(select(BillingTariff).where(BillingTariff.id == tariff_id).with_for_update(read=True))
    if tariff is None or tariff.status != "active":
        fail(404, "billing_tariff_unavailable", "This tariff is not available")
    if tariff.service_code not in SUPPORTED_SERVICES:
        fail(409, "billing_tariff_unavailable", "This tariff is not available")
    if tariff.service_code == "dealer_package":
        if type(tariff.listing_quota) is not int or not 1 <= tariff.listing_quota <= 10000:
            fail(409, "billing_tariff_capacity_unavailable", "This dealer package has no valid listing capacity")
    elif tariff.listing_quota is not None:
        fail(409, "billing_tariff_capacity_unavailable", "Listing capacity is only available for dealer packages")
    listing, company = _authorize_target(
        db,
        user=actor,
        target=target,
        service_code=tariff.service_code,
        lock=True,
    )
    if tariff.service_code == "dealer_package" and company is None:
        fail(422, "invalid_billing_target", "A dealer package requires a company target")
    if tariff.service_code != "dealer_package" and listing is None:
        fail(422, "invalid_billing_target", "This service requires a listing target")

    now = _now()
    _assert_target_available(db, target=target, service_code=tariff.service_code, now=now)
    order = BillingOrder(
        user_id=actor.id,
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
        provider=provider.name,
        idempotency_key_digest=hashlib.sha256(key.encode()).hexdigest(),
        request_digest=request_digest,
        status="pending",
        expires_at=now + ORDER_TTL,
    )
    db.add(order)
    db.flush()
    attempt = PaymentAttempt(
        order_id=order.id,
        attempt_number=1,
        provider=provider.name,
        amount=order.amount,
        currency=order.currency,
        status="pending",
    )
    db.add(attempt)
    db.flush()
    try:
        checkout = provider.create_checkout(order, idempotency_key=f"billing-order:{order.id}")
    except PaymentProviderUnavailable:
        db.rollback()
        fail(503, "commerce_provider_unconfigured", "Payment provider is not configured")
    except Exception:
        db.rollback()
        fail(503, "payment_provider_unavailable", "Payment provider could not create checkout")
    if (
        checkout.provider != provider.name
        or not isinstance(checkout.provider_reference, str)
        or not 1 <= len(checkout.provider_reference) <= 180
        or not _checkout_url_is_safe(checkout.checkout_url)
    ):
        db.rollback()
        fail(503, "payment_provider_invalid_response", "Payment provider returned an invalid checkout response")

    order.provider_reference = checkout.provider_reference
    attempt.provider_reference = checkout.provider_reference
    attempt.checkout_url = checkout.checkout_url
    db.add(AuditEvent(
        actor_id=actor.id,
        entity_type="billing_order",
        entity_id=order.id,
        action="created",
        details={
            "service_code": order.service_code,
            "amount": str(order.amount),
            "currency": order.currency,
            "duration_days": order.duration_days,
        },
    ))
    db.flush()
    return OrderCheckout(order=order, attempt=attempt, checkout_url=checkout.checkout_url)


def activate_paid_order(db: Session, order: BillingOrder) -> ListingPromotion:
    """Apply one paid order under a target lock and reject same-service overlap."""

    if order.status != "paid":
        fail(409, "order_not_paid", "Only a paid order can activate a service")
    if order.service_code == "dealer_package":
        company = db.scalar(select(Company).where(Company.id == order.company_id).with_for_update())
        if company is None or company.status != "approved":
            fail(409, "company_not_available", "The company is no longer available for this service")
        target = OrderTarget(company_id=company.id)
    else:
        listing = db.scalar(select(Listing).where(Listing.id == order.listing_id).with_for_update())
        if listing is None or listing.status != "active":
            fail(409, "listing_not_promotable", "The listing is no longer available for this service")
        target = OrderTarget(listing_id=listing.id)

    existing = db.scalar(
        select(ListingPromotion).where(ListingPromotion.order_id == order.id).with_for_update()
    )
    if existing is not None:
        return existing
    now = _now()
    _assert_target_available(
        db,
        target=target,
        service_code=order.service_code,
        now=now,
        ignore_order_id=order.id,
    )
    promotion = ListingPromotion(
        order_id=order.id,
        listing_id=order.listing_id,
        company_id=order.company_id,
        service_code=order.service_code,
        tariff_code=order.tariff_code,
        tariff_revision=order.tariff_revision,
        amount=order.amount,
        currency=order.currency,
        duration_days=order.duration_days,
        listing_quota=order.listing_quota,
        status="active",
        starts_at=now,
        ends_at=now + timedelta(days=order.duration_days),
    )
    db.add(promotion)
    db.flush()
    return promotion


def process_payment_callback(
    db: Session,
    *,
    provider: PaymentProvider,
    raw_body: bytes,
    signature: str | None,
) -> CallbackResult:
    """Authenticate, deduplicate, reconcile, and activate a provider event atomically."""

    _provider_ready(provider)
    try:
        payload = provider.verify_callback(raw_body, signature)
    except InvalidPaymentSignature:
        fail(401, "invalid_payment_signature", "Payment callback signature is invalid")
    except PaymentProviderUnavailable:
        fail(503, "commerce_provider_unconfigured", "Payment provider is not configured")
    except (InvalidPaymentCallback, ValueError, TypeError, KeyError, InvalidOperation, json.JSONDecodeError):
        fail(422, "invalid_payment_callback", "Payment callback payload is invalid")

    if payload.provider != provider.name:
        fail(401, "invalid_payment_signature", "Payment callback provider does not match")
    if (
        not payload.provider_event_id
        or len(payload.provider_event_id) > 180
        or not payload.provider_reference
        or len(payload.provider_reference) > 180
        or payload.status not in CALLBACK_STATUSES
        or not payload.amount.is_finite()
        or payload.amount <= 0
        or payload.currency not in {"BYN", "USD"}
        or not payload.event_type
        or len(payload.event_type) > 80
    ):
        fail(422, "invalid_payment_callback", "Payment callback payload is invalid")

    digest = hashlib.sha256(raw_body).hexdigest()
    event_lock_key = int.from_bytes(
        hashlib.sha256(f"{provider.name}:{payload.provider_event_id}".encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )
    # There is no row to lock before the first delivery. A transaction-scoped
    # PostgreSQL advisory lock closes that insert race for concurrent replays.
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": event_lock_key})
    seen = db.scalar(
        select(PaymentCallbackEvent).where(
            PaymentCallbackEvent.provider == provider.name,
            PaymentCallbackEvent.provider_event_id == payload.provider_event_id,
        ).with_for_update()
    )
    if seen is not None:
        if not hmac.compare_digest(seen.payload_sha256, digest):
            fail(409, "provider_event_replay_conflict", "A provider event ID was reused with different contents")
        order = db.get(BillingOrder, seen.order_id)
        if order is None:
            fail(409, "payment_order_unavailable", "The payment order is no longer available")
        return CallbackResult(order=order, event=seen, duplicate=True)

    attempt = db.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.provider == provider.name,
            PaymentAttempt.provider_reference == payload.provider_reference,
        ).with_for_update()
    )
    if attempt is None:
        fail(404, "payment_reference_not_found", "Payment reference was not found")
    order = db.scalar(select(BillingOrder).where(BillingOrder.id == attempt.order_id).with_for_update())
    if order is None:
        fail(404, "payment_order_not_found", "Payment order was not found")
    if payload.amount != attempt.amount or payload.amount != order.amount:
        fail(409, "payment_amount_mismatch", "Payment amount does not match the order")
    if payload.currency != attempt.currency or payload.currency != order.currency:
        fail(409, "payment_currency_mismatch", "Payment currency does not match the order")

    now = _now()
    outcome = "applied"
    if payload.status == "succeeded":
        if order.status == "pending" and order.expires_at <= now:
            fail(409, "payment_order_expired", "Payment order has expired")
        # A late success is authoritative even if an earlier failure callback
        # arrived first. A later failure cannot reverse a paid order.
        order.status = "paid"
        order.paid_at = order.paid_at or now
        attempt.status = "succeeded"
        activate_paid_order(db, order)
    elif order.status == "paid":
        outcome = "ignored"
    elif order.status not in {"pending", "failed", "cancelled", "expired"}:
        outcome = "ignored"
    elif order.status == "pending":
        if payload.status == "failed":
            order.status = "failed"
            attempt.status = "failed"
        else:
            order.status = "cancelled"
            attempt.status = "cancelled"
    else:
        outcome = "ignored"

    event = PaymentCallbackEvent(
        provider=provider.name,
        provider_event_id=payload.provider_event_id,
        order_id=order.id,
        provider_reference=payload.provider_reference,
        event_type=payload.event_type,
        payment_status=payload.status,
        amount=payload.amount,
        currency=payload.currency,
        payload_sha256=digest,
        outcome=outcome,
    )
    db.add(event)
    db.flush()
    return CallbackResult(order=order, event=event, duplicate=False)


def list_active_tariffs(db: Session) -> list[BillingTariff]:
    return db.scalars(
        select(BillingTariff)
        .where(BillingTariff.status == "active")
        .order_by(BillingTariff.service_code, BillingTariff.amount, BillingTariff.code)
        .limit(1000)
    ).all()


def list_user_orders(db: Session, user_id: UUID, *, page: int, page_size: int) -> tuple[list[BillingOrder], int]:
    base = select(BillingOrder).where(BillingOrder.user_id == user_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = db.scalars(
        base.order_by(BillingOrder.created_at.desc(), BillingOrder.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total


def get_user_order(db: Session, *, user_id: UUID, order_id: UUID) -> BillingOrder:
    order = db.scalar(select(BillingOrder).where(BillingOrder.id == order_id, BillingOrder.user_id == user_id))
    if order is None:
        fail(404, "not_found", "Billing order not found")
    return order
