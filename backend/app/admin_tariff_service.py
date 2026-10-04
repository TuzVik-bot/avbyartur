"""Audited owner control for explicit, versioned billing tariffs."""

import hashlib
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.admin_tariff_schemas import (
    AdminTariffCreateInput,
    AdminTariffDeleteInput,
    AdminTariffUpdateInput,
)
from app.models import AuditEvent, BillingOrder, BillingTariff, User
from app.security import verify_password
from app.services import consume_rate_limit, fail


def _amount_text(value: Decimal) -> str:
    return format(value, ".2f")


def _snapshot(tariff: BillingTariff) -> dict:
    return {
        "code": tariff.code,
        "service_code": tariff.service_code,
        "name": tariff.name,
        "amount": _amount_text(tariff.amount),
        "currency": tariff.currency,
        "duration_days": tariff.duration_days,
        "listing_quota": tariff.listing_quota,
        "status": tariff.status,
    }


def _confirm_active_admin(db: Session, admin: User, current_password: str) -> User:
    # consume_rate_limit commits. Acquire the write lock only after that commit,
    # so it cannot release a transaction lock before the tariff mutation.
    consume_rate_limit(db, "admin-tariff-reauth", str(admin.id), 10, timedelta(minutes=15))
    actor = db.scalar(
        select(User)
        .where(User.id == admin.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or actor.role != "admin" or actor.status != "active":
        fail(403, "forbidden", "An active administrator is required")
    if not verify_password(current_password, actor.password_hash):
        fail(401, "reauthentication_failed", "Подтвердите пароль администратора")
    return actor


def _lock_key(resource: str) -> int:
    digest = hashlib.sha256(f"avtorinok-billing-tariff:{resource}".encode()).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def list_tariffs(db: Session, *, page: int = 1, page_size: int = 25) -> dict:
    query = select(BillingTariff)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(BillingTariff.service_code, BillingTariff.code, BillingTariff.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def create_tariff(db: Session, admin: User, payload: AdminTariffCreateInput) -> BillingTariff:
    actor = _confirm_active_admin(db, admin, payload.current_password.get_secret_value())
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_key(f"code:{payload.code}")})
    existing = db.scalar(select(BillingTariff.id).where(BillingTariff.code == payload.code))
    if existing is not None:
        fail(409, "tariff_code_conflict", "Код тарифа уже используется")

    row = BillingTariff(
        code=payload.code,
        service_code=payload.service_code,
        name=payload.name,
        amount=payload.amount,
        currency=payload.currency,
        duration_days=payload.duration_days,
        listing_quota=payload.listing_quota,
        status=payload.status,
        revision=1,
    )
    db.add(row)
    db.flush()
    db.add(AuditEvent(
        actor_id=actor.id,
        entity_type="billing_tariff",
        entity_id=row.id,
        action="billing_tariff_created",
        details={"reason": payload.reason, "revision": row.revision, "after": _snapshot(row)},
    ))
    db.commit()
    db.refresh(row)
    return row


def update_tariff(db: Session, admin: User, tariff_id: UUID, payload: AdminTariffUpdateInput) -> tuple[BillingTariff, bool]:
    actor = _confirm_active_admin(db, admin, payload.current_password.get_secret_value())
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_key(f"id:{tariff_id}")})
    row = db.scalar(
        select(BillingTariff)
        .where(BillingTariff.id == tariff_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        fail(404, "not_found", "Тариф не найден")
    if row.revision != payload.expected_revision:
        fail(409, "revision_conflict", "Тариф изменён; обновите список")
    if row.service_code == "dealer_package" and payload.status == "active" and payload.listing_quota is None:
        fail(422, "invalid_tariff", "Для активного пакета дилера укажите лимит объявлений")
    if row.service_code != "dealer_package" and payload.listing_quota is not None:
        fail(422, "invalid_tariff", "Лимит объявлений допустим только для пакета дилера")

    before = _snapshot(row)
    next_values = {
        "name": payload.name,
        "amount": payload.amount,
        "currency": payload.currency,
        "duration_days": payload.duration_days,
        "listing_quota": payload.listing_quota,
        "status": payload.status,
    }
    changed = any(getattr(row, key) != value for key, value in next_values.items())
    if not changed:
        db.commit()
        return row, False

    for key, value in next_values.items():
        setattr(row, key, value)
    row.revision += 1
    db.flush()
    db.add(AuditEvent(
        actor_id=actor.id,
        entity_type="billing_tariff",
        entity_id=row.id,
        action="billing_tariff_updated",
        details={"reason": payload.reason, "revision": row.revision, "before": before, "after": _snapshot(row)},
    ))
    db.commit()
    db.refresh(row)
    return row, True


def delete_tariff(db: Session, admin: User, tariff_id: UUID, payload: AdminTariffDeleteInput) -> None:
    actor = _confirm_active_admin(db, admin, payload.current_password.get_secret_value())
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_key(f"id:{tariff_id}")})
    row = db.scalar(
        select(BillingTariff)
        .where(BillingTariff.id == tariff_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        fail(404, "not_found", "Тариф не найден")
    if row.revision != payload.expected_revision:
        fail(409, "revision_conflict", "Тариф изменён; обновите список")
    referenced = db.scalar(select(BillingOrder.id).where(BillingOrder.tariff_id == row.id).limit(1))
    if referenced is not None:
        fail(409, "tariff_referenced", "Тариф связан с историей заказов и не может быть удалён")

    snapshot = _snapshot(row)
    db.add(AuditEvent(
        actor_id=actor.id,
        entity_type="billing_tariff",
        entity_id=row.id,
        action="billing_tariff_deleted",
        details={"reason": payload.reason, "revision": row.revision, "before": snapshot},
    ))
    db.delete(row)
    db.commit()
