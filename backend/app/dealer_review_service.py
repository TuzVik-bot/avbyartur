from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DealerReview

PUBLIC_REVIEW_LIMIT = 30


def review_out(review: DealerReview, *, private: bool = False) -> dict:
    result = {
        "id": review.id,
        "rating": review.rating,
        "text": review.text,
        "created_at": review.created_at,
    }
    if private:
        result.update(status=review.status, revision=review.revision, moderation_reason=review.moderation_reason)
    return result


def public_reviews(db: Session, company_id: UUID) -> dict:
    """Published reviews of one company with their count and average rating."""

    published = (DealerReview.company_id == company_id, DealerReview.status == "published")
    count, average = db.execute(
        select(func.count(DealerReview.id), func.avg(DealerReview.rating)).where(*published)
    ).one()
    items = db.scalars(
        select(DealerReview)
        .where(*published)
        .order_by(DealerReview.created_at.desc(), DealerReview.id.desc())
        .limit(PUBLIC_REVIEW_LIMIT)
    ).all()
    return {
        "items": [review_out(review) for review in items],
        "count": int(count or 0),
        "average_rating": round(float(average), 2) if average is not None else None,
    }


def author_review(db: Session, company_id: UUID, author_id: UUID) -> dict | None:
    review = db.scalar(
        select(DealerReview).where(
            DealerReview.company_id == company_id,
            DealerReview.author_id == author_id,
        )
    )
    return review_out(review, private=True) if review is not None else None
