from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics_models import ContactClickEvent
from app.models import Listing
from app.analytics_schemas import ContactClickEventIn

def record_contact_click(db: Session, payload: ContactClickEventIn) -> dict[str, bool]:
    """Record one opted-in contact action for independent period aggregates.

    Events contain no visitor or session identifier, so analytics does not link
    a view, reveal, and contact action to the same person or claim a completed
    call or message.
    """
    listing = db.scalar(select(Listing).where(Listing.id == payload.listing_id, Listing.status == "active"))
    if listing is None or listing.status != "active":
        return {"accepted": True, "recorded": False, "duplicate": False}
    existing = db.scalar(select(ContactClickEvent.id).where(ContactClickEvent.dedup_id == str(payload.dedup_id)))
    if existing is not None:
        return {"accepted": True, "recorded": False, "duplicate": True}
    db.add(ContactClickEvent(
        listing_id=listing.id,
        channel=payload.channel,
        dedup_id=str(payload.dedup_id),
        occurred_at=payload.occurred_at,
    ))
    db.commit()
    return {"accepted": True, "recorded": True, "duplicate": False}
