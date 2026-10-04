from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    ContactReveal,
    Conversation,
    DealerTeamMember,
    Listing,
    ListingViewEvent,
    User,
)
from app.services import fail


TEAM_ROLES = frozenset({"owner", "admin", "seller", "viewer"})
WRITE_ROLES = frozenset({"owner", "admin", "seller"})
MANAGER_ROLES = frozenset({"owner", "admin"})


def company_role_for(
    db: Session,
    company: Company,
    user: User,
    *,
    lock: bool = False,
) -> str | None:
    if company.owner_id == user.id:
        return "owner"
    query = select(DealerTeamMember).where(
        DealerTeamMember.company_id == company.id,
        DealerTeamMember.user_id == user.id,
        DealerTeamMember.status == "active",
        User.id == user.id,
        User.status == "active",
    ).join(User, DealerTeamMember.user_id == User.id)
    if lock:
        query = query.with_for_update()
    member = db.scalar(query)
    return member.role if member else None


def company_ids_for_user(db: Session, user: User) -> list[UUID]:
    owned = db.scalars(select(Company.id).where(Company.owner_id == user.id)).all()
    memberships = db.scalars(
        select(DealerTeamMember.company_id)
        .join(User, User.id == DealerTeamMember.user_id)
        .where(
            DealerTeamMember.user_id == user.id,
            DealerTeamMember.status == "active",
            User.status == "active",
        )
    ).all()
    return list(dict.fromkeys([*owned, *memberships]))


def resolve_company_for_user(
    db: Session,
    user: User,
    *,
    allowed_roles: frozenset[str] | set[str] | None = None,
    require_approved: bool = False,
    lock: bool = False,
) -> tuple[Company, str]:
    owned_query = select(Company).where(Company.owner_id == user.id)
    if lock:
        owned_query = owned_query.with_for_update()
    company = db.scalar(owned_query)
    role = "owner" if company is not None else None

    if company is None:
        query = (
            select(Company)
            .join(DealerTeamMember, DealerTeamMember.company_id == Company.id)
            .join(User, User.id == DealerTeamMember.user_id)
            .where(
                DealerTeamMember.user_id == user.id,
                DealerTeamMember.status == "active",
                User.status == "active",
            )
            .order_by(Company.created_at, Company.id)
        )
        if lock:
            query = query.with_for_update(of=Company)
        matches = db.scalars(query).all()
        if len(matches) > 1:
            fail(409, "company_scope_ambiguous", "Select a company scope before continuing")
        if matches:
            company = matches[0]
            role = company_role_for(db, company, user, lock=lock)

    if company is None or role is None:
        fail(403, "company_membership_required", "An active company membership is required")
    if company.status == "blocked":
        fail(403, "company_blocked", "Company access is blocked")
    if require_approved and company.status != "approved":
        fail(403, "company_not_approved", "An approved company is required")
    if allowed_roles is not None and role not in allowed_roles:
        fail(403, "forbidden", "This company role cannot perform the requested action")
    return company, role


def require_company_role(
    db: Session,
    company_id: UUID,
    user: User,
    allowed_roles: frozenset[str] | set[str],
    *,
    require_approved: bool = False,
    lock: bool = False,
) -> tuple[Company, str]:
    query = select(Company).where(Company.id == company_id)
    if lock:
        query = query.with_for_update()
    company = db.scalar(query)
    if company is None:
        fail(404, "not_found", "Company not found")
    role = company_role_for(db, company, user, lock=lock)
    if role is None:
        fail(404, "not_found", "Company not found")
    if company.status == "blocked":
        fail(403, "company_blocked", "Company access is blocked")
    if require_approved and company.status != "approved":
        fail(403, "company_not_approved", "An approved company is required")
    if role not in allowed_roles:
        fail(403, "forbidden", "This company role cannot perform the requested action")
    return company, role


def dealer_analytics(
    db: Session,
    user: User,
    *,
    date_from: date,
    date_to: date,
) -> dict:
    company, _ = resolve_company_for_user(db, user, require_approved=True)
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)

    listing_rows = db.execute(
        select(Listing.id, Listing.title, Listing.status)
        .where(Listing.company_id == company.id)
        .order_by(Listing.updated_at.desc(), Listing.id.desc())
    ).all()
    listing_ids = [row.id for row in listing_rows]
    reveal_counts: dict[UUID, int] = {}
    chat_counts: dict[UUID, int] = {}
    view_counts: dict[UUID, int] = {}
    if listing_ids:
        reveal_counts = dict(db.execute(
            select(ContactReveal.listing_id, func.count(ContactReveal.id))
            .where(
                ContactReveal.listing_id.in_(listing_ids),
                ContactReveal.created_at >= start,
                ContactReveal.created_at < end,
            )
            .group_by(ContactReveal.listing_id)
        ).all())
        chat_counts = dict(db.execute(
            select(Conversation.listing_id, func.count(Conversation.id))
            .where(
                Conversation.listing_id.in_(listing_ids),
                Conversation.created_at >= start,
                Conversation.created_at < end,
            )
            .group_by(Conversation.listing_id)
        ).all())
        view_counts = dict(db.execute(
            select(ListingViewEvent.listing_id, func.count(ListingViewEvent.id))
            .where(
                ListingViewEvent.listing_id.in_(listing_ids),
                ListingViewEvent.created_at >= start,
                ListingViewEvent.created_at < end,
            )
            .group_by(ListingViewEvent.listing_id)
        ).all())

    return {
        "period": {"start": date_from.isoformat(), "end": date_to.isoformat()},
        "totals": {
            "listings": len(listing_rows),
            "active_listings": sum(row.status == "active" for row in listing_rows),
            "contact_reveals": sum(reveal_counts.values()),
            "chats": sum(chat_counts.values()),
            "views": sum(view_counts.values()),
        },
        "items": [
            {
                "listing_id": row.id,
                "title": row.title,
                "status": row.status,
                "contact_reveals": reveal_counts.get(row.id, 0),
                "chats": chat_counts.get(row.id, 0),
                "views": view_counts.get(row.id, 0),
            }
            for row in listing_rows
        ],
    }
