from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analytics_schemas import AnalyticsEventAccepted, ContactClickEventIn, FrontendErrorReportIn
from app.analytics_service import record_contact_click
from app.db import get_db
from app.error_monitoring import capture_safe_error
from app.security import client_ip
from app.services import consume_rate_limit

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _is_dedup_conflict(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint == "uq_contact_click_dedup":
        return True
    # SQLite is useful for local tests, though production uses PostgreSQL.
    message = str(exc.orig).lower()
    return (
        "unique constraint failed: contact_click_events.dedup_id" in message
        or "uq_contact_click_dedup" in message
    )


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
        return {"accepted": True, "recorded": result["recorded"]}
    except IntegrityError as exc:
        db.rollback()
        if _is_dedup_conflict(exc):
            return {"accepted": True, "recorded": False}
        capture_safe_error("analytics", type(exc).__name__)
        return {"accepted": True, "recorded": False}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - analytics must fail open.
        db.rollback()
        capture_safe_error("analytics", type(exc).__name__)
        return {"accepted": True, "recorded": False}


@router.post("/errors", status_code=202, response_model=AnalyticsEventAccepted)
def report_frontend_error(
    payload: FrontendErrorReportIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Forward only a safe error class, release ID, and fixed breadcrumb codes."""
    try:
        consume_rate_limit(db, "analytics-frontend-error-ip", client_ip(request), 30, timedelta(hours=1))
        recorded = capture_safe_error(
            "frontend", payload.error_type, release_id=payload.release_id, breadcrumbs=payload.breadcrumbs
        )
        return {"accepted": True, "recorded": recorded}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - optional monitoring must fail open.
        db.rollback()
        capture_safe_error("analytics", type(exc).__name__)
        return {"accepted": True, "recorded": False}
