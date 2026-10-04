"""Seller catalog intake and moderator review endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf, require_moderator
from app.catalog_request_schemas import (
    CatalogRequestCreateIn,
    CatalogRequestEnvelopeOut,
    CatalogRequestListOut,
    CatalogRequestMatchesOut,
    CatalogRequestPageOut,
    CatalogRequestReviewIn,
)
from app.catalog_request_service import (
    catalog_request_matches,
    catalog_request_out,
    create_catalog_request,
    list_catalog_requests,
    list_listing_catalog_requests,
    review_catalog_request,
)
from app.db import get_db
from app.models import User
from app.services import fail


router = APIRouter(prefix="/api/v1", tags=["catalog requests"])


@router.post(
    "/me/listings/{listing_id}/catalog-requests",
    response_model=CatalogRequestEnvelopeOut,
    status_code=201,
)
def create_listing_catalog_request(
    listing_id: UUID,
    payload: CatalogRequestCreateIn,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if not idempotency_key:
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    row, replayed = create_catalog_request(
        db,
        user=user,
        listing_id=listing_id,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    response.status_code = 200 if replayed else 201
    response.headers["Cache-Control"] = "no-store"
    return {"request": catalog_request_out(db, row)}


@router.get(
    "/me/listings/{listing_id}/catalog-requests",
    response_model=CatalogRequestListOut,
)
def listing_catalog_requests(
    listing_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    rows = list_listing_catalog_requests(db, listing_id=listing_id, user=user)
    response.headers["Cache-Control"] = "no-store"
    return {"items": [catalog_request_out(db, row) for row in rows]}


@router.get(
    "/moderation/catalog-requests",
    response_model=CatalogRequestPageOut,
)
def moderation_catalog_requests(
    moderator: Annotated[User, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    status: Literal["pending", "resolved", "rejected"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    rows, total = list_catalog_requests(
        db,
        status=status,
        page=page,
        page_size=page_size,
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": [catalog_request_out(db, row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/moderation/catalog-requests/{request_id}/matches",
    response_model=CatalogRequestMatchesOut,
)
def moderation_catalog_request_matches(
    request_id: UUID,
    moderator: Annotated[User, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict:
    query = q.strip()
    if not query:
        fail(422, "invalid_query", "Enter a name or specification to search")
    items = catalog_request_matches(
        db,
        request_id=request_id,
        query=query,
        limit=limit,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"items": items}


@router.post(
    "/moderation/catalog-requests/{request_id}/review",
    response_model=CatalogRequestEnvelopeOut,
)
def review_moderation_catalog_request(
    request_id: UUID,
    payload: CatalogRequestReviewIn,
    moderator: Annotated[User, Depends(require_moderator)],
    csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    row = review_catalog_request(
        db,
        request_id=request_id,
        moderator=moderator,
        payload=payload,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"request": catalog_request_out(db, row)}
