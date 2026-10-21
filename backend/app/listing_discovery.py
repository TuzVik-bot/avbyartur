from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Listing
from app.services import latest_listing_exchange_rate, public_listings_query

RELATED_LISTING_LIMIT = 8
RELATED_CANDIDATE_POOL_LIMIT = 100
RECENT_LISTING_LIMIT = 12


def _normalized_name(column):
    return func.lower(func.trim(func.coalesce(column, "")))


def related_listing_candidates(db: Session, listing: Listing) -> list[Listing]:
    """Return a small, deterministic set ranked by vehicle match and comparable budget."""
    same_model_conditions = []
    same_make_conditions = []
    model_name = (listing.manual_model or listing.model_name_snapshot or "").strip()
    make_name = (listing.manual_make or listing.make_name_snapshot or "").strip()
    model_text_conditions = []

    if listing.model_id is not None:
        same_model_conditions.append(Listing.model_id == listing.model_id)
    if model_name:
        model_text_conditions.extend((
            _normalized_name(Listing.manual_model) == model_name.casefold(),
            _normalized_name(Listing.model_name_snapshot) == model_name.casefold(),
        ))
    if listing.make_id is not None:
        same_make_conditions.append(Listing.make_id == listing.make_id)
    if make_name:
        same_make_conditions.append(_normalized_name(Listing.manual_make) == make_name.casefold())
        same_make_conditions.append(_normalized_name(Listing.make_name_snapshot) == make_name.casefold())
    if model_text_conditions:
        model_text_match = or_(*model_text_conditions)
        if same_make_conditions:
            model_text_match = and_(model_text_match, or_(*same_make_conditions))
        same_model_conditions.append(model_text_match)

    same_model = or_(*same_model_conditions) if same_model_conditions else None
    same_make = or_(*same_make_conditions) if same_make_conditions else None
    related_conditions = [condition for condition in (same_model, same_make) if condition is not None]

    if related_conditions:
        candidate_filter = or_(*related_conditions)
        related_rank = case(
            *(([(same_model, 0)] if same_model is not None else []) + ([(same_make, 1)] if same_make is not None else [])),
            else_=2,
        )
    elif listing.body_type_id is not None:
        candidate_filter = Listing.body_type_id == listing.body_type_id
        related_rank = case((candidate_filter, 2), else_=3)
    elif listing.region_id is not None:
        candidate_filter = Listing.region_id == listing.region_id
        related_rank = case((candidate_filter, 2), else_=3)
    else:
        return []

    candidate_query = (
        public_listings_query()
        .where(
            Listing.id != listing.id,
            Listing.category_code == listing.category_code,
            candidate_filter,
        )
        .order_by(related_rank, Listing.created_at.desc(), Listing.id.desc())
        .limit(RELATED_CANDIDATE_POOL_LIMIT)
        .with_only_columns(Listing.id)
    )
    candidate_ids = candidate_query.subquery()

    price_distance = None
    if listing.price_amount is not None and listing.currency in {"BYN", "USD"}:
        rate, rate_is_fresh = latest_listing_exchange_rate(db)
        if rate is not None and rate_is_fresh:
            target_byn = (
                Decimal(listing.price_amount)
                if listing.currency == "BYN"
                else Decimal(listing.price_amount) * rate.official_rate / Decimal(rate.scale)
            )
            candidate_byn = case(
                (Listing.currency == "BYN", Listing.price_amount),
                (Listing.currency == "USD", Listing.price_amount * rate.official_rate / Decimal(rate.scale)),
                else_=None,
            )
            price_distance = func.abs(candidate_byn - target_byn) / target_byn
        else:
            # If the exchange rate is stale, compare prices only when their
            # declared currencies match the target's. Never rank raw BYN and
            # USD amounts against each other.
            candidate_price = case(
                (Listing.currency == listing.currency, Listing.price_amount),
                else_=None,
            )
            price_distance = func.abs(candidate_price - Decimal(listing.price_amount)) / Decimal(listing.price_amount)

    ranked_query = public_listings_query().where(Listing.id.in_(select(candidate_ids.c.id)))
    order = [related_rank]
    if price_distance is not None:
        order.append(price_distance.asc().nullslast())
    order.extend((Listing.created_at.desc(), Listing.id.desc()))
    return db.scalars(ranked_query.order_by(*order).limit(RELATED_LISTING_LIMIT)).all()


def public_recent_listing_candidates(db: Session, ids: list[UUID]) -> list[Listing]:
    """Batch-revalidate local recent IDs and preserve their requested order."""
    ordered_ids = list(dict.fromkeys(ids))[:RECENT_LISTING_LIMIT]
    if not ordered_ids:
        return []
    requested_order = case(
        {listing_id: index for index, listing_id in enumerate(ordered_ids)},
        value=Listing.id,
        else_=len(ordered_ids),
    )
    return db.scalars(
        public_listings_query()
        .where(Listing.id.in_(ordered_ids))
        .order_by(requested_order)
        .limit(RECENT_LISTING_LIMIT)
    ).all()
