from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics_models import ContactClickEvent
from app.models import Listing
from app.analytics_schemas import ContactClickEventIn



# Funnel reporting compares aggregate stages for the same listing within a rolling window.
ATTRIBUTION_WINDOW = timedelta(days=30)

def record_contact_click(db: Session, payload: ContactClickEventIn) -> dict[str, bool]:
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
