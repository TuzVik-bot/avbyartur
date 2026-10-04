import json
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_service import lock_active_administrators
from app.api.dependencies import get_current_user, require_csrf
from app.db import get_db
from app.dealer_services import MANAGER_ROLES, TEAM_ROLES, WRITE_ROLES, resolve_company_for_user
from app.feed_schemas import (
    DealerFeedAPIImportRequest,
    DealerFeedCreate,
    DealerFeedImportOut,
    DealerFeedImportRowsOut,
    DealerFeedListOut,
    DealerFeedMissingCandidatesConfirmOut,
    DealerFeedMissingCandidatesConfirmRequest,
    DealerFeedMissingCandidatesOut,
    DealerFeedMutationOut,
    DealerFeedOut,
    DealerFeedPatch,
    DealerFeedSchemaOut,
    DealerFeedTokenOut,
)
from app.feed_services import (
    MAX_FEED_BYTES,
    FeedParseError,
    api_token_matches,
    confirm_missing_candidates,
    create_feed_import,
    digest_feed_payload,
    feed_out,
    feed_sample,
    feed_schema_out,
    import_row_out,
    import_run_out,
    issue_api_token,
    list_missing_candidates,
    parse_feed_bytes,
    preview_missing_candidates,
)
from app.models import Company, DealerFeed, FeedImportRow, FeedImportRun, User, UserSession
from app.services import fail, lock_owner


router = APIRouter(prefix="/api/v1/dealer", tags=["dealer feeds"])


def _company_feed(
    db: Session,
    user: User,
    feed_id: UUID,
    *,
    lock: bool = False,
    allowed_roles: frozenset[str] | set[str] = MANAGER_ROLES,
) -> tuple[Company, DealerFeed]:
    company, _role = resolve_company_for_user(
        db,
        user,
        allowed_roles=allowed_roles,
        require_approved=True,
    )
    query = select(DealerFeed).where(
        DealerFeed.id == feed_id,
        DealerFeed.company_id == company.id,
    )
    if lock:
        query = query.with_for_update()
    feed = db.scalar(query)
    if feed is None:
        fail(404, "not_found", "Feed not found")
    return company, feed


@router.get("/feeds", response_model=DealerFeedListOut)
def list_dealer_feeds(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company, _role = resolve_company_for_user(db, user, allowed_roles=TEAM_ROLES)
    feeds = db.scalars(
        select(DealerFeed)
        .where(DealerFeed.company_id == company.id)
        .order_by(DealerFeed.created_at.desc(), DealerFeed.id.desc())
    ).all()
    return {"items": [feed_out(feed) for feed in feeds]}


@router.get("/feeds/samples/{format_}")
def download_dealer_feed_sample(
    format_: Literal["csv", "xml", "api", "schema"],
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    resolve_company_for_user(db, user, allowed_roles=TEAM_ROLES)
    try:
        content, filename, media_type = feed_sample(format_)
    except FeedParseError as exc:
        fail(404, exc.code, str(exc))
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/feeds/{feed_id}/missing-candidates", response_model=DealerFeedMissingCandidatesOut)
def get_dealer_feed_missing_candidates(
    feed_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _company, feed = _company_feed(db, user, feed_id, allowed_roles=TEAM_ROLES)
    return {"items": list_missing_candidates(db, feed)}


@router.post(
    "/feeds/{feed_id}/missing-candidates/pause",
    response_model=DealerFeedMissingCandidatesConfirmOut,
)
def confirm_dealer_feed_missing_candidates(
    feed_id: UUID,
    payload: DealerFeedMissingCandidatesConfirmRequest,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    lock_owner(db, user.id)
    company, feed = _company_feed(db, user, feed_id, lock=True, allowed_roles=MANAGER_ROLES)
    run, paused_external_ids = confirm_missing_candidates(
        db,
        feed=feed,
        company_id=company.id,
        initiated_by=user.id,
        items=[item.model_dump() for item in payload.items],
        idempotency_key=idempotency_key,
    )
    return {"run": import_run_out(run), "paused_external_ids": paused_external_ids}


@router.get("/feeds/schema", response_model=DealerFeedSchemaOut)
def get_dealer_feed_schema(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    resolve_company_for_user(db, user, allowed_roles=TEAM_ROLES)
    return feed_schema_out()


@router.post("/feeds", response_model=DealerFeedMutationOut)
def create_dealer_feed(
    payload: DealerFeedCreate,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    lock_owner(db, user.id)
    company, _role = resolve_company_for_user(
        db, user, allowed_roles=MANAGER_ROLES, require_approved=True, lock=True,
    )
    token = digest = prefix = None
    if payload.format == "api":
        token, digest, prefix = issue_api_token()
    feed = DealerFeed(
        company_id=company.id,
        name=payload.name.strip(),
        format=payload.format,
        status="active",
        field_mapping=payload.field_mapping,
        manual_conflict_policy=payload.manual_conflict_policy,
        missing_retirement_enabled=payload.missing_retirement_enabled,
        missing_retirement_delay_hours=payload.missing_retirement_delay_hours,
        api_token_digest=digest,
        api_token_prefix=prefix,
        created_by=user.id,
    )
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return {"feed": feed_out(feed), "api_token": token}


@router.patch("/feeds/{feed_id}", response_model=DealerFeedMutationOut)
def update_dealer_feed(
    feed_id: UUID,
    payload: DealerFeedPatch,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    lock_owner(db, user.id)
    _company, feed = _company_feed(db, user, feed_id, lock=True)
    if payload.status is not None:
        feed.status = payload.status
    if payload.manual_conflict_policy is not None:
        feed.manual_conflict_policy = payload.manual_conflict_policy
    if payload.missing_retirement_enabled is not None:
        feed.missing_retirement_enabled = payload.missing_retirement_enabled
    if payload.missing_retirement_delay_hours is not None:
        feed.missing_retirement_delay_hours = payload.missing_retirement_delay_hours
    db.commit()
    db.refresh(feed)
    return {"feed": feed_out(feed), "api_token": None}


@router.post("/feeds/{feed_id}/rotate-token", response_model=DealerFeedTokenOut)
def rotate_dealer_feed_token(
    feed_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    lock_owner(db, user.id)
    _company, feed = _company_feed(db, user, feed_id, lock=True)
    if feed.format != "api":
        fail(409, "api_feed_required", "Only API feeds have tokens")
    token, feed.api_token_digest, feed.api_token_prefix = issue_api_token()
    db.commit()
    return {"feed_id": feed.id, "api_token": token, "api_token_prefix": feed.api_token_prefix}


@router.post("/feeds/{feed_id}/imports", response_model=DealerFeedImportOut)
async def import_dealer_feed_file(
    feed_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    dry_run: Annotated[bool, Query()] = True,
    complete_snapshot: Annotated[bool, Query()] = False,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    lock_owner(db, user.id)
    company, feed = _company_feed(db, user, feed_id, lock=True, allowed_roles=WRITE_ROLES)
    if feed.status != "active":
        fail(409, "feed_disabled", "This feed is disabled")
    if feed.format == "api":
        fail(409, "api_feed_required", "API feeds accept structured JSON imports")
    content = await file.read(MAX_FEED_BYTES + 1)
    filename = PurePosixPath((file.filename or "upload").replace("\\", "/")).name[:180] or "upload"
    parse_error = None
    try:
        rows = parse_feed_bytes(content, feed_format=feed.format, field_mapping=feed.field_mapping or {})
    except FeedParseError as exc:
        rows = []
        parse_error = exc
    run = create_feed_import(
        db,
        feed=feed,
        company_id=company.id,
        initiated_by=user.id,
        rows=rows,
        payload_digest=digest_feed_payload(content),
        idempotency_key=idempotency_key,
        dry_run=dry_run,
        source_filename=filename,
        complete_snapshot=complete_snapshot,
        parse_error=parse_error,
    )
    missing_candidates = list_missing_candidates(db, feed)
    if complete_snapshot and dry_run and run.rejected_rows == 0:
        seen_external_ids = {
            str(row.get("values", {}).get("dealer_external_id"))
            for row in rows
            if row.get("values", {}).get("dealer_external_id")
        }
        missing_candidates = preview_missing_candidates(
            db,
            feed,
            present_external_ids=seen_external_ids,
            payload_digest=digest_feed_payload(content),
        )
    elif complete_snapshot and not dry_run and run.status != "succeeded":
        # A rejected complete snapshot has no authority to create, clear, or confirm candidates.
        missing_candidates = list_missing_candidates(db, feed)
    return {"run": import_run_out(run), "missing_candidates": missing_candidates}


@router.post("/feeds/{feed_id}/api-imports", response_model=DealerFeedImportOut)
def import_dealer_feed_api(
    feed_id: UUID,
    payload: DealerFeedAPIImportRequest,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    dealer_feed_token: Annotated[str | None, Header(alias="X-Dealer-Feed-Token", max_length=256)] = None,
) -> dict:
    scheme, separator, token = (authorization or "").partition(" ")
    if dealer_feed_token is not None:
        if scheme.casefold() not in {"", "basic"}:
            fail(401, "feed_token_ambiguous", "Use one company feed token transport")
        token = dealer_feed_token.strip()
    elif not separator or scheme.casefold() != "bearer":
        fail(401, "feed_token_required", "A valid company API feed token is required")
    if not token or len(token) > 256:
        fail(401, "feed_token_required", "A valid API feed bearer token is required")
    initial_feed = db.scalar(select(DealerFeed).where(DealerFeed.id == feed_id))
    if (
        initial_feed is None
        or initial_feed.status != "active"
        or initial_feed.format != "api"
        or not api_token_matches(token, initial_feed.api_token_digest)
    ):
        fail(401, "feed_token_invalid", "API feed token is invalid")

    initial_company = db.scalar(select(Company).where(Company.id == initial_feed.company_id))
    if initial_company is None:
        fail(403, "company_not_approved", "An approved company is required")
    initial_company_id = initial_company.id
    initial_owner_id = initial_company.owner_id
    initial_creator_id = initial_feed.created_by

    # Match user administration and session writes: lock the active-admin set
    # first, then both user FK actors in a stable order before company/feed.
    lock_active_administrators(db)
    locked_users = db.scalars(
        select(User)
        .where(User.id.in_({initial_owner_id, initial_creator_id}))
        .order_by(User.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    users_by_id = {locked_user.id: locked_user for locked_user in locked_users}
    owner = users_by_id.get(initial_owner_id)
    if owner is None or owner.status != "active":
        fail(403, "seller_unavailable", "Seller account is not active")
    if initial_creator_id not in users_by_id:
        fail(401, "feed_token_invalid", "API feed token is invalid")

    company = db.scalar(
        select(Company)
        .where(Company.id == initial_company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if company is None or company.owner_id != initial_owner_id:
        fail(409, "feed_scope_changed", "The API feed company changed during authorization")
    if company.status != "approved":
        fail(403, "company_not_approved", "An approved company is required")

    feed = db.scalar(
        select(DealerFeed)
        .where(DealerFeed.id == feed_id, DealerFeed.company_id == initial_company_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        feed is None
        or feed.created_by != initial_creator_id
        or feed.status != "active"
        or feed.format != "api"
        or not api_token_matches(token, feed.api_token_digest)
    ):
        fail(401, "feed_token_invalid", "API feed token is invalid")

    rows = [
        {"row_number": index, "values": item}
        for index, item in enumerate(payload.items, start=1)
    ]
    content = json.dumps(payload.items, sort_keys=True, separators=(",", ":"), default=str).encode()
    run = create_feed_import(
        db,
        feed=feed,
        company_id=company.id,
        initiated_by=feed.created_by,
        rows=rows,
        payload_digest=digest_feed_payload(content),
        idempotency_key=idempotency_key,
        dry_run=payload.dry_run,
        source_filename="api",
        complete_snapshot=payload.complete_snapshot,
    )
    missing_candidates = list_missing_candidates(db, feed)
    if payload.complete_snapshot and payload.dry_run and run.rejected_rows == 0:
        seen_external_ids = {str(item.get("dealer_external_id")) for item in payload.items if item.get("dealer_external_id")}
        missing_candidates = preview_missing_candidates(
            db,
            feed,
            present_external_ids=seen_external_ids,
            payload_digest=digest_feed_payload(content),
        )
    return {"run": import_run_out(run), "missing_candidates": missing_candidates}


@router.get("/feed-imports/{run_id}", response_model=DealerFeedImportOut)
def get_dealer_feed_import(
    run_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company, _role = resolve_company_for_user(db, user, allowed_roles=TEAM_ROLES)
    run = db.scalar(select(FeedImportRun).where(
        FeedImportRun.id == run_id,
        FeedImportRun.company_id == company.id,
    ))
    if run is None:
        fail(404, "not_found", "Feed import not found")
    return {"run": import_run_out(run)}


@router.get("/feed-imports/{run_id}/rows", response_model=DealerFeedImportRowsOut)
def list_dealer_feed_import_rows(
    run_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    company, _role = resolve_company_for_user(db, user, allowed_roles=TEAM_ROLES)
    run = db.scalar(select(FeedImportRun).where(
        FeedImportRun.id == run_id,
        FeedImportRun.company_id == company.id,
    ))
    if run is None:
        fail(404, "not_found", "Feed import not found")
    rows = db.scalars(
        select(FeedImportRow)
        .where(FeedImportRow.run_id == run.id)
        .order_by(FeedImportRow.row_number, FeedImportRow.id)
    ).all()
    return {"items": [import_row_out(row) for row in rows]}
