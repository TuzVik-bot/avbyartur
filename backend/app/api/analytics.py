from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics_schemas import AnalyticsEventAccepted, ContactClickEventIn
from app.analytics_service import record_contact_click
from app.db import get_db
from app.error_monitoring import capture_safe_error
from app.security import client_ip
from app.services import consume_rate_limit

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.post("/events", status_code=202, response_model=AnalyticsEventAccepted)
def contact_click(
    payload: ContactClickEventIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    analytics_consent: Annotated[str | None, Header(alias="X-Analytics-Consent")] = None,
) -> dict:
    """Record only a consented click; views and successful reveals use existing counters."""
    if analytics_consent != "granted":
        return {"accepted": True, "recorded": False}
    try:
        consume_rate_limit(db, "analytics-contact-click-ip", client_ip(request), 120, timedelta(hours=1))
        result = record_contact_click(db, payload)
        return {"accepted": True, "recorded": not result["duplicate"]}
    except IntegrityError:
        # Concurrent retries race the unique dedup constraint. The first write wins.
        db.rollback()
        return {"accepted": True, "recorded": False}
    except Exception as exc:  # noqa: BLE001 - analytics must fail open.
        db.rollback()
        capture_safe_error("analytics", type(exc).__name__)
        return {"accepted": True, "recorded": False}
