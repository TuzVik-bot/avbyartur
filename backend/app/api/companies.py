import hashlib
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import company_context_for_user, get_current_user, require_csrf
from app.company_schemas import (
    CompanyMutationResponse,
    DealerDetailResponse,
    DealerDirectoryResponse,
    MyCompanyResponse,
)
from app.dealer_services import MANAGER_ROLES, require_company_role
from app.db import get_db
from app.models import AuditEvent, Company, DealerTeamMember, Listing, User, UserSession
from app.schemas import CompanyInput, CompanyPatchInput
from app.services import (
    check_revision,
    fail,
    listing_publication_dates,
    lock_owner,
    serialize_listings,
)

router = APIRouter(prefix="/api/v1", tags=["companies"])


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return (slug or f"dealer-{hashlib.sha1(name.encode()).hexdigest()[:12]}")[:190]


def _company_out(company: Company, *, private: bool) -> dict:
    result = {
        "id": str(company.id), "name": company.name, "slug": company.slug,
        "status": company.status, "revision": getattr(company, "revision", 1), "address": company.address,
        "business_hours": company.business_hours,
    }
    if private:
        result.update(unp=company.unp, phone=company.phone, moderation_reason=company.moderation_reason)
    return result


def _is_duplicate_company_unp(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None) == "uq_company_unp"


@router.get("/me/company", response_model=MyCompanyResponse)
def my_company(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]) -> dict:
    company, _role = company_context_for_user(db, user)
    return {"company": _company_out(company, private=True) if company else None}


@router.post("/companies", response_model=CompanyMutationResponse)
def create_company(
    payload: CompanyInput, user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    lock_owner(db, user.id)
    existing = db.scalar(select(Company).where(Company.owner_id == user.id).with_for_update())
    if existing:
        fail(409, "company_exists", "This account already owns a company")
    active_membership = db.scalar(
        select(DealerTeamMember.id)
        .where(DealerTeamMember.user_id == user.id, DealerTeamMember.status == "active")
        .limit(1)
    )
    if active_membership is not None:
        fail(409, "user_already_in_company", "This account already belongs to a company")
    if db.scalar(select(Company.id).where(Company.unp == payload.unp)):
        fail(409, "company_unp_exists", "This UNP is already assigned to a company")
    base = _slug(payload.name)
    slug = base
    if db.scalar(select(Company.id).where(Company.slug == slug)):
        slug = f"{base[:170]}-{hashlib.sha1(payload.unp.encode()).hexdigest()[:8]}"
    company = Company(
        owner_id=user.id, name=payload.name.strip(), slug=slug, unp=payload.unp,
        address=payload.address.strip(), phone=payload.phone.strip(), status="pending",
        business_hours=payload.business_hours.model_dump(mode="json") if payload.business_hours else None,
    )
    db.add(company)
    try:
        db.flush()
        db.add(AuditEvent(actor_id=user.id, entity_type="company", entity_id=company.id, action="created", details={"status": "pending"}))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_company_unp(exc):
            fail(409, "company_unp_exists", "This UNP is already assigned to a company")
        raise
    return {"company": _company_out(company, private=True)}


@router.patch("/companies/{company_id}", response_model=CompanyMutationResponse)
def update_company(
    company_id: UUID, payload: CompanyPatchInput, user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)],
) -> dict:
    company, _role = require_company_role(
        db, company_id, user, MANAGER_ROLES, lock=True,
    )
    check_revision(company, payload.expected_revision, "Company")
    if company.status == "blocked":
        fail(403, "company_blocked", "Blocked company cannot be edited")
    old_status = company.status
    changed_fields = []
    critical_changed_fields = []
    for key in ("name", "unp", "address", "phone"):
        value = getattr(payload, key).strip()
        if getattr(company, key) != value:
            if key == "unp" and db.scalar(
                select(Company.id).where(Company.unp == value, Company.id != company.id)
            ):
                fail(409, "company_unp_exists", "This UNP is already assigned to a company")
            changed_fields.append(key)
            critical_changed_fields.append(key)
            setattr(company, key, value)

    if "business_hours" in payload.model_fields_set:
        business_hours = payload.business_hours.model_dump(mode="json") if payload.business_hours else None
        if company.business_hours != business_hours:
            company.business_hours = business_hours
            changed_fields.append("business_hours")

    if critical_changed_fields and old_status != "pending":
        company.status = "pending"
        company.moderation_reason = None
    if "name" in changed_fields:
        base = _slug(company.name)
        company.slug = f"{base[:170]}-{hashlib.sha1(company.unp.encode()).hexdigest()[:8]}"
    company.revision += 1
    db.add(AuditEvent(
        actor_id=user.id, entity_type="company", entity_id=company.id, action="updated",
        details={"changed_fields": changed_fields, "status_before": old_status, "status_after": company.status},
    ))
    try:
        db.flush()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_company_unp(exc):
            fail(409, "company_unp_exists", "This UNP is already assigned to a company")
        raise
    return {"company": _company_out(company, private=True)}


@router.get("/dealers", response_model=DealerDirectoryResponse)
def dealers(
    db: Annotated[Session, Depends(get_db)], page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
) -> dict:
    query = select(Company).where(Company.status == "approved").order_by(Company.name, Company.id)
    total = int(db.scalar(select(func.count(Company.id)).where(Company.status == "approved")) or 0)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_company_out(company, private=False) for company in rows],
        "pagination": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size},
    }


@router.get("/dealers/{slug}", response_model=DealerDetailResponse, response_model_exclude_unset=True)
def dealer_detail(
    slug: str,
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 25,
) -> dict:
    company = db.scalar(select(Company).where(Company.slug == slug, Company.status == "approved"))
    if company is None:
        fail(404, "not_found", "Company not found")
    conditions = (
        Listing.company_id == company.id,
        Listing.status == "active",
        User.status == "active",
        Company.status == "approved",
    )
    query = (
        select(Listing)
        .join(User, Listing.owner_id == User.id)
        .join(Company, Listing.company_id == Company.id)
        .where(*conditions)
        .order_by(Listing.created_at.desc(), Listing.id.desc())
    )
    total = int(db.scalar(
        select(func.count(Listing.id))
        .join(User, Listing.owner_id == User.id)
        .join(Company, Listing.company_id == Company.id)
        .where(*conditions)
    ) or 0)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    serialized_listings = serialize_listings(db, rows)
    publication_dates = listing_publication_dates(db, rows)
    for listing, item in zip(rows, serialized_listings, strict=True):
        item["published_at"] = publication_dates.get(listing.id)
    return {
        "company": _company_out(company, private=False),
        "listings": {
            "items": serialized_listings,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size,
            },
        },
    }
