import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, false, func, inspect as sa_inspect, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.config import get_settings
from app.contact_channels import validated_contact_channels
from app.listing_validation_policy import (
    MAXIMUM_LISTING_PHOTOS,
    is_listing_year_allowed,
    minimum_required_photos,
)
from app.listing_categories import CATEGORY_CODES, category_submission_errors, validate_category_details
from app.listing_subcategories import subcategory_details_condition, subcategory_field
from app.listing_schemas import ListingSearchFilters
from app.models import (
    BillingOrder,
    CatalogBodyVariant,
    CatalogBodyType,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Company,
    DealerTeamMember,
    ExchangeRate,
    Listing,
    ListingCategoryDetails,
    ListingPhoto,
    ListingPriceEvent,
    ListingPromotion,
    ListingStatusEvent,
    ListingViewEvent,
    LocationCity,
    LocationRegion,
    RateLimitBucket,
    SavedSearch,
    User,
    WorkerJob,
)
from app.runtime_settings import runtime_limit


def latest_listing_exchange_rate(db: Session) -> tuple[ExchangeRate | None, bool]:
    now = datetime.now(timezone.utc)
    rate = db.scalar(
        select(ExchangeRate)
        .where(ExchangeRate.currency == "USD", ExchangeRate.rate_date <= now.date().isoformat())
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )
    if rate is None or rate.fetched_at is None:
        return rate, False
    fetched = rate.fetched_at if rate.fetched_at.tzinfo else rate.fetched_at.replace(tzinfo=timezone.utc)
    return rate, fetched >= now - timedelta(hours=72)


def listing_display_price_expression(currency: str, rate: ExchangeRate):
    amount = Listing.price_amount
    if currency == "BYN":
        converted = amount * rate.official_rate / Decimal(rate.scale)
        return case((Listing.currency == "BYN", amount), (Listing.currency == "USD", converted), else_=None)
    converted = amount * Decimal(rate.scale) / rate.official_rate
    return case((Listing.currency == "USD", amount), (Listing.currency == "BYN", converted), else_=None)


# Upper bound for public and staff page numbers: deeper OFFSET scans get 422.
MAX_PAGE = 1000
LIKE_ESCAPE = "\\"
SEARCH_TEXT_MAX_LENGTH = 100
SEARCH_FIELD_MAX_LENGTH = 120


def contains_pattern(value: str, max_length: int) -> str:
    """Build an ILIKE substring pattern that treats user input literally.

    Use with ``escape=LIKE_ESCAPE`` so ``%``, ``_`` and ``\\`` in the input
    never act as wildcards.
    """
    term = value.strip()[:max_length]
    escaped = (
        term.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


def public_listings_query():
    return (
        select(Listing)
        .join(User, Listing.owner_id == User.id)
        .where(Listing.status == "active", User.status == "active")
        .outerjoin(Company, Listing.company_id == Company.id)
        .where(or_(Listing.company_id.is_(None), Company.status == "approved"))
    )


def build_public_listing_query(
    db: Session,
    filters: ListingSearchFilters | dict[str, Any],
    rate_info: tuple[ExchangeRate | None, bool] | None = None,
):
    """Build the public listing visibility/filter query shared by API and worker."""
    if not isinstance(filters, ListingSearchFilters):
        filters = ListingSearchFilters.model_validate(filters)
    if rate_info is None:
        rate_info = latest_listing_exchange_rate(db)
    latest_rate, rate_fresh = rate_info

    query = public_listings_query()
    query = query.where(Listing.category_code == filters.category_code)
    if filters.subcategory:
        field = subcategory_field(filters.category_code)
        if field:
            query = query.join(ListingCategoryDetails, ListingCategoryDetails.listing_id == Listing.id).where(
                subcategory_details_condition(filters.category_code, filters.subcategory)
            )
    if filters.q:
        term = contains_pattern(filters.q, SEARCH_TEXT_MAX_LENGTH)
        searched = (
            Listing.title, Listing.make_name_snapshot, Listing.model_name_snapshot,
            CatalogMake.name, cast(CatalogMake.aliases, String), CatalogModel.name, cast(CatalogModel.aliases, String),
            Listing.manual_city, Listing.district,
        )
        query = query.outerjoin(CatalogMake, Listing.make_id == CatalogMake.id).outerjoin(CatalogModel, Listing.model_id == CatalogModel.id).where(
            or_(*(column.ilike(term, escape=LIKE_ESCAPE) for column in searched))
        )
    # The multi-select matches selected models per make; a make without selected
    # models includes all its models. Unknown or mismatched models match nothing.
    if filters.make_ids is not None or filters.model_ids is not None:
        make_ids = [UUID(item) for item in filters.make_ids.split(",")] if filters.make_ids else ([filters.make_id] if filters.make_id else [])
        model_ids = [UUID(item) for item in filters.model_ids.split(",")] if filters.model_ids else ([filters.model_id] if filters.model_id else [])
        if model_ids:
            models = db.execute(select(CatalogModel.id, CatalogModel.make_id).where(CatalogModel.id.in_(model_ids))).all()
            if len(models) != len(model_ids) or any(model.make_id not in make_ids for model in models):
                query = query.where(false())
            else:
                by_make: dict[UUID, list[UUID]] = defaultdict(list)
                for model in models:
                    by_make[model.make_id].append(model.id)
                query = query.where(or_(*(
                    and_(Listing.make_id == make_id, Listing.model_id.in_(by_make[make_id]))
                    if by_make[make_id] else Listing.make_id == make_id
                    for make_id in make_ids
                )))
        elif make_ids:
            query = query.where(Listing.make_id.in_(make_ids))
    else:
        if filters.make_id is not None:
            query = query.where(Listing.make_id == filters.make_id)
        if filters.model_id is not None:
            query = query.where(Listing.model_id == filters.model_id)
    for field, value in (
        (Listing.generation_id, filters.generation_id), (Listing.body_variant_id, filters.body_variant_id),
        (Listing.modification_id, filters.modification_id), (Listing.region_id, filters.region_id),
        (Listing.city_id, filters.city_id), (Listing.fuel, filters.fuel),
        (Listing.transmission, filters.transmission), (Listing.drive, filters.drive),
        (Listing.condition, filters.condition), (Listing.color, filters.color),
        (Listing.customs_status, filters.customs_status),
        (Listing.technical_condition, filters.technical_condition),
        (Listing.body_condition, filters.body_condition), (Listing.exchange, filters.exchange),
        (Listing.bargaining, filters.bargaining), (Listing.credit, filters.credit),
        (Listing.leasing, filters.leasing), (Listing.damaged, filters.damaged),
        (Listing.parts_only, filters.parts_only),
        (Listing.in_transit, filters.in_transit),
    ):
        if value is not None:
            query = query.where(field == value)
    if filters.body_type:
        query = query.join(CatalogBodyType, Listing.body_type_id == CatalogBodyType.id).where(
            or_(cast(Listing.body_type_id, String) == filters.body_type, CatalogBodyType.slug == filters.body_type)
        )
    if filters.equipment:
        query = query.where(Listing.equipment.contains(filters.equipment))
    if filters.district:
        query = query.where(
            Listing.district.ilike(contains_pattern(filters.district, SEARCH_FIELD_MAX_LENGTH), escape=LIKE_ESCAPE)
        )
    if filters.call_hours:
        query = query.where(
            Listing.call_hours.ilike(contains_pattern(filters.call_hours, SEARCH_FIELD_MAX_LENGTH), escape=LIKE_ESCAPE)
        )
    if filters.has_vin is not None:
        has_vin_expression = Listing.vin.is_not(None) & (func.length(func.trim(Listing.vin)) > 0)
        query = query.where(has_vin_expression if filters.has_vin else ~has_vin_expression)
    if filters.has_photos is not None:
        ready_photo = select(ListingPhoto.id).where(
            ListingPhoto.listing_id == Listing.id,
            ListingPhoto.status == "ready",
        ).exists()
        query = query.where(ready_photo if filters.has_photos else ~ready_photo)
    if filters.seller_type == "private":
        query = query.where(Listing.company_id.is_(None))
    if filters.seller_type == "company":
        query = query.where(Listing.company_id.is_not(None))

    display_price = (
        listing_display_price_expression(filters.currency, latest_rate)
        if filters.currency and rate_fresh and latest_rate
        else Listing.price_amount
    )
    if filters.price_min is not None:
        query = query.where(display_price >= filters.price_min)
    if filters.price_max is not None:
        query = query.where(display_price <= filters.price_max)
    if filters.year_min is not None:
        query = query.where(Listing.year >= filters.year_min)
    if filters.year_max is not None:
        query = query.where(Listing.year <= filters.year_max)
    if filters.mileage_min is not None:
        query = query.where(Listing.mileage_km >= filters.mileage_min)
    if filters.mileage_max is not None:
        query = query.where(Listing.mileage_km <= filters.mileage_max)
    if filters.engine_volume_min is not None:
        query = query.where(Listing.engine_volume_l >= filters.engine_volume_min)
    if filters.engine_volume_max is not None:
        query = query.where(Listing.engine_volume_l <= filters.engine_volume_max)
    if filters.power_min is not None:
        query = query.where(Listing.power_hp >= filters.power_min)
    if filters.power_max is not None:
        query = query.where(Listing.power_hp <= filters.power_max)
    return query, display_price


# Filters compared with plain SQL equality; the listing attribute has the
# same name and Python type as the parsed filter value.
_EQUALITY_FILTER_FIELDS = (
    "generation_id", "body_variant_id", "modification_id", "region_id", "city_id",
    "fuel", "transmission", "drive", "condition", "color", "customs_status",
    "technical_condition", "body_condition", "exchange", "bargaining", "credit",
    "leasing", "damaged", "parts_only", "in_transit",
)
# (listing attribute, lower bound filter, upper bound filter) on integer columns.
_INTEGER_RANGE_FILTER_FIELDS = (
    ("year", "year_min", "year_max"),
    ("mileage_km", "mileage_min", "mileage_max"),
    ("power_hp", "power_min", "power_max"),
)


def _selected_make_ids(filters: ListingSearchFilters) -> list[UUID]:
    if filters.make_ids:
        return [UUID(item) for item in filters.make_ids.split(",")]
    return [filters.make_id] if filters.make_id else []


def _catalog_selection_may_match(filters: ListingSearchFilters, listing: Listing) -> bool:
    if filters.make_ids is not None or filters.model_ids is not None:
        # Every branch of the multi-select query restricts the listing make to
        # the selected makes; the model part is left to SQL.
        make_ids = _selected_make_ids(filters)
        return not make_ids or listing.make_id in make_ids
    if filters.make_id is not None and listing.make_id != filters.make_id:
        return False
    return filters.model_id is None or listing.model_id == filters.model_id


def listing_may_match_filters(filters: ListingSearchFilters, listing: Listing) -> bool:
    """Cheap in-memory necessary condition for build_public_listing_query.

    Returns False only when the SQL query cannot contain the listing: SQL
    equality and range predicates are false for NULL columns and so is the
    corresponding Python comparison. Filters without an exact in-memory
    equivalent (text search, catalog joins, prices, photos) are left to SQL.
    """
    if listing.category_code != filters.category_code:
        return False
    if not _catalog_selection_may_match(filters, listing):
        return False
    for field in _EQUALITY_FILTER_FIELDS:
        expected = getattr(filters, field)
        if expected is not None and getattr(listing, field) != expected:
            return False
    for attribute, lower_field, upper_field in _INTEGER_RANGE_FILTER_FIELDS:
        value = getattr(listing, attribute)
        lower, upper = getattr(filters, lower_field), getattr(filters, upper_field)
        if lower is not None and (value is None or value < lower):
            return False
        if upper is not None and (value is None or value > upper):
            return False
    if filters.seller_type == "private" and listing.company_id is not None:
        return False
    return not (filters.seller_type == "company" and listing.company_id is None)


def listing_in_public_catalog(db: Session, listing: Listing) -> bool:
    """Whether the listing passes the visibility part of every public search."""
    statement = public_listings_query().with_only_columns(Listing.id).where(Listing.id == listing.id).limit(1)
    return db.scalar(statement) is not None


def listing_matches_public_search(
    db: Session,
    filters: dict[str, Any],
    listing: Listing,
) -> bool:
    """Use the exact public query semantics to match one saved-search listing."""
    try:
        parsed_filters = ListingSearchFilters.model_validate(filters)
    except ValidationError:
        return False
    if not listing_may_match_filters(parsed_filters, listing):
        return False
    has_price_bounds = parsed_filters.price_min is not None or parsed_filters.price_max is not None
    if has_price_bounds and parsed_filters.currency is None:
        return False
    rate_info = latest_listing_exchange_rate(db) if has_price_bounds else (None, False)
    _rate, fresh = rate_info
    if has_price_bounds and not fresh:
        return False
    query, _ = build_public_listing_query(db, parsed_filters, rate_info)
    statement = query.with_only_columns(Listing.id).where(Listing.id == listing.id).order_by(None).limit(1)
    return db.scalar(statement) is not None


def fail(status_code: int, code: str, message: str, field_errors: dict[str, str] | None = None) -> None:
    raise HTTPException(status_code, detail={"code": code, "message": message, "field_errors": field_errors or {}})


def consume_rate_limit(db: Session, namespace: str, subject: str, limit: int, period: timedelta) -> None:
    now = datetime.now(timezone.utc)
    key = hashlib.sha256(f"{namespace}:{subject}".encode()).hexdigest()
    cutoff = now - period
    statement = pg_insert(RateLimitBucket).values(key_hash=key, window_started=now, count=1)
    statement = statement.on_conflict_do_update(
        index_elements=[RateLimitBucket.key_hash],
        set_={
            "window_started": case((RateLimitBucket.window_started < cutoff, now), else_=RateLimitBucket.window_started),
            "count": case((RateLimitBucket.window_started < cutoff, 1), else_=RateLimitBucket.count + 1),
        },
    ).returning(RateLimitBucket.count)
    count = db.scalar(statement)
    db.commit()
    if count is not None and count > limit:
        fail(429, "rate_limited", "Too many requests")


def require_owned_listing(
    db: Session,
    listing_id: UUID,
    user: User,
    *,
    lock: bool = False,
    foreign_public_active_forbidden: bool = False,
) -> Listing:
    # Read the listing's company scope without a lock first. Phone reveal locks
    # company before listing, so mutation routes must acquire them in that order.
    listing = db.scalar(select(Listing).where(Listing.id == listing_id))
    if listing is None:
        fail(404, "not_found", "Listing not found")
    observed_company_id = listing.company_id
    company = None
    if lock and observed_company_id is not None:
        company = db.scalar(
            select(Company)
            .where(Company.id == observed_company_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if lock:
        listing = db.scalar(
            select(Listing)
            .where(Listing.id == listing_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if listing is None:
            fail(404, "not_found", "Listing not found")
        if listing.company_id != observed_company_id:
            fail(409, "listing_changed_retry", "Listing ownership changed; reload before retrying")
    if listing.company_id is None:
        if listing.owner_id != user.id:
            if foreign_public_active_forbidden and listing_is_public(db, listing):
                fail(403, "listing_forbidden", "You cannot edit this listing")
            fail(404, "not_found", "Listing not found")
        return listing

    if not lock:
        company = db.scalar(select(Company).where(Company.id == listing.company_id))
    if company is None:
        fail(404, "not_found", "Listing not found")
    if company.status == "blocked":
        fail(403, "company_blocked", "Company access is blocked")
    if company.owner_id == user.id:
        return listing
    role = db.scalar(
        select(DealerTeamMember.role)
        .join(User, User.id == DealerTeamMember.user_id)
        .where(
            DealerTeamMember.company_id == company.id,
            DealerTeamMember.user_id == user.id,
            DealerTeamMember.status == "active",
            User.status == "active",
        )
    )
    if role is None:
        if foreign_public_active_forbidden and listing_is_public(db, listing):
            fail(403, "listing_forbidden", "You cannot edit this listing")
        fail(404, "not_found", "Listing not found")
    if role == "viewer":
        fail(403, "company_role_read_only", "A viewer cannot change company listings")
    return listing


def check_revision(resource: Any, expected_revision: int, resource_name: str = "Listing") -> None:
    if resource.revision != expected_revision:
        fail(409, "revision_conflict", f"{resource_name} changed; reload before retrying")


def enqueue_job(
    db: Session,
    kind: str,
    job_key: str,
    payload: dict,
    *,
    run_after: datetime | None = None,
    max_attempts: int = 5,
) -> WorkerJob:
    # Keep the historical contract that enqueueing flushes pending work.
    db.flush()
    existing = db.scalar(select(WorkerJob).where(WorkerJob.job_key == job_key))
    if existing:
        return existing
    values = {
        "job_key": job_key,
        "kind": kind,
        "payload": payload,
        "status": "queued",
        "attempts": 0,
        "max_attempts": max_attempts,
    }
    if run_after is not None:
        values["run_after"] = run_after
    # A concurrent transaction may insert the same key between the lookup and
    # this insert; the conflict then resolves to that row instead of a 500.
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else pg_insert
    statement = (
        insert(WorkerJob)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[WorkerJob.job_key])
        .returning(WorkerJob.id)
    )
    job_id = db.scalar(statement)
    if job_id is not None:
        return db.get_one(WorkerJob, job_id)
    return db.scalars(select(WorkerJob).where(WorkerJob.job_key == job_key)).one()


def enqueue_saved_search_match(db: Session, listing: Listing) -> WorkerJob | None:
    """Queue a matching pass only when an active search can receive it.

    Avoid creating a no-op job for every published listing while the pilot has
    no notification subscribers.  The existence check is deliberately inside
    the same transaction as the listing transition, so an enabled search is
    never missed for the publication event that created the job.
    """

    has_subscriber = db.scalar(
        select(SavedSearch.id)
        .join(User, User.id == SavedSearch.user_id)
        .where(
            SavedSearch.status == "active",
            SavedSearch.notifications_enabled.is_(True),
            SavedSearch.notification_channel.is_not(None),
            User.status == "active",
        )
        .limit(1)
    )
    if has_subscriber is None:
        return None

    return enqueue_job(
        db,
        "saved-search.match",
        f"saved-search.match:{listing.id}:{listing.revision}",
        {"listing_id": str(listing.id), "listing_revision": listing.revision},
    )


def lock_owner(db: Session, owner_id: UUID) -> User:
    owner = db.scalar(select(User).where(User.id == owner_id).with_for_update().execution_options(populate_existing=True))
    if owner is None or owner.status != "active":
        fail(403, "seller_unavailable", "Seller account is not active")
    return owner


def seller_company(db: Session, user: User, requested_type: str | None = None) -> Company | None:
    if requested_type == "company":
        company = db.scalar(select(Company).where(Company.owner_id == user.id))
        if company is None:
            matches = db.scalars(
                select(Company)
                .join(DealerTeamMember, DealerTeamMember.company_id == Company.id)
                .join(User, User.id == DealerTeamMember.user_id)
                .where(
                    DealerTeamMember.user_id == user.id,
                    DealerTeamMember.status == "active",
                    DealerTeamMember.role.in_({"admin", "seller"}),
                    User.status == "active",
                    Company.status != "blocked",
                )
                .order_by(Company.created_at, Company.id)
            ).all()
            if len(matches) > 1:
                fail(409, "company_scope_ambiguous", "Select a company scope before continuing")
            company = matches[0] if matches else None
        if company is None or company.status != "approved":
            fail(403, "company_not_approved", "An approved company is required")
        return company
    if requested_type == "private":
        return None
    return db.scalar(select(Company).where(Company.owner_id == user.id, Company.status == "approved"))


def active_quota_count(db: Session, owner_id: UUID, company_id: UUID | None) -> int:
    query = select(func.count(Listing.id)).where(Listing.status.in_(["active", "pending_review"]))
    if company_id is not None:
        query = query.where(Listing.company_id == company_id)
    else:
        query = query.where(Listing.owner_id == owner_id, Listing.company_id.is_(None))
    return int(db.scalar(query) or 0)


def quota_limit(company: Company | None, db: Session | None = None) -> int:
    key = "company_listing_quota" if company else "private_listing_quota"
    base_limit = runtime_limit(db, key, fallback=getattr(get_settings(), key))
    if company is None or db is None:
        return base_limit

    now = datetime.now(timezone.utc)
    package_limit = db.scalar(
        select(func.max(ListingPromotion.listing_quota))
        .join(BillingOrder, BillingOrder.id == ListingPromotion.order_id)
        .where(
            ListingPromotion.company_id == company.id,
            ListingPromotion.service_code == "dealer_package",
            ListingPromotion.status == "active",
            ListingPromotion.starts_at <= now,
            ListingPromotion.ends_at > now,
            ListingPromotion.listing_quota.is_not(None),
            BillingOrder.status == "paid",
        )
    )
    return max(base_limit, int(package_limit)) if package_limit is not None else base_limit


def validate_listing_for_submit(db: Session, listing: Listing) -> None:
    errors: dict[str, str] = {}
    policy_settings = get_settings()
    category_code = getattr(listing, "category_code", None) or "cars"
    if category_code not in CATEGORY_CODES:
        errors["category_code"] = "Choose a supported listing category"
    elif category_code in {"cars", "trucks", "buses", "motorcycles", "special_equipment", "agricultural_equipment", "trailers", "watercraft"}:
        if listing.make_id is None and not listing.manual_make:
            errors["make_id"] = "Choose a catalog make or enter a manual make"
        if listing.model_id is None and not listing.manual_model:
            errors["model_id"] = "Choose a catalog model or enter a manual model"
        if not is_listing_year_allowed(listing.year, listing, settings=policy_settings):
            errors["year"] = "Year is outside the allowed range"
    if category_code == "cars":
        if listing.mileage_km is None or listing.mileage_km < 0:
            errors["mileage_km"] = "Mileage must be zero or greater"
    category_details = getattr(listing, "category_details", None)
    if category_code not in CATEGORY_CODES:
        pass
    elif category_details is None:
        if category_code != "cars":
            errors["category_details"] = "Add category-specific characteristics"
    else:
        if category_details.category_code != category_code:
            errors["category_details"] = "Category details do not match the listing category"
        else:
            try:
                details = validate_category_details(category_code, category_details.details)
            except ValueError:
                errors["category_details"] = "Category details are invalid"
            else:
                errors.update(category_submission_errors(category_code, details))
    if listing.price_amount is None or listing.price_amount <= Decimal(0):
        errors["price_amount"] = "Price must be greater than zero"
    if not listing.description.strip():
        errors["description"] = "Description is required"
    if category_code == "cars" and not listing.fuel:
        errors["fuel"] = "Fuel type is required"
    if category_code == "cars" and not listing.transmission:
        errors["transmission"] = "Transmission is required"
    if category_code == "cars" and not listing.drive:
        errors["drive"] = "Drive type is required"
    if not listing.condition:
        errors["condition"] = "Vehicle condition is required"
    if listing.region_id is None:
        errors["region_id"] = "Choose a region"
    if listing.city_id is not None and listing.manual_city:
        errors["city_id"] = "Choose a catalog city or enter a manual place, not both"
        errors["manual_city"] = "Choose a catalog city or enter a manual place, not both"
    elif listing.city_id is None and not listing.manual_city:
        errors["city_id"] = "Choose a catalog city or enter a manual place"
    if category_code == "cars" and listing.fuel == "electric" and listing.engine_volume_l and listing.engine_volume_l > 0:
        errors["engine_volume_l"] = "Electric vehicles cannot have a combustion engine volume"
    if category_code == "cars" and listing.generation_id and listing.year is not None:
        generation = db.get(CatalogGeneration, listing.generation_id)
        if generation is not None and (
            (generation.year_from is not None and listing.year < generation.year_from)
            or (generation.year_to is not None and listing.year > generation.year_to)
        ):
            errors["year"] = "Year is outside the selected generation"
            errors["generation_id"] = "Choose a matching generation or remove it"
    photos = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id).order_by(ListingPhoto.position)).all()
    minimum_photos = minimum_required_photos(listing, settings=policy_settings)
    ready_photo_count = sum(photo.status == "ready" for photo in photos)
    if ready_photo_count < minimum_photos:
        errors["photos"] = f"Add at least {minimum_photos} processed photo(s)"
    if len(photos) > MAXIMUM_LISTING_PHOTOS:
        errors["photos"] = "A listing can have at most 30 photos"
    if not listing.title.strip():
        errors["title"] = "Title is required"
    if errors:
        fail(422, "validation_error", "Listing is incomplete", errors)


def catalog_item(
    item: Any,
    *,
    make_id: UUID | None = None,
    model_id: UUID | None = None,
    generation_id: UUID | None = None,
) -> dict | None:
    if item is None:
        return None
    data: dict[str, Any] = {
        "id": str(item.id), "slug": item.slug, "name": item.name,
        "aliases": list(getattr(item, "aliases", []) or []),
    }
    if make_id is not None:
        data["make_id"] = str(make_id)
    if model_id is not None:
        data["model_id"] = str(model_id)
    if generation_id is not None:
        data["generation_id"] = str(generation_id)
    if isinstance(item, CatalogGeneration):
        data.update(year_from=item.year_from, year_to=item.year_to)
    return data


def catalog_modification_item(item: CatalogModification, *, include_aliases: bool = True) -> dict:
    data = {"id": str(item.id), "slug": item.slug, "name": item.name}
    if include_aliases:
        data["aliases"] = []
    if item.source_name != "Drom" or not isinstance(item.source_metadata, dict):
        return data

    source = item.source_metadata

    def raw_value(key: str) -> str | None:
        value = source.get(key)
        return value if isinstance(value, str) and value else None

    def numeric_value(key: str, *, integer: bool) -> int | float | None:
        value = raw_value(key)
        if value is None:
            return None
        try:
            number = Decimal(value.strip())
        except InvalidOperation:
            return None
        if not number.is_finite():
            return None
        if integer:
            return int(number) if number == number.to_integral_value() else None
        parsed = float(number)
        return parsed if math.isfinite(parsed) else None

    data["source"] = {
        "name": "Drom",
        "id": raw_value("source_id"),
        "url": raw_value("source_url"),
    }
    data["specs"] = {
        "engine_code": raw_value("engine_code"),
        "frame_code": raw_value("frame_code"),
        "engine_l": numeric_value("engine_l", integer=False),
        "power_hp": numeric_value("power_hp", integer=True),
        "fuel": raw_value("fuel"),
        "transmission": raw_value("transmission"),
        "drive": raw_value("drive"),
        "production_period_raw": raw_value("production_period"),
        "summary_raw": raw_value("summary"),
    }
    return data


def serialize_listing(
    db: Session,
    listing: Listing,
    *,
    public: bool = True,
    include_contact: bool = False,
) -> dict:
    from app.listing_provenance import listing_provenance
    origin = listing_provenance(db, [listing]).get(listing.id)
    badges = _active_promotion_badges(db, [listing.id]).get(listing.id, [])
    item = _serialize_listing(
        db,
        listing,
        public=public,
        include_modification=True,
        include_contact=include_contact,
        promotion_badges=badges,
        origin=origin,
    )
    _attach_view_counts(db, [listing], [item], public=public)
    return item


def table_available(db: Session, table_name: str) -> bool:
    """Whether an optional table exists in this database.

    PostgreSQL schemas are managed by migrations, so every mapped table exists
    there and the catalog lookup (one extra query per request) is skipped.
    Partial SQLite test fixtures create only some tables, and session-like
    objects without a bind (as _active_promotion_badges also allows) have none.
    """
    if not hasattr(db, "get_bind"):
        return False
    bind = db.get_bind()
    return bind.dialect.name == "postgresql" or sa_inspect(bind).has_table(table_name)


def _attach_view_counts(db: Session, listings: list[Listing], items: list[dict], *, public: bool) -> None:
    if not public or not listings or not table_available(db, "listing_view_events"):
        return
    counts = dict(db.execute(
        select(ListingViewEvent.listing_id, func.count(ListingViewEvent.id))
        .where(ListingViewEvent.listing_id.in_([listing.id for listing in listings]))
        .group_by(ListingViewEvent.listing_id)
    ).all())
    for listing, item in zip(listings, items, strict=True):
        item["view_count"] = counts.get(listing.id, 0)


# Search badges and the price_drop sort only consider discounts this recent.
PRICE_DROP_BADGE_WINDOW = timedelta(days=30)


def recent_price_drops_subquery(listing_ids: list[UUID] | None = None):
    """Latest price event per listing when it is a same-currency drop inside the badge window.

    Events are filtered to the window before ranking: an event inside the window
    can only be the latest one when no newer event exists, so a later price rise
    or removal still hides an earlier discount.
    """
    cutoff = datetime.now(timezone.utc) - PRICE_DROP_BADGE_WINDOW
    ranked = select(
        ListingPriceEvent.listing_id,
        ListingPriceEvent.event_type,
        ListingPriceEvent.price_amount,
        ListingPriceEvent.currency,
        ListingPriceEvent.previous_price_amount,
        ListingPriceEvent.previous_currency,
        ListingPriceEvent.created_at,
        func.row_number().over(
            partition_by=ListingPriceEvent.listing_id,
            order_by=(ListingPriceEvent.revision.desc(), ListingPriceEvent.id.desc()),
        ).label("position"),
    ).where(ListingPriceEvent.created_at >= cutoff)
    if listing_ids is not None:
        ranked = ranked.where(ListingPriceEvent.listing_id.in_(listing_ids))
    ranked = ranked.subquery()
    return select(
        ranked.c.listing_id,
        ranked.c.price_amount,
        ranked.c.previous_price_amount,
        ranked.c.currency,
        ranked.c.created_at.label("changed_at"),
    ).where(
        ranked.c.position == 1,
        ranked.c.event_type == "changed",
        ranked.c.currency == ranked.c.previous_currency,
        ranked.c.price_amount < ranked.c.previous_price_amount,
    ).subquery()


def attach_last_price_drops(db: Session, listings: list[Listing], items: list[dict]) -> None:
    """Set ``last_price_drop`` for a listing page with one query."""
    if not listings:
        return
    if not table_available(db, "listing_price_events"):
        for item in items:
            item["last_price_drop"] = None
        return
    drops = recent_price_drops_subquery([listing.id for listing in listings])
    found = {row.listing_id: row for row in db.execute(select(drops)).all()}
    for listing, item in zip(listings, items, strict=True):
        row = found.get(listing.id)
        item["last_price_drop"] = None if row is None else {
            "amount": str(row.price_amount),
            "previous_amount": str(row.previous_price_amount),
            "currency": row.currency,
            "changed_at": row.changed_at,
        }


def listing_publication_dates(db: Session, listings: list[Listing]) -> dict[UUID, datetime]:
    """Return first-ever transition to active for a listing page in one query."""
    listing_ids = [listing.id for listing in listings]
    if not listing_ids:
        return {}
    rows = db.execute(
        select(ListingStatusEvent.listing_id, func.min(ListingStatusEvent.created_at))
        .where(
            ListingStatusEvent.listing_id.in_(listing_ids),
            ListingStatusEvent.to_status == "active",
        )
        .group_by(ListingStatusEvent.listing_id)
    ).all()
    return {listing_id: published_at for listing_id, published_at in rows if published_at is not None}


def serialize_listings(
    db: Session,
    listings: list[Listing],
    *,
    public: bool = True,
    include_contact: bool = False,
    include_modification: bool = False,
) -> list[dict]:
    from app.listing_provenance import listing_provenance
    origins = listing_provenance(db, listings)
    badges_by_listing = _active_promotion_badges(db, [listing.id for listing in listings])
    if len(listings) < 2:
        items = [
            _serialize_listing(
                db,
                listing,
                public=public,
                include_modification=include_modification,
                include_contact=include_contact,
                promotion_badges=badges_by_listing.get(listing.id, []),
                origin=origins.get(listing.id),
            )
            for listing in listings
        ]
        _attach_view_counts(db, listings, items, public=public)
        return items

    listing_ids = {listing.id for listing in listings}
    references = {
        CatalogMake: {listing.make_id for listing in listings if listing.make_id},
        CatalogModel: {listing.model_id for listing in listings if listing.model_id},
        CatalogGeneration: {listing.generation_id for listing in listings if listing.generation_id},
        CatalogBodyType: {listing.body_type_id for listing in listings if listing.body_type_id},
        CatalogBodyVariant: {listing.body_variant_id for listing in listings if listing.body_variant_id},
        LocationRegion: {listing.region_id for listing in listings if listing.region_id},
        LocationCity: {listing.city_id for listing in listings if listing.city_id},
        Company: {listing.company_id for listing in listings if listing.company_id},
        User: {listing.owner_id for listing in listings},
    }
    if include_modification:
        references[CatalogModification] = {listing.modification_id for listing in listings if listing.modification_id}
    records = {
        model: {
            row.id: row
            for row in db.scalars(select(model).where(model.id.in_(ids))).all()
        }
        for model, ids in references.items()
        if ids
    }

    photos_by_listing: dict[UUID, list[ListingPhoto]] = defaultdict(list)
    photos = db.scalars(
        select(ListingPhoto)
        .where(ListingPhoto.listing_id.in_(listing_ids))
        .order_by(ListingPhoto.listing_id, ListingPhoto.position)
    ).all()
    for photo in photos:
        photos_by_listing[photo.listing_id].append(photo)

    items = [
        _serialize_listing(
            db,
            listing,
            public=public,
            records=records,
            photos_by_listing=photos_by_listing,
            include_modification=include_modification,
            include_contact=include_contact,
            promotion_badges=badges_by_listing.get(listing.id, []),
            origin=origins.get(listing.id),
        )
        for listing in listings
    ]
    _attach_view_counts(db, listings, items, public=public)
    return items


def _active_promotion_badges(db: Session, listing_ids: list[UUID]) -> dict[UUID, list[str]]:
    if not listing_ids:
        return {}
    active_codes = {"bump", "highlight", "top"}
    if hasattr(db, "get_bind"):
        try:
            bind = db.get_bind()
            if bind.dialect.name != "postgresql" and not sa_inspect(bind).has_table("listing_promotions"):
                return {}
        except (AttributeError, OperationalError):
            return {}
    try:
        rows = db.execute(
            select(ListingPromotion.listing_id, ListingPromotion.service_code)
            .where(
                ListingPromotion.listing_id.in_(listing_ids),
                ListingPromotion.service_code.in_(active_codes),
                ListingPromotion.status == "active",
                ListingPromotion.starts_at <= func.now(),
                ListingPromotion.ends_at > func.now(),
            )
        ).all()
    except AttributeError:
        # Small serialization unit stubs may only implement ``get`` and
        # ``scalars``; promotion data is optional for those contracts.
        return {}
    except OperationalError as exc:
        # Listing serialization is also used by SQLite catalog-only fixtures
        # that intentionally omit billing tables. A real billing failure must
        # still propagate; only the absent optional table is ignored.
        if hasattr(db, "get_bind") and db.get_bind().dialect.name == "postgresql":
            raise
        message = str(exc).casefold()
        if "no such table" not in message and "does not exist" not in message:
            raise
        return {}
    found: dict[UUID, set[str]] = defaultdict(set)
    for listing_id, service_code in rows:
        found[listing_id].add(service_code)
    order = ("top", "bump", "highlight")
    return {listing_id: [code for code in order if code in codes] for listing_id, codes in found.items()}


def _serialize_listing(
    db: Session,
    listing: Listing,
    *,
    public: bool,
    records: dict[type, dict[UUID, Any]] | None = None,
    photos_by_listing: dict[UUID, list[ListingPhoto]] | None = None,
    include_modification: bool = False,
    include_contact: bool = False,
    promotion_badges: list[str] | None = None,
    origin: tuple | None = None,
) -> dict:
    def get_record(model, identity):
        if identity is None:
            return None
        if records is None:
            return db.get(model, identity)
        return records.get(model, {}).get(identity)

    make = get_record(CatalogMake, listing.make_id)
    model = get_record(CatalogModel, listing.model_id)
    generation = get_record(CatalogGeneration, listing.generation_id)
    body_type = get_record(CatalogBodyType, listing.body_type_id)
    body_variant = get_record(CatalogBodyVariant, listing.body_variant_id)
    if body_variant is not None and body_variant.generation_id != listing.generation_id:
        body_variant = None
    region = get_record(LocationRegion, listing.region_id)
    city = get_record(LocationCity, listing.city_id)
    photos = (
        db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id).order_by(ListingPhoto.position)).all()
        if photos_by_listing is None
        else photos_by_listing.get(listing.id, [])
    )
    company = get_record(Company, listing.company_id)
    user = get_record(User, listing.owner_id)
    seller = {"type": "company", "id": str(company.id), "name": company.name, "slug": company.slug} if company else {
        "type": "private", "id": str(user.id) if user else "", "name": user.display_name if user else "",
    }
    # Import audit proves origin, not verified seller ownership or a chat recipient.
    unconfirmed_import = origin is not None
    if public and unconfirmed_import:
        seller = {"type": "private", "id": "", "name": ""}
    visible_photos = [photo for photo in photos if not public or photo.status == "ready"]
    photo_urls = [f"/api/v1/photos/{photo.id}/768" for photo in visible_photos if photo.status == "ready"]
    title = listing.title.strip() or " ".join(filter(None, [listing.make_name_snapshot, listing.model_name_snapshot]))
    created_at = listing.created_at or datetime.now(timezone.utc)
    updated_at = listing.updated_at or created_at
    result = {
        "id": str(listing.id), "slug": listing.slug, "title": title,
        "status": listing.status, "revision": listing.revision,
        "category_code": getattr(listing, "category_code", "cars"),
        "category_details": dict(getattr(getattr(listing, "category_details", None), "details", None) or {}),
        "make": catalog_item(make) or (CatalogItemFallback(listing.make_name_snapshot, listing.manual_make)),
        "model": catalog_item(model, make_id=listing.make_id) or CatalogItemFallback(listing.model_name_snapshot, listing.manual_model, listing.make_id),
        "generation": catalog_item(generation, make_id=listing.make_id, model_id=listing.model_id),
        "year": listing.year, "mileage_km": listing.mileage_km, "fuel": listing.fuel,
        "transmission": listing.transmission, "drive": listing.drive,
        "body_type": body_type.name if body_type else None,
        "body_variant_id": str(body_variant.id) if body_variant else None,
        "body_variant": catalog_item(body_variant, generation_id=listing.generation_id) if body_variant else None,
        "price": None if listing.price_amount is None else {
            "amount": str(listing.price_amount), "currency": listing.currency,
            "display_byn": None, "rate_date": None, "market_comparison": None,
        },
        "region": catalog_item(region), "city": catalog_item(city), "manual_city": listing.manual_city, "seller": seller,
        "created_at": created_at.isoformat(), "updated_at": updated_at.isoformat(),
        "published_at": None,
        "damaged": listing.damaged, "parts_only": listing.parts_only, "in_transit": listing.in_transit,
        "description": listing.description, "engine_volume_l": str(listing.engine_volume_l) if listing.engine_volume_l is not None else None,
        "power_hp": listing.power_hp, "condition": listing.condition,
        "color": listing.color,
        "customs_status": listing.customs_status,
        "technical_condition": listing.technical_condition,
        "body_condition": listing.body_condition,
        "exchange": listing.exchange,
        "bargaining": listing.bargaining,
        "credit": listing.credit,
        "leasing": listing.leasing,
        "equipment": list(listing.equipment or []),
        "district": listing.district,
        "call_hours": listing.call_hours,
        "has_phone": bool(listing.contact_phone and listing.contact_phone.strip()),
        "has_external_contacts": bool(validated_contact_channels(listing.telegram_contact_url, listing.viber_contact_url)),
        "provenance": origin[1] if origin else None,
        "is_imported": unconfirmed_import,
        "can_chat": not unconfirmed_import,
        "promotion_badges": list(promotion_badges or []),
        "photo_badges": list(listing.photo_badges or []),
        "vin": None if public else listing.vin, "moderation_reason": None if public else listing.moderation_reason,
        "photo_urls": photo_urls,
        "photos": [
            {"id": str(photo.id), "url": f"/api/v1/photos/{photo.id}/768" if photo.status == "ready" else None,
             "status": photo.status, "position": photo.position, "is_cover": photo.is_cover}
            for photo in visible_photos
        ],
    }
    if public:
        result.pop("vin", None)
        result.pop("moderation_reason", None)
    if include_modification:
        modification = get_record(CatalogModification, listing.modification_id)
        result["modification"] = catalog_modification_item(modification, include_aliases=False) if modification else None
    if include_contact:
        result["contact_phone"] = listing.contact_phone
        result["telegram_contact_url"] = listing.telegram_contact_url
        result["viber_contact_url"] = listing.viber_contact_url
    return result


def CatalogItemFallback(name: str | None, manual_name: str | None, parent_id: UUID | None = None) -> dict | None:
    value = manual_name or name
    if not value:
        return None
    slug = "manual-" + hashlib.sha1(value.lower().encode()).hexdigest()[:12]
    result = {"id": str(parent_id or UUID(int=0)), "slug": slug, "name": value, "aliases": []}
    return result


def listing_is_public(db: Session, listing: Listing) -> bool:
    if listing.status not in {"active", "sold"}:
        return False
    owner = db.get(User, listing.owner_id)
    if owner is None or owner.status != "active":
        return False
    if listing.company_id:
        company = db.get(Company, listing.company_id)
        if company is None or company.status != "approved":
            return False
    if listing.status == "sold" and listing.sold_at:
        sold_at = listing.sold_at
        if sold_at.tzinfo is None:
            sold_at = sold_at.replace(tzinfo=timezone.utc)
        if sold_at < datetime.now(timezone.utc) - timedelta(days=30):
            return False
    return True
