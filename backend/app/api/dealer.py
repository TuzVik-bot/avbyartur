from datetime import date, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_csrf
from app.db import get_db
from app.dealer_schemas import (
    DealerAnalyticsOut,
    DealerTeamCreate,
    DealerTeamListOut,
    DealerTeamMutationOut,
    DealerTeamPatch,
)
from app.dealer_services import (
    MANAGER_ROLES,
    dealer_analytics,
    resolve_company_for_user,
)
from app.models import AuditEvent, Company, DealerTeamMember, User, UserSession
from app.services import check_revision, fail, lock_owner
from app.admin_service import lock_active_administrators


router = APIRouter(prefix="/api/v1/dealer", tags=["dealer"])


def _member_out(member: DealerTeamMember, user: User) -> dict:
    effective_status = member.status if user.status == "active" else "revoked"
    return {
        "id": member.id,
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": member.role,
        "status": effective_status,
        "revision": member.revision,
        "created_at": member.created_at,
    }


def _owner_out(company: Company, user: User) -> dict:
    return {
        "id": user.id,
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": "owner",
        "status": "active",
        "revision": company.revision,
        "created_at": company.created_at,
    }


@router.get("/team", response_model=DealerTeamListOut)
def dealer_team(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company, _role = resolve_company_for_user(db, user)
    owner = db.get(User, company.owner_id)
    items = [_owner_out(company, owner)] if owner is not None else []
    members = db.execute(
        select(DealerTeamMember, User)
        .join(User, User.id == DealerTeamMember.user_id)
        .where(DealerTeamMember.company_id == company.id)
        .order_by(DealerTeamMember.created_at, DealerTeamMember.id)
    ).all()
    items.extend(_member_out(member, member_user) for member, member_user in members)
    return {"items": items}


def _lock_team_users(db: Session, actor: User, target_id: UUID | None) -> dict[UUID, User]:
    # User administration locks its active-admin guard before any target.
    # Team changes must use that same order, including audit foreign keys.
    lock_active_administrators(db)
    ids = {actor.id}
    if target_id is not None:
        ids.add(target_id)
    rows = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.id)
                      .with_for_update().execution_options(populate_existing=True)).all()
    users = {row.id: row for row in rows}
    current = users.get(actor.id)
    if current is None or current.status != "active":
        fail(403, "account_unavailable", "Account is unavailable")
    return users


@router.post("/team", response_model=DealerTeamMutationOut)
def add_dealer_team_member(
    payload: DealerTeamCreate,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    locked_users = _lock_team_users(db, user, payload.user_id)
    target = locked_users.get(payload.user_id)
    company, actor_role = resolve_company_for_user(db, user, allowed_roles=MANAGER_ROLES, lock=True)
    if target is None or target.status != "active":
        fail(404, "active_user_not_found", "Only an existing active user can join a company")
    if target.id == company.owner_id:
        fail(409, "owner_already_member", "The company owner is already a team member")
    owned_company_ids = db.scalars(select(Company.id).where(Company.owner_id == target.id)).all()
    if owned_company_ids:
        fail(409, "user_already_in_company", "This user already owns a company")

    memberships = db.scalars(
        select(DealerTeamMember).where(
            DealerTeamMember.user_id == target.id,
            DealerTeamMember.status == "active",
        )
    ).all()
    if any(item.company_id != company.id for item in memberships):
        fail(409, "user_already_in_company", "This user already belongs to another company")

    existing = db.scalar(
        select(DealerTeamMember)
        .where(
            DealerTeamMember.company_id == company.id,
            DealerTeamMember.user_id == target.id,
        )
        .with_for_update()
    )
    if existing is not None and existing.status == "active":
        fail(409, "team_member_exists", "This user is already on the company team")
    if payload.role == "admin" and actor_role != "owner":
        fail(403, "owner_required", "Only the company owner can grant the admin role")

    if existing is None:
        member = DealerTeamMember(
            company_id=company.id,
            user_id=target.id,
            role=payload.role,
            status="active",
            revision=1,
            granted_by=user.id,
        )
        db.add(member)
        action = "created"
    else:
        member = existing
        member.role = payload.role
        member.status = "active"
        member.revision += 1
        member.granted_by = user.id
        action = "reactivated"
    db.flush()
    db.add(AuditEvent(
        actor_id=user.id,
        entity_type="dealer_team_member",
        entity_id=member.id,
        action=action,
        details={"company_id": str(company.id), "role": member.role},
    ))
    db.commit()
    return {"member": _member_out(member, target)}


@router.patch("/team/{member_id}", response_model=DealerTeamMutationOut)
def update_dealer_team_member(
    member_id: UUID,
    payload: DealerTeamPatch,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    target_id = db.scalar(select(DealerTeamMember.user_id).where(DealerTeamMember.id == member_id))
    locked_users = _lock_team_users(db, user, target_id)
    company, actor_role = resolve_company_for_user(db, user, allowed_roles=MANAGER_ROLES, lock=True)
    member = db.scalar(
        select(DealerTeamMember)
        .where(
            DealerTeamMember.id == member_id,
            DealerTeamMember.company_id == company.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if member is None:
        if member_id == company.owner_id:
            fail(403, "owner_protected", "The company owner cannot be changed through team management")
        fail(404, "not_found", "Team member not found")
    if actor_role != "owner" and member.role == "admin":
        fail(403, "owner_required", "Only the company owner can change an admin member")
    if payload.role == "admin" and actor_role != "owner":
        fail(403, "owner_required", "Only the company owner can grant the admin role")
    target = locked_users.get(member.user_id)
    if target is None:
        fail(404, "active_user_not_found", "Team member is no longer available")
    if payload.status == "active" and target.status != "active":
        fail(409, "inactive_user", "An inactive user cannot be reactivated on the team")

    check_revision(member, payload.expected_revision, "Team member")
    changed = False
    if payload.role is not None and payload.role != member.role:
        member.role = payload.role
        changed = True
    if payload.status is not None and payload.status != member.status:
        member.status = payload.status
        changed = True
    if changed:
        member.revision += 1
        db.add(AuditEvent(
            actor_id=user.id,
            entity_type="dealer_team_member",
            entity_id=member.id,
            action="updated",
            details={"company_id": str(company.id), "role": member.role, "status": member.status},
        ))
    db.commit()
    return {"member": _member_out(member, target)}


@router.get("/analytics", response_model=DealerAnalyticsOut)
def dealer_analytics_summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dict:
    today = date.today()
    if date_from is None and date_to is None:
        date_from, date_to = today - timedelta(days=29), today
    elif date_from is None:
        date_from = date_to
    elif date_to is None:
        date_to = date_from
    if date_from > date_to:
        fail(422, "invalid_period", "The start date must not follow the end date")
    if (date_to - date_from).days > 366:
        fail(422, "period_too_wide", "Analytics period cannot exceed 367 days")
    return dealer_analytics(db, user, date_from=date_from, date_to=date_to)
