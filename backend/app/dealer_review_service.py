from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DealerReview


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


def public_reviews(db: Session, company_id: UUID, *, author_id: UUID | None = None) -> dict:
    summary = db.execute(
        select(func.count(DealerReview.id), func.avg(DealerReview.rating)).where(
            DealerReview.company_id == company_id,
            DealerReview.status == "published",
        )
    ).one()
    items = db.scalars(
        select(DealerReview)
        .where(DealerReview.company_id == company_id, DealerReview.status == "published")
        .order_by(DealerReview.created_at.desc(), DealerReview.id.desc())
        .limit(30)
    ).all()
    mine = None
    if author_id is not None:
        mine_row = db.scalar(select(DealerReview).where(
            DealerReview.company_id == company_id,
            DealerReview.author_id == author_id,
        ))
        if mine_row is not None:
            mine = review_out(mine_row, private=True)
    return {
        "reviews": {
            "items": [review_out(review) for review in items],
            "count": int(summary[0] or 0),
            "average_rating": round(float(summary[1]), 2) if summary[1] is not None else None,
        },
        "my_review": mine,
    }
