"""Public price history and opt-in price-drop notification creation."""

from decimal import Decimal
import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Company,
    Favorite,
    Listing,
    ListingPriceEvent,
    NotificationOutbox,
    User,
)
from app.profile_identity_models import UserNotificationPreferences
from app.services import enqueue_job


def is_same_currency_price_drop(
    previous_amount: Decimal | None,
    previous_currency: str | None,
    amount: Decimal | None,
    currency: str | None,
) -> bool:
    """Return true only when the seller lowered the raw amount in one currency."""

    return (
        previous_amount is not None
        and amount is not None
        and previous_currency is not None
        and previous_currency == currency
        and amount < previous_amount
    )


def _price_text(amount: Decimal, currency: str) -> str:
    return f"{amount:.2f} {currency}"


def _listing_url(listing: Listing) -> str:
    segment = listing.slug or str(listing.id)
    return f"/cars/{segment}/{segment}/{listing.id}"


def _enqueue_price_drop_notifications(
    db: Session,
    listing: Listing,
    event: ListingPriceEvent,
) -> None:
    if not is_same_currency_price_drop(
        event.previous_price_amount,
        event.previous_currency,
        event.price_amount,
        event.currency,
    ):
        return

    recipients = db.scalars(
        select(Favorite.user_id)
        .join(User, User.id == Favorite.user_id)
        .outerjoin(
            UserNotificationPreferences,
            UserNotificationPreferences.user_id == Favorite.user_id,
        )
        .where(
            Favorite.listing_id == listing.id,
            Favorite.price_drop_notifications_enabled.is_(True),
            Favorite.user_id != listing.owner_id,
            User.status == "active",
            or_(
                UserNotificationPreferences.user_id.is_(None),
                UserNotificationPreferences.web_enabled.is_(True),
            ),
        )
        .order_by(Favorite.user_id)
    ).all()
    if not recipients:
        return

    title = "Цена снизилась в избранном"
    body = (
        f"{listing.title or 'Объявление'}: цена снизилась с "
        f"{_price_text(event.previous_price_amount, event.previous_currency)} до "
        f"{_price_text(event.price_amount, event.currency)}."
    )
    url = _listing_url(listing)
    for user_id in recipients:
        dedupe_key = f"price-drop:event:{event.id}:user:{user_id}:web"
        outbox_id = db.scalar(
            pg_insert(NotificationOutbox)
            .values(
                id=uuid.uuid4(),
                dedupe_key=dedupe_key,
                user_id=user_id,
                listing_id=listing.id,
                price_event_id=event.id,
                channel="web",
                status="queued",
                payload={
                    "title": title,
                    "body": body,
                    "url": url,
                    "price_event_id": str(event.id),
                    "previous_amount": str(event.previous_price_amount),
                    "previous_currency": event.previous_currency,
                    "amount": str(event.price_amount),
                    "currency": event.currency,
                },
            )
            .on_conflict_do_nothing(constraint="uq_notification_outbox_dedupe")
            .returning(NotificationOutbox.id)
        )
        if outbox_id is not None:
            enqueue_job(
                db,
                "notification.deliver",
                f"notification.deliver:{outbox_id}",
                {"outbox_id": str(outbox_id)},
            )


def record_active_listing_price_state(
    db: Session,
    listing: Listing,
    *,
    baseline_if_missing: bool = False,
) -> ListingPriceEvent | None:
    """Record an active public price state once, then queue eligible discounts."""

    if listing.status != "active":
        return None
    owner = db.get(User, listing.owner_id)
    if owner is None or owner.status != "active":
        return None
    if listing.company_id is not None:
        company = db.get(Company, listing.company_id)
        if company is None or company.status != "approved":
            return None

    existing_revision = db.scalar(
        select(ListingPriceEvent).where(
            ListingPriceEvent.listing_id == listing.id,
            ListingPriceEvent.revision == listing.revision,
        )
    )
    if existing_revision is not None:
        return existing_revision

    latest = db.scalar(
        select(ListingPriceEvent)
        .where(ListingPriceEvent.listing_id == listing.id)
        .order_by(ListingPriceEvent.revision.desc(), ListingPriceEvent.id.desc())
        .limit(1)
    )
    amount = listing.price_amount
    currency = listing.currency if amount is not None else None
    if latest is None and amount is None:
        return None
    if latest is not None and latest.price_amount == amount and latest.currency == currency:
        return None

    if latest is None:
        event_type = "baseline" if baseline_if_missing else "published"
    elif amount is None:
        event_type = "removed"
    elif latest.price_amount is None:
        event_type = "added"
    else:
        event_type = "changed"

    event = ListingPriceEvent(
        listing_id=listing.id,
        revision=listing.revision,
        event_type=event_type,
        price_amount=amount,
        currency=currency,
        previous_price_amount=latest.price_amount if latest is not None else None,
        previous_currency=latest.currency if latest is not None else None,
    )
    db.add(event)
    db.flush()
    _enqueue_price_drop_notifications(db, listing, event)
    return event
