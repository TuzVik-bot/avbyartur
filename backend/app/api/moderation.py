from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_csrf, require_moderator
from app.db import get_db
from app.admin_service import lock_active_administrators
from app.models import AuditEvent, Company, Listing, ListingStatusEvent, Report, User
from app.risk_signals import collect_listing_risk_signals
from app.listing_change_audit import list_listing_change_history
from app.schemas import CompanyModerationInput, ModerationInput, ReportResolveInput
from app.services import (
    check_revision,
    enqueue_saved_search_match,
    fail,
    lock_owner,
    serialize_listing,
)
from app.staff_schemas import (
    ModerationCompanyQueueResponse,
    ModerationCompanyResponse,
    ModerationListingQueueResponse,
    ModerationListingResponse,
    ModerationListingHistoryOut,
    ModerationReportQueueResponse,
    ModerationReportResponse,
)

router = APIRouter(prefix="/api/v1/moderation", tags=["moderation"])


@router.get("/listings/{listing_id}/history", response_model=ModerationListingHistoryOut)
def listing_change_history(
    listing_id: UUID,
    moderator: Annotated[User, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    if db.get(Listing, listing_id) is None:
        fail(404, "not_found", "Listing not found")
    response.headers["Cache-Control"] = "no-store"
    return {"items": list_listing_change_history(db, listing_id, limit=limit)}


def require_admin(user: Annotated[User, Depends(require_moderator)]) -> User:
    if user.role != "admin":
        fail(403, "forbidden", "Admin access required")
    return user


def _lock_moderation_users(db: Session, actor: User, owner_id: UUID | None = None) -> None:
    # Administrative role changes lock this set first. Keep their order before
    # actor/owner rows, then resource rows, including audit actor FK inserts.
    lock_active_administrators(db)
    ids = {actor.id}
    if owner_id is not None:
        ids.add(owner_id)
    users = {row.id: row for row in db.scalars(
        select(User).where(User.id.in_(ids)).order_by(User.id)
        .with_for_update().execution_options(populate_existing=True)
    ).all()}
    current_actor = users.get(actor.id)
    if current_actor is None or current_actor.status != "active" or current_actor.role not in {"moderator", "admin"}:
        fail(403, "forbidden", "Moderator access required")
    if owner_id is not None:
        owner = users.get(owner_id)
        if owner is None or owner.status != "active":
            fail(403, "seller_unavailable", "Seller account is not active")


def _lock_listing_owner_first(db: Session, listing_id: UUID, actor: User | None = None) -> Listing:
    owner_id = db.scalar(select(Listing.owner_id).where(Listing.id == listing_id))
    if owner_id is None:
        fail(404, "not_found", "Listing not found")
    company_id = db.scalar(select(Listing.company_id).where(Listing.id == listing_id))
    if actor is None:
        lock_owner(db, owner_id)
    else:
        _lock_moderation_users(db, actor, owner_id)
    if company_id is not None:
        company = db.scalar(select(Company).where(Company.id == company_id)
                            .with_for_update().execution_options(populate_existing=True))
        if company is None:
            fail(404, "not_found", "Company not found")
    listing = db.scalar(select(Listing).where(Listing.id == listing_id)
                        .with_for_update().execution_options(populate_existing=True))
    if listing is None:
        fail(404, "not_found", "Listing not found")
    if listing.owner_id != owner_id or listing.company_id != company_id:
        fail(409, "revision_conflict", "Listing ownership changed; reload before retrying")
    return listing


@router.get("/listings", response_model=ModerationListingQueueResponse, response_model_exclude_unset=True)
def listing_queue(
    moderator: Annotated[User, Depends(require_moderator)], db: Annotated[Session, Depends(get_db)],
    status: Literal["pending_review", "active"] = "pending_review",
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    query = select(Listing).where(Listing.status == status).order_by(Listing.created_at, Listing.id)
    total = int(db.scalar(select(func.count(Listing.id)).where(Listing.status == status)) or 0)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    items = [serialize_listing(db, listing, public=False) for listing in rows]
    risk_signals = collect_listing_risk_signals(db, rows)
    for listing, item in zip(rows, items, strict=True):
        item["risk_signals"] = risk_signals[listing.id]
    return {"items": items, "pagination": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}}


@router.post(
    "/listings/{listing_id}/approve",
    response_model=ModerationListingResponse,
    response_model_exclude_unset=True,
)
def approve_listing(
    listing_id: UUID, payload: ModerationInput, moderator: Annotated[User, Depends(require_moderator)],
    csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    listing = _lock_listing_owner_first(db, listing_id, moderator)
    check_revision(listing, payload.expected_revision)
    if listing.status != "pending_review" or listing.submitted_revision != listing.revision:
        fail(409, "revision_conflict", "Only the current submitted revision can be approved")
    if listing.company_id:
        company = db.scalar(select(Company).where(Company.id == listing.company_id).with_for_update())
        if company is None or company.status != "approved":
            fail(409, "company_not_approved", "The company is not approved")
    listing.revision += 1
    listing.moderated_at = datetime.now(UTC)
    listing.moderation_reason = None
    old_status = listing.status
    listing.status = "active"
    db.add(ListingStatusEvent(listing_id=listing.id, actor_id=moderator.id, from_status=old_status, to_status="active", revision=listing.revision, reason=None))
    enqueue_saved_search_match(db, listing)
    db.add(AuditEvent(actor_id=moderator.id, entity_type="listing", entity_id=listing.id, action="approved", details={"revision": payload.expected_revision}))
    db.commit()
    return {"listing": serialize_listing(db, listing, public=False)}


def _listing_decision(listing_id: UUID, payload: ModerationInput, moderator: User, db: Session, target: str) -> dict:
    if not payload.reason or not payload.reason.strip():
        fail(422, "reason_required", "A reason is required", {"reason": "Required"})
    listing = _lock_listing_owner_first(db, listing_id, moderator)
    check_revision(listing, payload.expected_revision)
    if target == "blocked":
        if listing.status not in {"pending_review", "active"}:
            fail(409, "revision_conflict", "Only pending or active listings can be blocked")
        if listing.status == "pending_review" and listing.submitted_revision != listing.revision:
            fail(409, "revision_conflict", "Only the current submitted revision can be blocked")
    elif listing.status != "pending_review" or listing.submitted_revision != listing.revision:
        fail(409, "revision_conflict", "Only the current submitted revision can be moderated")
    old_status = listing.status
    listing.revision += 1
    listing.moderated_at = datetime.now(UTC)
    listing.moderation_reason = payload.reason.strip()
    listing.status = target
    db.add(ListingStatusEvent(listing_id=listing.id, actor_id=moderator.id, from_status=old_status, to_status=target, revision=listing.revision, reason=payload.reason.strip()))
    db.add(AuditEvent(actor_id=moderator.id, entity_type="listing", entity_id=listing.id, action=target, details={"reason": payload.reason.strip(), "revision": payload.expected_revision}))
    db.commit()
    return {"listing": serialize_listing(db, listing, public=False)}


@router.post(
    "/listings/{listing_id}/reject",
    response_model=ModerationListingResponse,
    response_model_exclude_unset=True,
)
def reject_listing(listing_id: UUID, payload: ModerationInput, moderator: Annotated[User, Depends(require_moderator)], csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    return _listing_decision(listing_id, payload, moderator, db, "rejected")


@router.post(
    "/listings/{listing_id}/block",
    response_model=ModerationListingResponse,
    response_model_exclude_unset=True,
)
def block_listing(listing_id: UUID, payload: ModerationInput, moderator: Annotated[User, Depends(require_moderator)], csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    return _listing_decision(listing_id, payload, moderator, db, "blocked")


@router.get("/companies", response_model=ModerationCompanyQueueResponse)
def company_queue(moderator: Annotated[User, Depends(require_moderator)], db: Annotated[Session, Depends(get_db)]) -> dict:
    rows = db.scalars(select(Company).where(Company.status == "pending").order_by(Company.created_at, Company.id)).all()
    return {"items": [{
        "id": str(row.id), "name": row.name, "slug": row.slug, "unp": row.unp,
        "address": row.address, "phone": row.phone, "status": row.status,
        "revision": row.revision,
    } for row in rows]}


@router.post("/companies/{company_id}/approve", response_model=ModerationCompanyResponse)
def approve_company(
    company_id: UUID, payload: CompanyModerationInput, admin: Annotated[User, Depends(require_admin)],
    csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    return _company_decision(company_id, admin, db, "approved", None, payload.expected_revision)


def _company_decision(
    company_id: UUID, moderator: User, db: Session, target: str, reason: str | None,
    expected_revision: int,
) -> dict:
    _lock_moderation_users(db, moderator)
    company = db.scalar(select(Company).where(Company.id == company_id).with_for_update().execution_options(populate_existing=True))
    if company is None:
        fail(404, "not_found", "Company not found")
    check_revision(company, expected_revision, "Company")
    if target == "approved" and company.status != "pending":
        fail(409, "invalid_company_state", "Only pending companies can be approved")
    if target in {"rejected", "blocked"} and company.status not in {"pending", "approved", "rejected"}:
        fail(409, "invalid_company_state", "Company cannot move to this state")
    old_status = company.status
    company.status = target
    company.moderation_reason = reason
    company.revision += 1
    details = {"from_status": old_status, "to_status": target}
    if reason:
        details["reason"] = reason
    details["revision"] = expected_revision
    db.add(AuditEvent(actor_id=moderator.id, entity_type="company", entity_id=company.id, action=target, details=details))
    db.commit()
    return {"company": {
        "id": str(company.id), "name": company.name, "slug": company.slug,
        "status": company.status, "revision": company.revision,
        "moderation_reason": company.moderation_reason,
    }}


@router.post("/companies/{company_id}/reject", response_model=ModerationCompanyResponse)
def reject_company(company_id: UUID, payload: CompanyModerationInput, moderator: Annotated[User, Depends(require_moderator)], csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    if not payload.reason or not payload.reason.strip():
        fail(422, "reason_required", "A reason is required", {"reason": "Required"})
    return _company_decision(company_id, moderator, db, "rejected", payload.reason.strip(), payload.expected_revision)


@router.post("/companies/{company_id}/block", response_model=ModerationCompanyResponse)
def block_company(company_id: UUID, payload: CompanyModerationInput, moderator: Annotated[User, Depends(require_moderator)], csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    if not payload.reason or not payload.reason.strip():
        fail(422, "reason_required", "A reason is required", {"reason": "Required"})
    return _company_decision(company_id, moderator, db, "blocked", payload.reason.strip(), payload.expected_revision)


@router.get("/reports", response_model=ModerationReportQueueResponse)
def report_queue(
    moderator: Annotated[User, Depends(require_moderator)], db: Annotated[Session, Depends(get_db)],
    status: Literal["open", "resolved"] = "open",
) -> dict:
    rows = db.scalars(select(Report).where(Report.status == status).order_by(Report.created_at, Report.id)).all()
    return {"items": [{
        "id": str(row.id), "listing_id": str(row.listing_id), "category": row.category,
        "comment": row.comment, "status": row.status, "revision": row.revision,
        "created_at": row.created_at.isoformat(),
    } for row in rows]}


@router.post("/reports/{report_id}/resolve", response_model=ModerationReportResponse)
def resolve_report(report_id: UUID, payload: ReportResolveInput, moderator: Annotated[User, Depends(require_moderator)], csrf: Annotated[object, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    _lock_moderation_users(db, moderator)
    report = db.scalar(select(Report).where(Report.id == report_id).with_for_update().execution_options(populate_existing=True))
    if report is None:
        fail(404, "not_found", "Report not found")
    check_revision(report, payload.expected_revision, "Report")
    report.status = "resolved"
    report.resolution = payload.resolution.strip()
    report.revision += 1
    db.add(AuditEvent(
        actor_id=moderator.id, entity_type="report", entity_id=report.id, action="resolved",
        details={"resolution": report.resolution, "revision": payload.expected_revision},
    ))
    db.commit()
    return {"report": {
        "id": str(report.id), "status": report.status, "revision": report.revision,
        "resolution": report.resolution,
    }}
