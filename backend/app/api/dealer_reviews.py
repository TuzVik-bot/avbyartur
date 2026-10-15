from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf, require_moderator
from app.db import get_db
from app.dealer_review_schemas import DealerReviewInput, DealerReviewModerationInput, DealerReviewPatch, DealerReviewReportInput
from app.dealer_review_service import public_reviews, review_out
from app.dealer_services import company_role_for
from app.models import AuditEvent, Company, DealerReview, DealerReviewReport, User, UserSession
from app.services import check_revision, fail

router = APIRouter(prefix="/api/v1", tags=["dealer reviews"])


def _company_or_404(db: Session, slug: str) -> Company:
    company = db.scalar(select(Company).where(Company.slug == slug, Company.status == "approved"))
    if company is None:
        fail(404, "not_found", "Company not found")
    return company


@router.post("/dealers/{slug}/reviews", status_code=201)
def create_review(
    slug: str, payload: DealerReviewInput,
    user: Annotated[User, Depends(get_current_user)], _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company = _company_or_404(db, slug)
    if company_role_for(db, company, user) is not None:
        fail(403, "dealer_self_review", "Company team members cannot review their own company")
    if db.scalar(select(DealerReview.id).where(DealerReview.company_id == company.id, DealerReview.author_id == user.id)):
        fail(409, "dealer_review_exists", "You already submitted a review for this company")
    review = DealerReview(company_id=company.id, author_id=user.id, rating=payload.rating, text=payload.text, status="pending")
    db.add(review)
    try:
        db.flush()
        db.add(AuditEvent(actor_id=user.id, entity_type="dealer_review", entity_id=review.id, action="created", details={"company_id": str(company.id), "status": "pending"}))
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "dealer_review_exists", "You already submitted a review for this company")
    db.refresh(review)
    return {"review": review_out(review, private=True)}


@router.get("/dealers/{slug}/reviews/mine")
def my_review(
    slug: str, user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    company = _company_or_404(db, slug)
    return {"review": public_reviews(db, company.id, author_id=user.id)["my_review"]}


@router.patch("/dealer-reviews/{review_id}")
def update_review(
    review_id: UUID, payload: DealerReviewPatch,
    user: Annotated[User, Depends(get_current_user)], _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    review = db.scalar(select(DealerReview).where(DealerReview.id == review_id).with_for_update())
    if review is None or review.author_id != user.id:
        fail(404, "not_found", "Review not found")
    check_revision(review, payload.expected_revision, "Review")
    review.rating = payload.rating
    review.text = payload.text
    review.status = "pending"
    review.moderation_reason = None
    review.revision += 1
    db.add(AuditEvent(actor_id=user.id, entity_type="dealer_review", entity_id=review.id, action="updated", details={"status": "pending", "revision": review.revision}))
    db.commit()
    db.refresh(review)
    return {"review": review_out(review, private=True)}


@router.post("/dealer-reviews/{review_id}/reports", status_code=201)
def report_review(
    review_id: UUID, payload: DealerReviewReportInput,
    user: Annotated[User, Depends(get_current_user)], _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    review = db.get(DealerReview, review_id)
    if review is None or review.status != "published":
        fail(404, "not_found", "Published review not found")
    if review.author_id == user.id:
        fail(403, "dealer_review_self_report", "You cannot report your own review")
    existing = db.scalar(select(DealerReviewReport).where(DealerReviewReport.review_id == review_id, DealerReviewReport.reporter_id == user.id))
    if existing is not None:
        fail(409, "dealer_review_report_exists", "You already reported this review")
    report = DealerReviewReport(review_id=review.id, reporter_id=user.id, reason=payload.reason)
    db.add(report)
    try:
        db.flush()
        db.add(AuditEvent(actor_id=user.id, entity_type="dealer_review", entity_id=review.id, action="reported", details={"report_id": str(report.id)}))
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "dealer_review_report_exists", "You already reported this review")
    return {"id": report.id, "status": report.status}


@router.get("/moderation/dealer-reviews")
def moderation_reviews(
    moderator: Annotated[User, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[Literal["pending", "published", "rejected", "hidden"], Query()] = "pending",
) -> dict:
    rows = db.scalars(select(DealerReview).where(DealerReview.status == status).order_by(DealerReview.created_at, DealerReview.id).limit(100)).all()
    return {"items": [
        {**review_out(review, private=True), "company_id": review.company_id, "author_id": review.author_id}
        for review in rows
    ]}


@router.post("/moderation/dealer-reviews/{review_id}/review")
def moderate_review(
    review_id: UUID, payload: DealerReviewModerationInput,
    moderator: Annotated[User, Depends(require_moderator)], _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    review = db.scalar(select(DealerReview).where(DealerReview.id == review_id).with_for_update())
    if review is None:
        fail(404, "not_found", "Review not found")
    check_revision(review, payload.expected_revision, "Review")
    before = review.status
    review.status = payload.status
    review.moderation_reason = payload.reason
    review.revision += 1
    db.add(AuditEvent(actor_id=moderator.id, entity_type="dealer_review", entity_id=review.id, action=payload.status, details={"status_before": before, "status_after": review.status, "revision": review.revision}))
    db.commit()
    db.refresh(review)
    return {"review": review_out(review, private=True)}
