import hmac
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import String, case, cast, func, inspect as sa_inspect, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_optional_user,
    get_session_record,
    require_csrf,
)
from app.config import get_settings
from app.db import get_db
from app.dealer_services import company_ids_for_user, company_role_for
from app.listing_schemas import (
    FavoriteToggleOut,
    ListingDetailOut,
    ListingAnalyticsOut,
    ListingFavoritesOut,
    ListingOwnerDetailOut,
    ListingOwnerSearchOut,
    ListingReportOut,
    ListingRelatedOut,
    ListingSearchOut,
    PhoneRevealOut,
    ListingPublicCapabilitiesOut,
)
from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Company,
    Conversation,
    ContactReveal,
    ExchangeRate,
    Favorite,
    IdempotencyRecord,
    Listing,
    ListingPhoto,
    ListingPromotion,
    ListingStatusEvent,
    ListingViewEvent,
    LocationCity,
    LocationRegion,
    Report,
    User,
    UserSession,
)
from app.schemas import (
    ApiErrorOut,
    ListingForm,
    ListingPatch,
    ReportInput,
    RevisionInput,
)
from app.listing_options import LISTING_OPTIONS, ListingOptionsOut
from app.listing_validation_policy import listing_validation_policy
from app.validation_policy_schemas import ListingValidationPolicyOut
from app.listing_change_audit import build_listing_edit_event, snapshot_listing_fields
from app.security import client_ip, new_secret, secret_hash
from app.services import (
    active_quota_count,
    check_revision,
    consume_rate_limit,
    enqueue_saved_search_match,
    fail,
    listing_is_public,
    lock_owner,
    quota_limit,
    require_owned_listing,
    seller_company,
    serialize_listing,
    serialize_listings,
    validate_listing_for_submit,
)

router = APIRouter(prefix="/api/v1", tags=["listings"])


@router.get("/listing-validation-policy", response_model=ListingValidationPolicyOut)
def public_listing_validation_policy(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return listing_validation_policy()


GUEST_PHONE_REVEAL_IP_LIMIT = 30
GUEST_PHONE_REVEAL_DEVICE_LIMIT = 30
GUEST_PHONE_REVEAL_LISTING_LIMIT = 300
GUEST_CONTACT_PROOF_COOKIE = "avtorinok_guest_contact_proof"
GUEST_CONTACT_DEVICE_COOKIE = "avtorinok_guest_contact_device"
GUEST_CONTACT_PROOF_TTL_SECONDS = 15 * 60
GUEST_CONTACT_DEVICE_TTL_SECONDS = 24 * 60 * 60
EDITABLE_FIELDS = {
    "make_id", "model_id", "generation_id", "body_type_id", "body_variant_id", "modification_id",
    "manual_make", "manual_model", "title", "year", "mileage_km", "fuel", "transmission", "drive",
    "condition", "damaged", "parts_only", "engine_volume_l", "power_hp", "description", "vin",
    "region_id", "city_id", "manual_city", "contact_phone", "color", "customs_status",
    "technical_condition", "body_condition", "exchange", "bargaining", "credit", "leasing",
    "equipment", "district", "call_hours",
}


def _guest_contact_cookie_value(purpose: str, nonce: str, ttl_seconds: int) -> str:
    expires_at = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
    payload = f"guest-contact:{purpose}:{nonce}:{expires_at}"
    return f"{nonce}.{expires_at}.{secret_hash(payload)}"


def _guest_contact_cookie_nonce(value: str | None, purpose: str, ttl_seconds: int) -> str | None:
    if not value:
        return None
    try:
        nonce, raw_expires_at, signature = value.rsplit(".", 2)
        expires_at = int(raw_expires_at)
    except (ValueError, TypeError):
        return None
    now = int(datetime.now(timezone.utc).timestamp())
    if not nonce or expires_at <= now or expires_at > now + ttl_seconds + 5:
        return None
    expected = secret_hash(f"guest-contact:{purpose}:{nonce}:{expires_at}")
    return nonce if hmac.compare_digest(signature, expected) else None


def _require_guest_contact_proof(request: Request) -> str:
    proof_cookie = request.cookies.get(GUEST_CONTACT_PROOF_COOKIE)
    proof_header = request.headers.get("x-guest-contact-token")
    device_cookie = request.cookies.get(GUEST_CONTACT_DEVICE_COOKIE)
    proof_nonce = _guest_contact_cookie_nonce(
        proof_cookie, "proof", GUEST_CONTACT_PROOF_TTL_SECONDS
    )
    device_nonce = _guest_contact_cookie_nonce(
        device_cookie, "device", GUEST_CONTACT_DEVICE_TTL_SECONDS
    )
    if (
        not proof_cookie
        or not proof_header
        or len(proof_header) > 256
        or not hmac.compare_digest(proof_cookie, proof_header)
        or proof_nonce is None
        or device_nonce is None
    ):
        fail(403, "guest_contact_proof_required", "Refresh the page to request this contact")
    return device_nonce


def _lock_public_active_listing(
    db: Session,
    listing_id: UUID,
    owner_id: UUID,
    company_id: UUID | None,
    *,
    actor_id: UUID | None = None,
    session_token_hash: str | None = None,
) -> Listing:
    # Lock all user rows in a stable order, then session -> company -> listing.
    user_ids = {owner_id}
    if actor_id is not None:
        user_ids.add(actor_id)
    locked_users = db.scalars(
        select(User)
        .where(User.id.in_(user_ids))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    users_by_id = {user.id: user for user in locked_users}
    owner = users_by_id.get(owner_id)
    if actor_id is not None:
        actor = users_by_id.get(actor_id)
        if actor is None or actor.status != "active" or not session_token_hash:
            fail(401, "invalid_session", "Sign in required")
        session = db.scalar(
            select(UserSession)
            .where(UserSession.token_hash == session_token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        expires_at = session.expires_at if session is not None else None
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if (
            session is None
            or session.user_id != actor_id
            or session.revoked_at is not None
            or expires_at is None
            or expires_at <= datetime.now(timezone.utc)
        ):
            fail(401, "invalid_session", "Sign in required")
    company = None
    if company_id is not None:
        company = db.scalar(
            select(Company)
            .where(Company.id == company_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    listing = db.scalar(
        select(Listing)
        .where(Listing.id == listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        owner is None
        or owner.status != "active"
        or listing is None
        or listing.status != "active"
        or listing.owner_id != owner_id
        or listing.company_id != company_id
        or (company_id is not None and (company is None or company.status != "approved"))
    ):
        fail(404, "not_found", "Listing not found")
    return listing


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:180] or uuid4().hex[:12]


def _apply_fields(db: Session, listing: Listing, values: dict, user: User, *, creating: bool) -> None:
    seller_type = values.pop("seller_type", None)
    price = values.pop("price", None)
    if price is not None:
        listing.price_amount = price["amount"]
        listing.currency = price["currency"]
    if creating or seller_type is not None:
        company = seller_company(db, user, seller_type or "private")
        listing.company_id = company.id if company else None
    for field in EDITABLE_FIELDS:
        if field in values:
            setattr(listing, field, values[field])

    make = db.get(CatalogMake, listing.make_id) if listing.make_id else None
    model = db.get(CatalogModel, listing.model_id) if listing.model_id else None
    if listing.make_id and make is None:
        fail(422, "invalid_catalog_reference", "Unknown make", {"make_id": "Unknown make"})
    if listing.model_id and model is None:
        fail(422, "invalid_catalog_reference", "Unknown model", {"model_id": "Unknown model"})
    if model and (make is None or model.make_id != make.id):
        fail(422, "invalid_catalog_reference", "Model does not belong to selected make", {"model_id": "Model belongs to another make"})
    generation = db.get(CatalogGeneration, listing.generation_id) if listing.generation_id else None
    if listing.generation_id and (generation is None or generation.model_id != listing.model_id):
        fail(422, "invalid_catalog_reference", "Generation does not belong to selected model", {"generation_id": "Generation belongs to another model"})
    body_variant = db.get(CatalogBodyVariant, listing.body_variant_id) if listing.body_variant_id else None
    if listing.body_variant_id and (body_variant is None or body_variant.generation_id != listing.generation_id):
        fail(422, "invalid_catalog_reference", "Body variant does not belong to selected generation", {"body_variant_id": "Invalid body variant"})
    modification = db.get(CatalogModification, listing.modification_id) if listing.modification_id else None
    if listing.modification_id and (modification is None or modification.generation_id != listing.generation_id):
        fail(422, "invalid_catalog_reference", "Modification does not belong to selected generation", {"modification_id": "Invalid modification"})
    if listing.body_type_id and db.get(CatalogBodyType, listing.body_type_id) is None:
        fail(422, "invalid_catalog_reference", "Unknown body type", {"body_type_id": "Unknown body type"})
    if listing.city_id is not None and listing.manual_city:
        fail(422, "invalid_location", "Choose a catalog city or enter a manual place, not both", {
            "city_id": "Cannot be set together with manual_city",
            "manual_city": "Cannot be set together with city_id",
        })
    if listing.city_id:
        city = db.get(LocationCity, listing.city_id)
        if city is None or city.region_id != listing.region_id:
            fail(422, "invalid_location", "City does not belong to selected region", {"city_id": "City belongs to another region"})
    if listing.region_id and db.get(LocationRegion, listing.region_id) is None:
        fail(422, "invalid_location", "Unknown region", {"region_id": "Unknown region"})

    listing.make_name_snapshot = make.name if make else listing.manual_make
    listing.model_name_snapshot = model.name if model else listing.manual_model
    listing.generation_name_snapshot = generation.name if generation else None
    if not listing.title or not listing.title.strip():
        listing.title = " ".join(filter(None, [listing.make_name_snapshot, listing.model_name_snapshot, str(listing.year) if listing.year else None]))


def _record_transition(db: Session, listing: Listing, actor: User, target: str, reason: str | None = None) -> None:
    old = listing.status
    listing.status = target
    db.add(ListingStatusEvent(
        listing_id=listing.id, actor_id=actor.id, from_status=old, to_status=target,
        revision=listing.revision, reason=reason,
    ))


def _latest_exchange_rate(db: Session) -> tuple[ExchangeRate | None, bool]:
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


def _convert_price(amount: Decimal, source: str | None, target: str, rate: ExchangeRate | None, *, fresh: bool) -> Decimal | None:
    if source == target:
        return amount
    if not fresh or rate is None:
        return None
    if source == "USD" and target == "BYN":
        return amount * rate.official_rate / Decimal(rate.scale)
    if source == "BYN" and target == "USD":
        return amount * Decimal(rate.scale) / rate.official_rate
    return None


def _display_price_expression(currency: str, rate: ExchangeRate):
    amount = Listing.price_amount
    if currency == "BYN":
        converted = amount * rate.official_rate / Decimal(rate.scale)
        return case((Listing.currency == "BYN", amount), (Listing.currency == "USD", converted), else_=None)
    converted = amount * Decimal(rate.scale) / rate.official_rate
    return case((Listing.currency == "USD", amount), (Listing.currency == "BYN", converted), else_=None)


def _listed(
    db: Session,
    listings: list[Listing],
    *,
    public: bool = True,
    include_contact: bool = False,
    rate_info: tuple[ExchangeRate | None, bool] | None = None,
    display_currency: str | None = None,
    include_modification: bool = False,
) -> list[dict]:
    if rate_info is None:
        rate_info = _latest_exchange_rate(db)
    rate, fresh = rate_info
    result = []
    items = (
        [serialize_listing(db, listing, public=public, include_contact=include_contact) for listing in listings]
        if include_modification
        else serialize_listings(db, listings, public=public, include_contact=include_contact)
    )
    for listing, item in zip(listings, items, strict=True):
        if item["price"]:
            amount = Decimal(str(listing.price_amount))
            if fresh and rate:
                byn = _convert_price(amount, listing.currency, "BYN", rate, fresh=True)
                if byn is not None:
                    item["price"]["display_byn"] = str(byn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    item["price"]["rate_date"] = rate.rate_date
            if display_currency and fresh:
                display_amount = _convert_price(amount, listing.currency, display_currency, rate, fresh=True)
                if display_amount is not None:
                    item["price"]["display_amount"] = str(display_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                    item["price"]["display_currency"] = display_currency
        result.append(item)
    return result


def _active_query():
    return select(Listing).join(User, Listing.owner_id == User.id).where(Listing.status == "active", User.status == "active").outerjoin(Company, Listing.company_id == Company.id).where(or_(Listing.company_id.is_(None), Company.status == "approved"))


@router.get("/listing-options", response_model=ListingOptionsOut)
def listing_options() -> dict:
    return LISTING_OPTIONS


@router.get("/listings", response_model=ListingSearchOut, response_model_exclude_unset=True)
def search_listings(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    make_id: UUID | None = None,
    model_id: UUID | None = None,
    generation_id: UUID | None = None,
    body_variant_id: UUID | None = None,
    modification_id: UUID | None = None,
    price_min: Annotated[Decimal | None, Query(gt=0)] = None,
    price_max: Annotated[Decimal | None, Query(gt=0)] = None,
    currency: Literal["BYN", "USD"] | None = None,
    year_min: Annotated[int | None, Query(ge=1886, le=2100)] = None,
    year_max: Annotated[int | None, Query(ge=1886, le=2100)] = None,
    mileage_min: Annotated[int | None, Query(ge=0)] = None,
    mileage_max: Annotated[int | None, Query(ge=0)] = None,
    fuel: str | None = None,
    transmission: str | None = None,
    drive: str | None = None,
    body_type: str | None = None,
    damaged: bool | None = None,
    parts_only: bool | None = None,
    condition: str | None = None,
    color: Literal[
        "black", "white", "gray", "silver", "red", "blue", "green", "yellow", "brown", "beige", "orange", "purple", "other",
    ] | None = None,
    customs_status: Literal["cleared_rb", "eaeu_import", "uncleared", "unknown"] | None = None,
    technical_condition: Literal["good", "needs_repair", "non_operational"] | None = None,
    body_condition: Literal["good", "minor_damage", "significant_damage", "repaired"] | None = None,
    exchange: bool | None = None,
    bargaining: bool | None = None,
    credit: bool | None = None,
    leasing: bool | None = None,
    equipment: Annotated[list[Literal[
        "abs", "esp", "airbags", "air_conditioning", "climate_control", "heated_seats",
        "cruise_control", "parking_sensors", "rear_camera", "leather_seats", "carplay", "android_auto",
    ]] | None, Query()] = None,
    district: str | None = None,
    call_hours: str | None = None,
    has_vin: bool | None = None,
    has_photos: bool | None = None,
    engine_volume_min: Annotated[Decimal | None, Query(ge=0, le=30)] = None,
    engine_volume_max: Annotated[Decimal | None, Query(ge=0, le=30)] = None,
    power_min: Annotated[int | None, Query(ge=1, le=3000)] = None,
    power_max: Annotated[int | None, Query(ge=1, le=3000)] = None,
    region_id: UUID | None = None,
    city_id: UUID | None = None,
    seller_type: Literal["private", "company"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=25)] = 25,
    sort: Literal["newest", "price_asc", "price_desc", "year_desc", "mileage_asc"] = "newest",
) -> dict:
    price_operation = price_min is not None or price_max is not None or sort in {"price_asc", "price_desc"}
    if price_operation and currency is None:
        fail(422, "currency_required", "Price filters and sorting require currency=BYN or currency=USD", {"currency": "Required for price operations"})
    rate_info = _latest_exchange_rate(db)
    latest_rate, rate_fresh = rate_info
    if price_operation and not rate_fresh:
        fail(422, "exchange_rate_unavailable", "Price filtering and sorting require a fresh official exchange rate", {"currency": "A fresh exchange rate is unavailable"})

    query = _active_query()
    if q:
        term = f"%{q.strip()[:100]}%"
        query = query.outerjoin(CatalogMake, Listing.make_id == CatalogMake.id).outerjoin(CatalogModel, Listing.model_id == CatalogModel.id).where(
            or_(Listing.title.ilike(term), Listing.make_name_snapshot.ilike(term), Listing.model_name_snapshot.ilike(term),
                CatalogMake.name.ilike(term), cast(CatalogMake.aliases, String).ilike(term), CatalogModel.name.ilike(term), cast(CatalogModel.aliases, String).ilike(term),
                Listing.manual_city.ilike(term), Listing.district.ilike(term))
        )
    for field, value in ((Listing.make_id, make_id), (Listing.model_id, model_id), (Listing.generation_id, generation_id),
                         (Listing.body_variant_id, body_variant_id),
                         (Listing.modification_id, modification_id),
                         (Listing.region_id, region_id), (Listing.city_id, city_id), (Listing.fuel, fuel),
                         (Listing.transmission, transmission), (Listing.drive, drive), (Listing.condition, condition),
                         (Listing.color, color), (Listing.customs_status, customs_status),
                         (Listing.technical_condition, technical_condition), (Listing.body_condition, body_condition),
                         (Listing.exchange, exchange), (Listing.bargaining, bargaining), (Listing.credit, credit),
                         (Listing.leasing, leasing), (Listing.damaged, damaged), (Listing.parts_only, parts_only)):
        if value is not None:
            query = query.where(field == value)
    if body_type:
        query = query.join(CatalogBodyType, Listing.body_type_id == CatalogBodyType.id).where(
            or_(cast(Listing.body_type_id, String) == body_type, CatalogBodyType.slug == body_type)
        )
    if equipment:
        query = query.where(Listing.equipment.contains(equipment))
    if district:
        query = query.where(Listing.district.ilike(f"%{district.strip()[:120]}%"))
    if call_hours:
        query = query.where(Listing.call_hours.ilike(f"%{call_hours.strip()[:120]}%"))
    if has_vin is not None:
        has_vin_expression = Listing.vin.is_not(None) & (func.length(func.trim(Listing.vin)) > 0)
        query = query.where(has_vin_expression if has_vin else ~has_vin_expression)
    if has_photos is not None:
        ready_photo = select(ListingPhoto.id).where(
            ListingPhoto.listing_id == Listing.id,
            ListingPhoto.status == "ready",
        ).exists()
        query = query.where(ready_photo if has_photos else ~ready_photo)
    if seller_type == "private":
        query = query.where(Listing.company_id.is_(None))
    if seller_type == "company":
        query = query.where(Listing.company_id.is_not(None))
    display_price = _display_price_expression(currency, latest_rate) if currency and rate_fresh and latest_rate else Listing.price_amount
    if price_min is not None:
        query = query.where(display_price >= price_min)
    if price_max is not None:
        query = query.where(display_price <= price_max)
    if year_min is not None:
        query = query.where(Listing.year >= year_min)
    if year_max is not None:
        query = query.where(Listing.year <= year_max)
    if mileage_min is not None:
        query = query.where(Listing.mileage_km >= mileage_min)
    if mileage_max is not None:
        query = query.where(Listing.mileage_km <= mileage_max)
    if engine_volume_min is not None:
        query = query.where(Listing.engine_volume_l >= engine_volume_min)
    if engine_volume_max is not None:
        query = query.where(Listing.engine_volume_l <= engine_volume_max)
    if power_min is not None:
        query = query.where(Listing.power_hp >= power_min)
    if power_max is not None:
        query = query.where(Listing.power_hp <= power_max)

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = int(db.scalar(count_query) or 0)
    order = {
        "newest": (Listing.created_at.desc(), Listing.id.desc()),
        "price_asc": (display_price.asc().nullslast(), Listing.id.asc()),
        "price_desc": (display_price.desc().nullslast(), Listing.id.desc()),
        "year_desc": (Listing.year.desc(), Listing.id.desc()),
        "mileage_asc": (Listing.mileage_km.asc(), Listing.id.asc()),
    }[sort]
    bind = db.get_bind()
    promotion_table_available = (
        bind.dialect.name == "postgresql"
        or (sort == "newest" and sa_inspect(bind).has_table("listing_promotions"))
    )
    if sort == "newest" and promotion_table_available:
        active_boost = (
            select(
                ListingPromotion.listing_id.label("listing_id"),
                func.max(case(
                    (ListingPromotion.service_code == "top", 2),
                    else_=1,
                )).label("rank"),
            )
            .where(
                ListingPromotion.listing_id.is_not(None),
                ListingPromotion.service_code.in_({"top", "bump"}),
                ListingPromotion.status == "active",
                ListingPromotion.starts_at <= func.now(),
                ListingPromotion.ends_at > func.now(),
            )
            .group_by(ListingPromotion.listing_id)
            .subquery()
        )
        query = query.outerjoin(active_boost, active_boost.c.listing_id == Listing.id)
        order = (active_boost.c.rank.desc().nullslast(), *order)
    rows = db.scalars(query.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    result = {
        "items": _listed(db, rows, rate_info=rate_info, display_currency=currency),
        "pagination": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size},
    }
    if rate_fresh and latest_rate:
        result["fx"] = {"rate_date": latest_rate.rate_date, "usd_rate": str(latest_rate.official_rate), "scale": latest_rate.scale}
    return result


@router.get("/listings/public-capabilities", response_model=ListingPublicCapabilitiesOut)
def listing_public_capabilities(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    enabled = bool(getattr(settings, "public_guest_contact_enabled", False))
    if not enabled:
        secure = bool(getattr(settings, "session_cookie_secure", False))
        for name in (GUEST_CONTACT_PROOF_COOKIE, GUEST_CONTACT_DEVICE_COOKIE):
            response.delete_cookie(
                name, path="/", secure=secure, httponly=True, samesite="strict"
            )
        return {"guest_contact_reveal_enabled": False}

    secure = bool(getattr(settings, "session_cookie_secure", False))
    device_nonce = _guest_contact_cookie_nonce(
        request.cookies.get(GUEST_CONTACT_DEVICE_COOKIE),
        "device",
        GUEST_CONTACT_DEVICE_TTL_SECONDS,
    )
    if device_nonce is None:
        device_nonce = new_secret()
        response.set_cookie(
            GUEST_CONTACT_DEVICE_COOKIE,
            _guest_contact_cookie_value("device", device_nonce, GUEST_CONTACT_DEVICE_TTL_SECONDS),
            max_age=GUEST_CONTACT_DEVICE_TTL_SECONDS,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )

    proof_value = request.cookies.get(GUEST_CONTACT_PROOF_COOKIE)
    if _guest_contact_cookie_nonce(
        proof_value, "proof", GUEST_CONTACT_PROOF_TTL_SECONDS
    ) is None:
        proof_value = _guest_contact_cookie_value(
            "proof", new_secret(), GUEST_CONTACT_PROOF_TTL_SECONDS
        )
        response.set_cookie(
            GUEST_CONTACT_PROOF_COOKIE,
            proof_value,
            max_age=GUEST_CONTACT_PROOF_TTL_SECONDS,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )
    response.headers["X-Guest-Contact-Token"] = proof_value
    return {"guest_contact_reveal_enabled": True}


@router.get(
    "/listings/{listing_id}",
    response_model=ListingDetailOut,
    response_model_exclude_unset=True,
    responses={410: {"model": ApiErrorOut, "description": "Previously published listing is archived"}},
)
def get_listing(listing_id: UUID, db: Annotated[Session, Depends(get_db)], user: Annotated[User | None, Depends(get_optional_user)]) -> dict:
    listing = db.get(Listing, listing_id)
    if listing is None:
        fail(404, "not_found", "Listing not found")
    if listing.status == "archived":
        # Keep URLs for listings that were actually published as a durable
        # gone resource. The archive reason is deliberately not part of this
        # decision: seller removal, retention cleanup, and future archive
        # workflows all need the same HTTP contract once a public URL existed.
        archive_event = db.scalar(select(ListingStatusEvent).where(
            ListingStatusEvent.listing_id == listing.id,
            ListingStatusEvent.to_status == "archived",
        ).order_by(ListingStatusEvent.revision.desc()).limit(1))
        was_published = archive_event is not None and db.scalar(select(ListingStatusEvent.id).where(
            ListingStatusEvent.listing_id == listing.id,
            ListingStatusEvent.to_status == "active",
            ListingStatusEvent.revision < archive_event.revision,
        ).limit(1)) is not None
        if was_published:
            fail(410, "gone", "Listing is no longer available")
        fail(404, "not_found", "Listing not found")
    public = listing_is_public(db, listing)
    company_access = False
    if user is not None and listing.company_id is not None:
        company = db.get(Company, listing.company_id)
        company_access = company is not None and company.status != "blocked" and company_role_for(db, company, user) is not None
    owner_view = user is not None and (
        user.id == listing.owner_id
        or company_access
        or (user.role in {"moderator", "admin"} and listing.status == "pending_review")
    )
    if not public and not owner_view:
        fail(404, "not_found", "Listing not found")
    if listing.status == "blocked":
        fail(404, "not_found", "Listing not found")
    result = {
        "listing": _listed(
            db,
            [listing],
            public=public,
            include_contact=user is not None and (user.id == listing.owner_id or company_access),
            display_currency="BYN",
            include_modification=True,
        )[0]
    }
    if (
        public
        and not owner_view
        and (user is None or user.role == "user")
        and sa_inspect(db.get_bind()).has_table("listing_view_events")
    ):
        db.add(ListingViewEvent(listing_id=listing.id))
        db.commit()
    return result


@router.get(
    "/listings/{listing_id}/related",
    response_model=ListingRelatedOut,
    response_model_exclude_unset=True,
)
def related_listings(
    listing_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    listing = db.get(Listing, listing_id)
    if listing is None or not listing_is_public(db, listing):
        fail(404, "not_found", "Listing not found")

    query = _active_query().where(Listing.id != listing.id)
    if listing.model_id is not None:
        related_rank = case((Listing.model_id == listing.model_id, 0), else_=1)
        same_model_or_make = Listing.model_id == listing.model_id
        if listing.make_id is not None:
            same_model_or_make = or_(same_model_or_make, Listing.make_id == listing.make_id)
        query = query.where(same_model_or_make)
    elif listing.manual_model or listing.model_name_snapshot:
        model_name = (listing.manual_model or listing.model_name_snapshot or "").strip().casefold()
        make_name = (listing.manual_make or listing.make_name_snapshot or "").strip().casefold()
        related_model = func.lower(func.trim(func.coalesce(Listing.manual_model, Listing.model_name_snapshot))) == model_name
        if make_name:
            same_model_or_make = or_(
                related_model,
                func.lower(func.trim(func.coalesce(Listing.manual_make, Listing.make_name_snapshot))) == make_name,
            )
            related_rank = case((related_model, 0), else_=1)
        else:
            same_model_or_make = related_model
            related_rank = case((related_model, 0), else_=1)
        query = query.where(same_model_or_make)
    elif listing.make_id is not None:
        query = query.where(Listing.make_id == listing.make_id)
        related_rank = case((Listing.make_id == listing.make_id, 0), else_=1)
    elif listing.manual_make or listing.make_name_snapshot:
        make_name = (listing.manual_make or listing.make_name_snapshot or "").strip().casefold()
        same_make = func.lower(func.trim(func.coalesce(Listing.manual_make, Listing.make_name_snapshot))) == make_name
        query = query.where(same_make)
        related_rank = case((same_make, 0), else_=1)
    elif listing.body_type_id is not None:
        query = query.where(Listing.body_type_id == listing.body_type_id)
        related_rank = case((Listing.body_type_id == listing.body_type_id, 0), else_=1)
    elif listing.region_id is not None:
        query = query.where(Listing.region_id == listing.region_id)
        related_rank = case((Listing.region_id == listing.region_id, 0), else_=1)
    else:
        return {"items": []}

    rows = db.scalars(
        query.order_by(related_rank, Listing.created_at.desc(), Listing.id.desc()).limit(8)
    ).all()
    return {"items": _listed(db, rows)}


@router.get(
    "/listings/{listing_id}/analytics",
    response_model=ListingAnalyticsOut,
)
def listing_analytics(
    listing_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    listing = db.get(Listing, listing_id)
    company_access = False
    if listing is not None and listing.company_id is not None:
        company = db.get(Company, listing.company_id)
        company_access = (
            company is not None
            and company.status != "blocked"
            and company_role_for(db, company, user) is not None
        )
    if listing is None or (listing.owner_id != user.id and not company_access):
        fail(404, "not_found", "Listing not found")

    today = datetime.now(timezone.utc).date()
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

    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    view_events_available = sa_inspect(db.get_bind()).has_table("listing_view_events")
    counts = {
        "views": int(db.scalar(select(func.count(ListingViewEvent.id)).where(
            ListingViewEvent.listing_id == listing.id,
            ListingViewEvent.created_at >= start,
            ListingViewEvent.created_at < end,
        )) or 0) if view_events_available else 0,
        "contact_reveals": int(db.scalar(select(func.count(ContactReveal.id)).where(
            ContactReveal.listing_id == listing.id,
            ContactReveal.created_at >= start,
            ContactReveal.created_at < end,
        )) or 0),
        "chats": int(db.scalar(select(func.count(Conversation.id)).where(
            Conversation.listing_id == listing.id,
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )) or 0),
    }
    return {
        "listing_id": listing.id,
        "period": {"start": date_from.isoformat(), "end": date_to.isoformat()},
        **counts,
    }


def require_csrf_for_optional_user(
    request: Request,
    user: Annotated[User | None, Depends(get_optional_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserSession | None:
    if user is None:
        return None
    return require_csrf(request, get_session_record(request, db))


@router.post(
    "/listings/{listing_id}/phone-reveal", response_model=PhoneRevealOut
)
def reveal_phone(
    listing_id: UUID, request: Request,
    response: Response,
    user: Annotated[User | None, Depends(get_optional_user)],
    csrf: Annotated[UserSession | None, Depends(require_csrf_for_optional_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    response.headers["Cache-Control"] = "no-store, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    guest_contact_enabled = bool(
        getattr(get_settings(), "public_guest_contact_enabled", False)
    )
    if user is None and not guest_contact_enabled:
        fail(401, "unauthorized", "Sign in required")

    guest_device_nonce = None
    if user is None:
        guest_device_nonce = _require_guest_contact_proof(request)

    listing = db.get(Listing, listing_id)
    if listing is None or listing.status != "active" or not listing_is_public(db, listing):
        fail(404, "not_found", "Listing not found")
    listing_owner_id = listing.owner_id
    listing_company_id = listing.company_id
    if user is not None:
        consume_rate_limit(db, "phone-reveal", str(user.id), 30, timedelta(hours=1))
    else:
        ip = client_ip(request)
        # Persist only keyed fingerprints through the rate-limit bucket hashes;
        # never retain or log the raw address for guest contact requests.
        ip_fingerprint = secret_hash(ip)
        consume_rate_limit(
            db,
            "guest-phone-reveal-ip",
            ip_fingerprint,
            GUEST_PHONE_REVEAL_IP_LIMIT,
            timedelta(hours=1),
        )
        consume_rate_limit(
            db,
            "guest-phone-reveal-device",
            secret_hash(guest_device_nonce or ""),
            GUEST_PHONE_REVEAL_DEVICE_LIMIT,
            timedelta(hours=1),
        )
        consume_rate_limit(
            db,
            "guest-phone-reveal-listing",
            str(listing_id),
            GUEST_PHONE_REVEAL_LISTING_LIMIT,
            timedelta(hours=1),
        )
    listing = _lock_public_active_listing(
        db,
        listing_id,
        listing_owner_id,
        listing_company_id,
        actor_id=user.id if user is not None else None,
        session_token_hash=csrf.token_hash if user is not None and csrf is not None else None,
    )
    reveal = ContactReveal(
        listing_id=listing.id,
        user_id=user.id if user is not None else None,
    )
    phone = listing.contact_phone
    db.add(reveal)
    db.commit()
    return {"phone": phone}


@router.post(
    "/listings/{listing_id}/reports", response_model=ListingReportOut
)
def report_listing(
    listing_id: UUID, payload: ReportInput, request: Request,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    listing = db.get(Listing, listing_id)
    if listing is None or not listing_is_public(db, listing):
        fail(404, "not_found", "Listing not found")
    ip = client_ip(request)
    consume_rate_limit(db, "listing-report", f"{ip}:{user.id}", 5, timedelta(hours=1))
    report = Report(listing_id=listing.id, reporter_id=user.id, category=payload.category, comment=payload.comment, status="open")
    db.add(report)
    db.commit()
    return {"id": str(report.id), "status": report.status, "revision": report.revision}


@router.post(
    "/listings/drafts",
    response_model=ListingOwnerDetailOut,
    response_model_exclude_unset=True,
)
def create_draft(
    payload: ListingForm,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if not idempotency_key or len(idempotency_key) > 120:
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    lock_owner(db, user.id)
    prior = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor_id == user.id, IdempotencyRecord.scope == "listing.draft", IdempotencyRecord.key == idempotency_key))
    if prior:
        listing = db.get(Listing, prior.resource_id)
        return {"listing": serialize_listing(db, listing, public=False, include_contact=True)}
    values = payload.model_dump(exclude_unset=True)
    if values.get("seller_type") == "company":
        seller_company(db, user, "company")
    listing = Listing(owner_id=user.id, slug=f"listing-{uuid4().hex}", status="draft", revision=1, title="", description="", contact_phone="", damaged=False, parts_only=False)
    _apply_fields(db, listing, values, user, creating=True)
    db.add(listing)
    db.flush()
    db.add(IdempotencyRecord(actor_id=user.id, scope="listing.draft", key=idempotency_key, resource_id=listing.id))
    db.commit()
    db.refresh(listing)
    return {"listing": serialize_listing(db, listing, public=False, include_contact=True)}


@router.patch(
    "/listings/{listing_id}",
    response_model=ListingOwnerDetailOut,
    response_model_exclude_unset=True,
)
def update_listing(
    listing_id: UUID, payload: ListingPatch,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    # AuditEvent.actor_id is a User foreign key. Lock the actor before the
    # shared company/listing scope so concurrent phone reveals use one order.
    actor = db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or actor.status != "active":
        fail(403, "seller_unavailable", "Seller account is not active")
    listing = require_owned_listing(
        db,
        listing_id,
        user,
        lock=True,
        foreign_public_active_forbidden=True,
    )
    values = payload.model_dump(exclude_unset=True)
    check_revision(listing, values.pop("expected_revision"))
    if listing.status in {"sold", "blocked", "archived"}:
        fail(409, "listing_not_editable", "This listing cannot be edited")
    before_fields = snapshot_listing_fields(db, listing)
    seller_type = values.get("seller_type")
    if seller_type == "company":
        company = seller_company(db, user, "company")
        listing.company_id = company.id
    elif seller_type == "private":
        if listing.company_id is not None:
            company = db.get(Company, listing.company_id)
            if company is None or company.owner_id != user.id or listing.owner_id != user.id:
                fail(403, "company_listing_protected", "Only the company owner can move their own listing to a private account")
        listing.company_id = None
    _apply_fields(db, listing, values, user, creating=False)
    previous_status = listing.status
    if previous_status != "draft":
        listing.status = "draft"
        listing.submitted_revision = None
        listing.moderation_reason = None
        db.add(ListingStatusEvent(listing_id=listing.id, actor_id=user.id, from_status=previous_status, to_status="draft", revision=listing.revision + 1, reason="seller_edit"))
    listing.revision += 1
    audit_event = build_listing_edit_event(
        actor_id=user.id,
        listing=listing,
        before=before_fields,
        after=snapshot_listing_fields(db, listing),
        from_status=previous_status,
    )
    if audit_event is not None:
        db.add(audit_event)
    db.commit()
    return {"listing": serialize_listing(db, listing, public=False, include_contact=True)}


@router.post(
    "/listings/{listing_id}/submit",
    response_model=ListingOwnerDetailOut,
    response_model_exclude_unset=True,
)
def submit_listing(
    listing_id: UUID, payload: RevisionInput,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if not idempotency_key or len(idempotency_key) > 120:
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    lock_owner(db, user.id)
    listing = require_owned_listing(db, listing_id, user, lock=True)
    prior = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.actor_id == user.id, IdempotencyRecord.scope == f"listing.submit:{listing_id}", IdempotencyRecord.key == idempotency_key))
    if prior:
        return {"listing": serialize_listing(db, db.get(Listing, prior.resource_id), public=False, include_contact=True)}
    check_revision(listing, payload.expected_revision)
    if listing.status not in {"draft", "rejected"}:
        fail(409, "invalid_listing_state", "Only a draft or rejected listing can be submitted")
    photos = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)).all()
    if any(photo.status == "processing" for photo in photos):
        fail(409, "photos_processing", "Wait for all photos to finish processing")
    if any(photo.status != "ready" for photo in photos):
        fail(422, "photo_processing_failed", "Remove failed photos and upload them again", {"photos": "One or more photos failed processing"})
    validate_listing_for_submit(db, listing)
    if listing.company_id:
        company = db.scalar(select(Company).where(Company.id == listing.company_id).with_for_update())
        if company is None or company.status != "approved":
            fail(403, "company_not_approved", "Company approval is required")
    count = active_quota_count(db, user.id, listing.company_id)
    company_for_quota = db.get(Company, listing.company_id) if listing.company_id else None
    limit = quota_limit(company_for_quota, db)
    if count >= limit:
        fail(409, "quota_exceeded", f"Active listing quota ({limit}) reached")
    listing.submitted_revision = listing.revision
    listing.moderation_reason = None
    _record_transition(db, listing, user, "pending_review")
    db.add(IdempotencyRecord(actor_id=user.id, scope=f"listing.submit:{listing_id}", key=idempotency_key, resource_id=listing.id))
    db.commit()
    return {"listing": serialize_listing(db, listing, public=False, include_contact=True)}


def _seller_transition(listing_id: UUID, payload: RevisionInput, user: User, db: Session, target: str) -> dict:
    lock_owner(db, user.id)
    listing = require_owned_listing(db, listing_id, user, lock=True)
    check_revision(listing, payload.expected_revision)
    allowed = {
        "paused": {"active"}, "active": {"paused"}, "sold": {"active", "paused"},
    }
    if listing.status not in allowed.get(target, set()):
        fail(409, "invalid_listing_state", f"Cannot move {listing.status} listing to {target}")
    if target == "active":
        if listing.company_id:
            company = db.scalar(select(Company).where(Company.id == listing.company_id).with_for_update())
            if company is None or company.status != "approved":
                fail(403, "company_not_approved", "Company approval is required")
        count = active_quota_count(db, user.id, listing.company_id)
        company = db.get(Company, listing.company_id) if listing.company_id else None
        limit = quota_limit(company, db)
        if count >= limit:
            fail(409, "quota_exceeded", f"Active listing quota ({limit}) reached")
    listing.revision += 1
    if target == "sold":
        listing.sold_at = datetime.now(timezone.utc)
    _record_transition(db, listing, user, target)
    if target == "active":
        enqueue_saved_search_match(db, listing)
    db.commit()
    return {"listing": serialize_listing(db, listing, public=False, include_contact=True)}


@router.post(
    "/listings/{listing_id}/pause",
    response_model=ListingOwnerDetailOut,
    response_model_exclude_unset=True,
)
def pause_listing(listing_id: UUID, payload: RevisionInput, user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    return _seller_transition(listing_id, payload, user, db, "paused")


@router.post(
    "/listings/{listing_id}/resume",
    response_model=ListingOwnerDetailOut,
    response_model_exclude_unset=True,
)
def resume_listing(listing_id: UUID, payload: RevisionInput, user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    return _seller_transition(listing_id, payload, user, db, "active")


@router.post(
    "/listings/{listing_id}/sold",
    response_model=ListingOwnerDetailOut,
    response_model_exclude_unset=True,
)
def sold_listing(listing_id: UUID, payload: RevisionInput, user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    return _seller_transition(listing_id, payload, user, db, "sold")


@router.get("/me/listings", response_model=ListingOwnerSearchOut, response_model_exclude_unset=True)
def my_listings(
    user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1, page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    company_ids = company_ids_for_user(db, user)
    visibility = or_(Listing.owner_id == user.id, Listing.company_id.in_(company_ids)) if company_ids else Listing.owner_id == user.id
    query = select(Listing).where(visibility).order_by(Listing.updated_at.desc(), Listing.id.desc())
    total = int(db.scalar(select(func.count(Listing.id)).where(visibility)) or 0)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": _listed(db, rows, public=False, include_contact=True), "pagination": {"page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}}


@router.get("/me/favorites", response_model=ListingFavoritesOut, response_model_exclude_unset=True)
def my_favorites(user: Annotated[User, Depends(get_current_user)], db: Annotated[Session, Depends(get_db)]) -> dict:
    rows = db.scalars(select(Listing).join(Favorite, Favorite.listing_id == Listing.id).where(Favorite.user_id == user.id).order_by(Favorite.created_at.desc())).all()
    return {"items": _listed(db, [listing for listing in rows if listing_is_public(db, listing)])}


@router.put(
    "/me/favorites/{listing_id}", response_model=FavoriteToggleOut
)
def add_favorite(listing_id: UUID, user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    listing = db.get(Listing, listing_id)
    if listing is None or not listing_is_public(db, listing):
        fail(404, "not_found", "Listing not found")
    statement = pg_insert(Favorite).values(user_id=user.id, listing_id=listing.id).on_conflict_do_nothing(constraint="uq_favorite_user_listing")
    db.execute(statement)
    db.commit()
    return {"ok": True}


@router.delete(
    "/me/favorites/{listing_id}", response_model=FavoriteToggleOut
)
def remove_favorite(listing_id: UUID, user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)], db: Annotated[Session, Depends(get_db)]) -> dict:
    db.query(Favorite).filter(Favorite.user_id == user.id, Favorite.listing_id == listing_id).delete(synchronize_session=False)
    db.commit()
    return {"ok": True}
