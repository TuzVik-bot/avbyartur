"""Anonymous, scrubbed frontend error reports (no auth, no CSRF, nothing stored)."""

import logging
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.logging_config import configure_json_logger, log_event, redact_text
from app.security import client_ip, ip_scoped_limit
from app.services import consume_rate_limit

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
logger = configure_json_logger("avtorinok.frontend_errors")

FRONTEND_ERROR_IP_HOURLY_LIMIT = 30
FRONTEND_ERROR_RATE_NAMESPACE = "frontend-error-ip"
RELEASE_ID_MAX_CHARS = 64
BREADCRUMBS_MAX_ITEMS = 10

# Mirrors the allowlists in web/src/lib/analytics.ts (reportFrontendError).
FrontendErrorType = Literal[
    "Error",
    "TypeError",
    "RangeError",
    "ReferenceError",
    "SyntaxError",
    "NetworkError",
    "ApiClientError",
    "ChunkLoadError",
]
SafeBreadcrumb = Literal[
    "listing_detail_loaded",
    "contact_click",
    "contact_reveal_success",
    "internal_chat_opened",
    "api_request_failed",
]


class FrontendErrorReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: FrontendErrorType
    release_id: str = Field(
        min_length=1,
        max_length=RELEASE_ID_MAX_CHARS,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]*$",
    )
    breadcrumbs: list[SafeBreadcrumb] = Field(max_length=BREADCRUMBS_MAX_ITEMS)


class FrontendErrorAccepted(BaseModel):
    accepted: Literal[True] = True


@router.post("/errors", status_code=202, response_model=FrontendErrorAccepted)
def report_frontend_error(
    payload: FrontendErrorReport,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> FrontendErrorAccepted:
    """Log one scrubbed frontend error event; the request path and query are never logged."""
    ip = client_ip(request)
    consume_rate_limit(
        db,
        FRONTEND_ERROR_RATE_NAMESPACE,
        ip,
        ip_scoped_limit(ip, FRONTEND_ERROR_IP_HOURLY_LIMIT),
        timedelta(hours=1),
    )
    log_event(
        logger,
        logging.WARNING,
        "frontend_error",
        error_type=payload.error_type,
        release_id=redact_text(payload.release_id, limit=RELEASE_ID_MAX_CHARS),
        breadcrumbs=list(payload.breadcrumbs),
    )
    return FrontendErrorAccepted()
