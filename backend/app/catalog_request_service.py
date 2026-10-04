"""Ownership, snapshot, candidate matching, and review rules for catalog intake."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.catalog_schemas import CatalogModificationSourceOut, CatalogModificationSpecsOut
from app.catalog_request_models import CatalogRequest
from app.catalog_request_schemas import (
    CatalogRequestCatalogMatchOut,
    CatalogRequestCatalogNodeOut,
    CatalogRequestCreateIn,
    CatalogRequestManualParametersOut,
    CatalogRequestOut,
    CatalogRequestReviewIn,
    CatalogRequestSnapshotOut,
)
from app.dealer_services import company_role_for
from app.models import (
    AuditEvent,
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Company,
    Listing,
    User,
)
from app.services import check_revision, consume_rate_limit, fail, require_owned_listing
from app.services import catalog_modification_item


CATALOG_REQUEST_RATE_LIMIT = 10
CATALOG_REQUEST_RATE_PERIOD = timedelta(hours=1)
_WRITE_COMPANY_ROLES = frozenset({"owner", "admin", "seller"})


def _canonical_digest(value: dict[str, Any]) -> str:
    def json_value(item: Any) -> Any:
        if isinstance(item, UUID):
            return str(item)
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, dict):
            return {key: json_value(nested) for key, nested in item.items()}
        if isinstance(item, (list, tuple)):
            return [json_value(nested) for nested in item]
        return item

    encoded = json.dumps(
        json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _node(row, *, include_years: bool = False) -> dict | None:
    if row is None:
        return None
    value = {"id": str(row.id), "name": row.name}
    if include_years:
        value["year_from"] = row.year_from
        value["year_to"] = row.year_to
    return value


def _catalog_hierarchy(db: Session, listing: Listing) -> tuple[
    CatalogMake | None,
    CatalogModel | None,
    CatalogGeneration | None,
    CatalogBodyType | None,
    CatalogBodyVariant | None,
]:
    make = db.get(CatalogMake, listing.make_id) if listing.make_id else None
    model = db.get(CatalogModel, listing.model_id) if listing.model_id else None
    generation = db.get(CatalogGeneration, listing.generation_id) if listing.generation_id else None
    body_type = db.get(CatalogBodyType, listing.body_type_id) if listing.body_type_id else None
    body_variant = db.get(CatalogBodyVariant, listing.body_variant_id) if listing.body_variant_id else None

    if listing.make_id and make is None:
        fail(422, "invalid_catalog_reference", "Unknown catalog make")
    if listing.model_id and model is None:
        fail(422, "invalid_catalog_reference", "Unknown catalog model")
    if listing.generation_id and generation is None:
        fail(422, "invalid_catalog_reference", "Unknown catalog generation")
    if listing.body_type_id and body_type is None:
        fail(422, "invalid_catalog_reference", "Unknown catalog body type")
    if listing.body_variant_id and body_variant is None:
        fail(422, "invalid_catalog_reference", "Unknown catalog body variant")

    if model is not None and make is not None and model.make_id != make.id:
        fail(422, "invalid_catalog_reference", "Catalog model does not belong to the selected make")
    if generation is not None and model is not None and generation.model_id != model.id:
        fail(422, "invalid_catalog_reference", "Catalog generation does not belong to the selected model")
    if body_variant is not None and generation is not None and body_variant.generation_id != generation.id:
        fail(422, "invalid_catalog_reference", "Catalog body variant does not belong to the selected generation")

    # A child row identifies its parent exactly, so incomplete listing hierarchy
    # snapshots can still be safely used for moderator matching.
    if body_variant is not None and generation is None:
        generation = db.get(CatalogGeneration, body_variant.generation_id)
    if generation is not None and model is None:
        model = db.get(CatalogModel, generation.model_id)
    if model is not None and make is None:
        make = db.get(CatalogMake, model.make_id)

    if generation is not None and model is not None and generation.model_id != model.id:
        fail(422, "invalid_catalog_reference", "Catalog generation does not belong to the selected model")
    if model is not None and make is not None and model.make_id != make.id:
        fail(422, "invalid_catalog_reference", "Catalog model does not belong to the selected make")
    if body_variant is not None and generation is not None and body_variant.generation_id != generation.id:
        fail(422, "invalid_catalog_reference", "Catalog body variant does not belong to the selected generation")

    return make, model, generation, body_type, body_variant


def _snapshot(db: Session, listing: Listing) -> dict[str, Any]:
    make, model, generation, body_type, body_variant = _catalog_hierarchy(db, listing)
    engine_volume = (
        str(Decimal(str(listing.engine_volume_l)))
        if listing.engine_volume_l is not None
        else None
    )
    return {
        "catalog": {
            "make": _node(make),
            "model": _node(model),
            "generation": _node(generation, include_years=True),
            "body_type": _node(body_type),
            "body_variant": _node(body_variant),
        },
        "manual_identity": {
            "make": (listing.manual_make or listing.make_name_snapshot) if make is None else None,
            "model": (listing.manual_model or listing.model_name_snapshot) if model is None else None,
        },
        "manual_parameters": {
            "year": listing.year,
            "mileage_km": listing.mileage_km,
            "engine_volume_l": engine_volume,
            "power_hp": listing.power_hp,
            "fuel": listing.fuel,
            "transmission": listing.transmission,
            "drive": listing.drive,
        },
    }


def _manual_request_payload(payload: CatalogRequestCreateIn) -> dict[str, str | None]:
    return {
        "manual_modification_name": payload.manual_modification_name,
        "note": payload.note,
    }


def _key_hash(idempotency_key: str) -> str:
    return hashlib.sha256(idempotency_key.strip().encode("utf-8")).hexdigest()


def _idempotency_payload_digest(
    listing_id: UUID,
    payload: CatalogRequestCreateIn,
) -> str:
    return _canonical_digest({
        "listing_id": str(listing_id),
        "expected_listing_revision": payload.expected_listing_revision,
        **_manual_request_payload(payload),
    })


def _request_digest(snapshot: dict[str, Any], payload: CatalogRequestCreateIn) -> str:
    return _canonical_digest({
        "snapshot": snapshot,
        **_manual_request_payload(payload),
    })


def _find_idempotent_request(
    db: Session,
    *,
    actor_id: UUID,
    key_hash: str,
    payload_digest: str,
) -> CatalogRequest | None:
    prior = db.scalar(
        select(CatalogRequest).where(
            CatalogRequest.actor_id == actor_id,
            CatalogRequest.idempotency_key_hash == key_hash,
        )
    )
    if prior is None:
        return None
    if prior.idempotency_payload_digest != payload_digest:
        fail(409, "idempotency_conflict", "Idempotency-Key was already used for another request")
    return prior


def _assert_requestable_listing(listing: Listing) -> None:
    if listing.status in {"blocked", "archived"}:
        fail(409, "invalid_listing_state", "This listing cannot request a catalog change")
    if listing.modification_id is not None:
        fail(409, "modification_already_selected", "Clear the selected modification before requesting a match")


def create_catalog_request(
    db: Session,
    *,
    user: User,
    listing_id: UUID,
    payload: CatalogRequestCreateIn,
    idempotency_key: str,
) -> tuple[CatalogRequest, bool]:
    normalized_key = idempotency_key.strip()
    if not normalized_key or len(normalized_key) > 120:
        fail(422, "idempotency_required", "Idempotency-Key header is required")

    # Check listing access before replaying an existing key; a request key is
    # never an authorization token.
    listing = require_owned_listing(db, listing_id, user)
    key_hash = _key_hash(normalized_key)
    payload_digest = _idempotency_payload_digest(listing_id, payload)
    prior = _find_idempotent_request(
        db,
        actor_id=user.id,
        key_hash=key_hash,
        payload_digest=payload_digest,
    )
    if prior is not None:
        return prior, True

    consume_rate_limit(
        db,
        "catalog_request_user",
        str(user.id),
        CATALOG_REQUEST_RATE_LIMIT,
        CATALOG_REQUEST_RATE_PERIOD,
    )

    listing = require_owned_listing(db, listing_id, user, lock=True)
    check_revision(listing, payload.expected_listing_revision)
    _assert_requestable_listing(listing)

    # Recheck after the listing lock so simultaneous retries serialize on the
    # listing row before either the request key or active duplicate is created.
    prior = _find_idempotent_request(
        db,
        actor_id=user.id,
        key_hash=key_hash,
        payload_digest=payload_digest,
    )
    if prior is not None:
        return prior, True

    snapshot = _snapshot(db, listing)
    request_digest = _request_digest(snapshot, payload)
    duplicate = db.scalar(
        select(CatalogRequest).where(
            CatalogRequest.listing_id == listing.id,
            CatalogRequest.status == "pending",
            CatalogRequest.request_digest == request_digest,
        )
    )
    if duplicate is not None:
        fail(409, "catalog_request_duplicate", "An identical catalog request is already pending")

    row = CatalogRequest(
        listing_id=listing.id,
        actor_id=user.id,
        idempotency_key_hash=key_hash,
        request_digest=request_digest,
        idempotency_payload_digest=payload_digest,
        listing_revision=listing.revision,
        status="pending",
        revision=1,
        snapshot=snapshot,
        manual_modification_name=payload.manual_modification_name,
        note=payload.note,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = _find_idempotent_request(
            db,
            actor_id=user.id,
            key_hash=key_hash,
            payload_digest=payload_digest,
        )
        if prior is not None:
            return prior, True
        duplicate = db.scalar(
            select(CatalogRequest).where(
                CatalogRequest.listing_id == listing_id,
                CatalogRequest.status == "pending",
                CatalogRequest.request_digest == request_digest,
            )
        )
        if duplicate is not None:
            fail(409, "catalog_request_duplicate", "An identical catalog request is already pending")
        raise
    db.refresh(row)
    return row, False


def _can_view_listing_requests(db: Session, listing: Listing, user: User) -> None:
    if listing.company_id is None:
        if listing.owner_id != user.id:
            fail(404, "not_found", "Listing not found")
        return
    company = db.get(Company, listing.company_id)
    if company is None:
        fail(404, "not_found", "Listing not found")
    if company.status == "blocked":
        fail(403, "company_blocked", "Company access is blocked")
    if company_role_for(db, company, user) is None:
        fail(404, "not_found", "Listing not found")


def list_listing_catalog_requests(
    db: Session,
    *,
    listing_id: UUID,
    user: User,
) -> list[CatalogRequest]:
    listing = db.get(Listing, listing_id)
    if listing is None:
        fail(404, "not_found", "Listing not found")
    _can_view_listing_requests(db, listing, user)
    return db.scalars(
        select(CatalogRequest)
        .where(CatalogRequest.listing_id == listing_id)
        .order_by(CatalogRequest.created_at.desc(), CatalogRequest.id.desc())
    ).all()


def list_catalog_requests(
    db: Session,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[CatalogRequest], int]:
    query = select(CatalogRequest)
    count_query = select(func.count()).select_from(CatalogRequest)
    if status is not None:
        query = query.where(CatalogRequest.status == status)
        count_query = count_query.where(CatalogRequest.status == status)
    total = db.scalar(count_query) or 0
    rows = db.scalars(
        query.order_by(CatalogRequest.created_at.desc(), CatalogRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return rows, total


def _catalog_context_for_modification(
    db: Session,
    modification: CatalogModification,
) -> tuple[CatalogGeneration, CatalogModel, CatalogMake] | None:
    generation = db.get(CatalogGeneration, modification.generation_id)
    model = db.get(CatalogModel, generation.model_id) if generation is not None else None
    make = db.get(CatalogMake, model.make_id) if model is not None else None
    if generation is None or model is None or make is None:
        return None
    return generation, model, make


def _known_snapshot_nodes(request: CatalogRequest) -> tuple[dict | None, dict | None, dict | None, dict | None]:
    catalog = request.snapshot.get("catalog") if isinstance(request.snapshot, dict) else None
    if not isinstance(catalog, dict):
        return None, None, None, None
    return (
        catalog.get("make"),
        catalog.get("model"),
        catalog.get("generation"),
        catalog.get("body_variant"),
    )


def _matches_request(
    db: Session,
    request: CatalogRequest,
    modification: CatalogModification,
) -> bool:
    known_make, known_model, known_generation, known_body_variant = _known_snapshot_nodes(request)
    if not any((known_make, known_model, known_generation)):
        return False
    context = _catalog_context_for_modification(db, modification)
    if context is None:
        return False
    generation, model, make = context
    if known_generation is not None and str(generation.id) != known_generation.get("id"):
        return False
    if known_model is not None and str(model.id) != known_model.get("id"):
        return False
    if known_make is not None and str(make.id) != known_make.get("id"):
        return False
    if known_body_variant is not None:
        if str(generation.id) != known_body_variant.get("generation_id", str(generation.id)):
            return False

    parameters = request.snapshot.get("manual_parameters", {})
    year = parameters.get("year") if isinstance(parameters, dict) else None
    if isinstance(year, int):
        if generation.year_from is not None and year < generation.year_from:
            return False
        # A null end year means unknown, not an assertion that the generation
        # is still in production.
        if generation.year_to is not None and year > generation.year_to:
            return False
    return True


def _catalog_match_out(
    db: Session,
    modification: CatalogModification,
) -> CatalogRequestCatalogMatchOut | None:
    context = _catalog_context_for_modification(db, modification)
    if context is None:
        return None
    generation, model, make = context
    item = catalog_modification_item(modification, include_aliases=False)
    source = item.get("source")
    specs = item.get("specs")
    return CatalogRequestCatalogMatchOut(
        id=modification.id,
        slug=modification.slug,
        name=modification.name,
        make=CatalogRequestCatalogNodeOut.model_validate(_node(make)),
        model=CatalogRequestCatalogNodeOut.model_validate(_node(model)),
        generation=CatalogRequestCatalogNodeOut.model_validate(
            _node(generation, include_years=True)
        ),
        source=CatalogModificationSourceOut.model_validate(source) if source is not None else None,
        specs=CatalogModificationSpecsOut.model_validate(specs) if specs is not None else None,
    )


def catalog_request_out(db: Session, row: CatalogRequest) -> CatalogRequestOut:
    resolved = (
        db.get(CatalogModification, row.resolved_modification_id)
        if row.resolved_modification_id
        else None
    )
    return CatalogRequestOut(
        id=row.id,
        listing_id=row.listing_id,
        listing_revision=row.listing_revision,
        status=row.status,
        revision=row.revision,
        snapshot=CatalogRequestSnapshotOut(
            catalog=row.snapshot["catalog"],
            manual_identity=row.snapshot["manual_identity"],
            manual_parameters=CatalogRequestManualParametersOut.model_validate(
                row.snapshot["manual_parameters"]
            ),
        ),
        manual_modification_name=row.manual_modification_name,
        note=row.note,
        resolved_modification=_catalog_match_out(db, resolved) if resolved is not None else None,
        review_reason=row.review_reason,
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def catalog_request_matches(
    db: Session,
    *,
    request_id: UUID,
    query: str,
    limit: int,
) -> list[CatalogRequestCatalogMatchOut]:
    request = db.get(CatalogRequest, request_id)
    if request is None:
        fail(404, "not_found", "Catalog request not found")
    if request.status != "pending":
        fail(409, "catalog_request_not_pending", "Only pending requests can be matched")
    known_make, known_model, known_generation, known_body_variant = _known_snapshot_nodes(request)
    if not any((known_make, known_model, known_generation)):
        return []

    statement = (
        select(CatalogModification)
        .join(CatalogGeneration, CatalogGeneration.id == CatalogModification.generation_id)
        .join(CatalogModel, CatalogModel.id == CatalogGeneration.model_id)
        .join(CatalogMake, CatalogMake.id == CatalogModel.make_id)
    )
    if known_generation is not None:
        statement = statement.where(CatalogGeneration.id == UUID(known_generation["id"]))
    elif known_model is not None:
        statement = statement.where(CatalogModel.id == UUID(known_model["id"]))
    elif known_make is not None:
        statement = statement.where(CatalogMake.id == UUID(known_make["id"]))
    if known_body_variant is not None:
        variant_id = UUID(known_body_variant["id"])
        variant = db.get(CatalogBodyVariant, variant_id)
        if variant is None:
            return []
        statement = statement.where(CatalogGeneration.id == variant.generation_id)

    parameters = request.snapshot.get("manual_parameters", {})
    year = parameters.get("year") if isinstance(parameters, dict) else None
    if isinstance(year, int):
        statement = statement.where(
            or_(CatalogGeneration.year_from.is_(None), CatalogGeneration.year_from <= year),
            or_(CatalogGeneration.year_to.is_(None), CatalogGeneration.year_to >= year),
        )

    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    statement = statement.where(or_(
        CatalogModification.name.ilike(pattern, escape="\\"),
        CatalogGeneration.name.ilike(pattern, escape="\\"),
        CatalogModel.name.ilike(pattern, escape="\\"),
        *[
            CatalogModification.source_metadata[key].astext.ilike(pattern, escape="\\")
            for key in (
                "engine_code", "frame_code", "engine_l", "power_hp", "fuel",
                "transmission", "drive", "production_period", "summary",
            )
        ],
    ))
    rows = db.scalars(
        statement.order_by(CatalogModification.name, CatalogModification.id).limit(limit)
    ).all()
    return [
        match
        for row in rows
        if _matches_request(db, request, row)
        if (match := _catalog_match_out(db, row)) is not None
    ]


def review_catalog_request(
    db: Session,
    *,
    request_id: UUID,
    moderator: User,
    payload: CatalogRequestReviewIn,
) -> CatalogRequest:
    row = db.scalar(
        select(CatalogRequest)
        .where(CatalogRequest.id == request_id)
        .with_for_update()
    )
    if row is None:
        fail(404, "not_found", "Catalog request not found")
    check_revision(row, payload.expected_revision, "Catalog request")
    if row.status != "pending":
        fail(409, "catalog_request_not_pending", "Only pending requests can be reviewed")

    target: CatalogModification | None = None
    target_status = "rejected"
    if payload.decision == "resolve":
        target = db.get(CatalogModification, payload.resolved_modification_id)
        if target is None or not _matches_request(db, row, target):
            fail(
                422,
                "catalog_match_mismatch",
                "Select an existing modification that matches the request hierarchy",
            )
        target_status = "resolved"

    now = datetime.now(UTC)
    row.status = target_status
    row.resolved_modification_id = target.id if target is not None else None
    row.review_reason = payload.reason
    row.reviewed_by = moderator.id
    row.reviewed_at = now
    row.revision += 1
    db.add(AuditEvent(
        actor_id=moderator.id,
        entity_type="catalog_request",
        entity_id=row.id,
        action=f"catalog_request_{target_status}",
        details={
            "reason": payload.reason,
            "revision": row.revision,
            "resolved_modification_id": str(target.id) if target is not None else None,
        },
    ))
    db.commit()
    db.refresh(row)
    return row
