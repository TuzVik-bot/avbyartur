from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf
from app.billing_schemas import (
    BillingCallbackOut,
    BillingCheckoutOut,
    BillingOrderCreate,
    BillingOrderListOut,
    BillingOrderOut,
    BillingTariffOut,
)
from app.billing_services import (
    OrderTarget,
    PaymentProvider,
    create_order_checkout,
    get_payment_provider,
    get_user_order,
    list_active_tariffs,
    list_user_orders,
    process_payment_callback,
)
from app.db import get_db
from app.models import User, UserSession
from app.services import fail


router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
MAX_PAYMENT_CALLBACK_BYTES = 64 * 1024


@router.get("/tariffs", response_model=list[BillingTariffOut])
def active_tariffs(db: Annotated[Session, Depends(get_db)]) -> list:
    """Return only explicitly active, owner-provided price rows."""

    return list_active_tariffs(db)


@router.post("/orders", response_model=BillingCheckoutOut)
def create_billing_order(
    payload: BillingOrderCreate,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120, alias="Idempotency-Key")],
) -> dict:
    checkout = create_order_checkout(
        db,
        user=user,
        target=OrderTarget(listing_id=payload.listing_id, company_id=payload.company_id),
        tariff_id=payload.tariff_id,
        idempotency_key=idempotency_key,
        provider=provider,
    )
    db.commit()
    return {"order": checkout.order, "checkout_url": checkout.checkout_url}


@router.get("/orders", response_model=BillingOrderListOut)
def billing_order_history(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    items, total = list_user_orders(db, user.id, page=page, page_size=page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/orders/{order_id}", response_model=BillingOrderOut)
def billing_order_detail(
    order_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BillingOrderOut:
    return get_user_order(db, user_id=user.id, order_id=order_id)


@router.post("/callbacks/{provider_name}", response_model=BillingCallbackOut)
async def payment_callback(
    provider_name: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
    signature: Annotated[str | None, Header(alias="X-Payment-Signature")] = None,
) -> dict:
    if provider.name != provider_name:
        fail(404, "payment_provider_not_found", "Payment provider was not found")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PAYMENT_CALLBACK_BYTES:
            fail(413, "payment_callback_too_large", "Payment callback exceeds the allowed size")

    result = process_payment_callback(
        db,
        provider=provider,
        raw_body=bytes(body),
        signature=signature,
    )
    db.commit()
    return {
        "received": True,
        "duplicate": result.duplicate,
        "order_id": result.order.id,
        "status": result.order.status,
    }
