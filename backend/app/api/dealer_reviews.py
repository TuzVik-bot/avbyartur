from datetime import timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf, require_moderator
from app.db import get_db
from app.dealer_review_schemas import (
    DealerReviewInput,
    DealerReviewModerationInput,
    DealerReviewPatch,
    DealerReviewReportInput,
    DealerReviewReportOut,
    DealerReviewReportQueueOut,
    DealerReviewReportResolutionInput,
    DealerReviewReportResolutionResponse,
    DealerReviewResponse,
    ModerationDealerReviewListOut,
    MyDealerReviewResponse,
)
from app.dealer_review_service import author_review, review_out
from app.dealer_services import company_role_for
from app.models import AuditEvent, Company, DealerReview, DealerReviewReport, User, UserSession
from app.services import check_revision, consume_rate_limit, fail

router = APIRouter(prefix="/api/v1", tags=["dealer reviews"])

QUEUE_LIMIT = 100
REVIEW_CREATE_DAILY_LIMIT = 10
REVIEW_REPORT_DAILY_LIMIT = 20


def _approved_company(db: Session, slug: str) -> Company:
    company = db.scalar(select(Company).where(Company.slug == slug, Company.status == "approved"))
    if company is None:
        fail(404, "not_found", "Company not found")
    return company


def _review_exists() -> None:
    fail(409, "dealer_review_exists", "You already submitted a review for this company")


@router.post("/dealers/{slug}/reviews", status_code=201, response_model=DealerReviewResponse)
def create_review(
    slug: str,
    payload: DealerReviewInput,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company = _approved_company(db, slug)
    if company_role_for(db, company, user) is not None:
        fail(403, "dealer_self_review", "Company team members cannot review their own company")
    if db.scalar(
        select(DealerReview.id).where(DealerReview.company_id == company.id, DealerReview.author_id == user.id)
    ):
        _review_exists()
    consume_rate_limit(db, "dealer-review-create", str(user.id), REVIEW_CREATE_DAILY_LIMIT, timedelta(days=1))
    review = DealerReview(
        company_id=company.id, author_id=user.id, rating=payload.rating, text=payload.text, status="pending"
    )
    db.add(review)
    try:
        db.flush()
        db.add(
            AuditEvent(
                actor_id=user.id,
                entity_type="dealer_review",
                entity_id=review.id,
                action="created",
                details={"company_id": str(company.id), "status": "pending"},
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        _review_exists()
    db.refresh(review)
    return {"review": review_out(review, private=True)}


@router.get("/dealers/{slug}/reviews/mine", response_model=MyDealerReviewResponse)
def my_review(
    slug: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company = _approved_company(db, slug)
    return {"review": author_review(db, company.id, user.id)}


@router.patch("/dealer-reviews/{review_id}", response_model=DealerReviewResponse)
def update_review(
    review_id: UUID,
    payload: DealerReviewPatch,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    review = db.scalar(select(DealerReview).where(DealerReview.id == review_id).with_for_update())
    if review is None or review.author_id != user.id:
        fail(404, "not_found", "Review not found")
    check_revision(review, payload.expected_revision, "Review")
    review.rating = payload.rating
    review.text = payload.text
    # Every author edit goes back through moderation before it is public again.
    review.status = "pending"
    review.moderation_reason = None
    review.revision += 1
    db.add(
        AuditEvent(
            actor_id=user.id,
            entity_type="dealer_review",
            entity_id=review.id,
            action="updated",
            details={"status": "pending", "revision": review.revision},
        )
    )
    db.commit()
    db.refresh(review)
    return {"review": review_out(review, private=True)}


@router.post("/dealer-reviews/{review_id}/reports", status_code=201, response_model=DealerReviewReportOut)
def report_review(
    review_id: UUID,
    payload: DealerReviewReportInput,
    user: Annotated[User, Depends(get_current_user)],
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    review = db.get(DealerReview, review_id)
    if review is None or review.status != "published":
        fail(404, "not_found", "Published review not found")
    if review.author_id == user.id:
        fail(403, "dealer_review_self_report", "You cannot report your own review")
    if db.scalar(
        select(DealerReviewReport.id).where(
            DealerReviewReport.review_id == review_id,
            DealerReviewReport.reporter_id == user.id,
        )
    ):
        fail(409, "dealer_review_report_exists", "You already reported this review")
    consume_rate_limit(db, "dealer-review-report", str(user.id), REVIEW_REPORT_DAILY_LIMIT, timedelta(days=1))
    report = DealerReviewReport(review_id=review.id, reporter_id=user.id, reason=payload.reason)
    db.add(report)
    try:
        db.flush()
        db.add(
            AuditEvent(
                actor_id=user.id,
                entity_type="dealer_review",
                entity_id=review.id,
                action="reported",
                details={"report_id": str(report.id)},
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        fail(409, "dealer_review_report_exists", "You already reported this review")
    db.refresh(report)
    return {"id": report.id, "status": report.status}


@router.get("/moderation/dealer-reviews", response_model=ModerationDealerReviewListOut)
def moderation_reviews(
    _moderator: Annotated[User, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[Literal["pending", "published", "rejected", "hidden"], Query()] = "pending",
) -> dict:
    rows = db.scalars(
        select(DealerReview)
        .where(DealerReview.status == status)
        .order_by(DealerReview.created_at, DealerReview.id)
        .limit(QUEUE_LIMIT)
    ).all()
    return {
        "items": [
            {**review_out(review, private=True), "company_id": review.company_id, "author_id": review.author_id}
            for review in rows
        ]
    }


@router.post("/moderation/dealer-reviews/{review_id}/review", response_model=DealerReviewResponse)
def moderate_review(
    review_id: UUID,
    payload: DealerReviewModerationInput,
    moderator: Annotated[User, Depends(require_moderator)],
    _csrf: Annotated[UserSession, Depends(require_csrf)],
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
    db.add(
        AuditEvent(
            actor_id=moderator.id,
            entity_type="dealer_review",
            entity_id=review.id,
            action=payload.status,
            details={
                "status_before": before,
                "status_after": review.status,
                "revision": review.revision,
                "reason": payload.reason,
            },
        )
    )
    db.commit()
    db.refresh(review)
    return {"review": review_out(review, private=True)}


@router.get("/moderation/dealer-review-reports", response_model=DealerReviewReportQueueOut)
def dealer_review_report_queue(
    _moderator: Annotated[User, Depends(require_moderator)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[Literal["open", "resolved"], Query()] = "open",
) -> dict:
    rows = db.execute(
        select(DealerReviewReport, DealerReview, Company)
        .join(DealerReview, DealerReviewReport.review_id == DealerReview.id)
        .join(Company, DealerReview.company_id == Company.id)
        .where(DealerReviewReport.status == status)
        .order_by(DealerReviewReport.created_at, DealerReviewReport.id)
        .limit(QUEUE_LIMIT)
    ).all()
    # The reporter's identity stays out of the queue on purpose.
    return {
        "items": [
            {
                "id": report.id,
                "review_id": review.id,
                "company_name": company.name,
                "review_rating": review.rating,
                "review_text": review.text,
                "reason": report.reason,
                "status": report.status,
                "created_at": report.created_at,
            }
            for report, review, company in rows
        ]
    }


@router.post(
    "/moderation/dealer-review-reports/{report_id}/resolve",
    response_model=DealerReviewReportResolutionResponse,
)
def resolve_dealer_review_report(
    report_id: UUID,
    payload: DealerReviewReportResolutionInput,
    moderator: Annotated[User, Depends(require_moderator)],
    _csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    report = db.scalar(select(DealerReviewReport).where(DealerReviewReport.id == report_id).with_for_update())
    if report is None:
        fail(404, "not_found", "Dealer review report not found")
    if report.status != "open":
        fail(409, "report_already_resolved", "Dealer review report is already resolved")
    report.status = "resolved"
    db.add(
        AuditEvent(
            actor_id=moderator.id,
            entity_type="dealer_review_report",
            entity_id=report.id,
            action="resolved",
            details={"resolution": payload.resolution, "review_id": str(report.review_id)},
        )
    )
    db.commit()
    db.refresh(report)
    return {"report": {"id": report.id, "status": report.status, "resolution": payload.resolution}}
