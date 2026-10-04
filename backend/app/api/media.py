import io
import logging
import shutil
import warnings
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_optional_user, require_csrf
from app.config import get_settings
from app.db import get_db
from app.logging_config import configure_json_logger, log_event
from app.listing_change_audit import build_listing_photo_edit_event
from app.media_schemas import (
    ListingPhotoStatusesResponse,
    PhotoMutationResponse,
    PhotoUploadResponse,
)
from app.models import Company, Listing, ListingPhoto, User, UserSession
from app.dealer_services import company_role_for
from app.schemas import PhotoReorderInput, RevisionInput
from app.services import check_revision, enqueue_job, fail, listing_is_public, lock_owner, require_owned_listing

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 60_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
router = APIRouter(prefix="/api/v1", tags=["photos"])
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}
FORMAT_MIME_TYPES = {
    "JPEG": {"image/jpeg", "image/jpg"},
    "PNG": {"image/png"},
    "WEBP": {"image/webp"},
    "HEIF": {"image/heif", "image/heic"},
    "HEIC": {"image/heif", "image/heic"},
}
logger = configure_json_logger(__name__)


def _company_photo_access(db: Session, listing: Listing, user: User | None) -> bool:
    if user is None or listing.company_id is None:
        return False
    company = db.get(Company, listing.company_id)
    if company is None or company.status == "blocked":
        return False
    return company_role_for(db, company, user) is not None


def _photo_state(db: Session, listing_id: UUID) -> list[dict]:
    return [
        {"id": str(photo.id), "position": photo.position, "is_cover": photo.is_cover, "status": photo.status}
        for photo in db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing_id)).all()
    ]


def _record_photo_edit(db: Session, listing: Listing, actor: User, before: list[dict], from_status: str) -> None:
    db.flush()
    event = build_listing_photo_edit_event(
        actor_id=actor.id, listing_id=listing.id, revision=listing.revision,
        from_status=from_status, to_status=listing.status,
        before=before, after=_photo_state(db, listing.id),
    )
    if event is not None:
        db.add(event)


def _media_path(media_root: Path, *parts: str) -> Path | None:
    root = media_root.resolve()
    try:
        path = root.joinpath(*parts).resolve()
    except (OSError, RuntimeError):
        return None
    return path if path != root and path.is_relative_to(root) else None


class PhotoFileResponse(FileResponse):
    def set_stat_headers(self, stat_result) -> None:
        self.headers.setdefault("content-length", str(stat_result.st_size))

    def _should_use_range(self, http_if_range: str) -> bool:
        return False


def _draft(db: Session, listing: Listing, user: User) -> None:
    if listing.company_id is None and listing.owner_id != user.id:
        fail(404, "not_found", "Listing not found")
    if listing.status != "draft":
        fail(409, "listing_not_editable", "Photos can only be changed on a draft")


def _validate_image_data(raw: bytes, max_pixels: int, content_type: str | None = None) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ALLOWED_FORMATS:
                fail(415, "unsupported_photo", "Upload JPEG, PNG, WebP, or HEIC")
            declared_type = (content_type or "").split(";", 1)[0].strip().lower()
            if declared_type not in {"", "application/octet-stream"} and declared_type not in FORMAT_MIME_TYPES[image.format]:
                fail(415, "photo_mime_mismatch", "Photo content type does not match image data")
            if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
                fail(415, "animated_photo", "Animated images are not supported")
            if image.width * image.height > max_pixels:
                fail(413, "photo_pixel_limit", "Photo exceeds the 60 megapixel limit")
            image.verify()
            return image.size
    except Image.DecompressionBombWarning:
        fail(413, "photo_pixel_limit", "Photo exceeds the 60 megapixel limit")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        fail(415, "invalid_photo", "Photo data is invalid")


@router.post("/listings/{listing_id}/photos", response_model=PhotoUploadResponse)
def upload_photo(
    listing_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PhotoUploadResponse:
    if not idempotency_key or len(idempotency_key) > 120:
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    lock_owner(db, user.id)
    listing = require_owned_listing(db, listing_id, user, lock=True)
    before_photos, previous_status = _photo_state(db, listing.id), listing.status
    _draft(db, listing, user)
    prior = db.scalar(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id, ListingPhoto.idempotency_key == idempotency_key))
    if prior:
        return {"id": str(prior.id), "status": prior.status, "url": f"/api/v1/photos/{prior.id}/768"}
    count = len(db.scalars(select(ListingPhoto.id).where(ListingPhoto.listing_id == listing.id)).all())
    if count >= 30:
        fail(409, "photo_limit", "A listing can have at most 30 photos")

    settings = get_settings()
    raw = file.file.read(settings.upload_max_bytes + 1)
    if len(raw) > settings.upload_max_bytes:
        fail(413, "photo_too_large", "Photo exceeds the 20 MiB limit")
    width, height = _validate_image_data(raw, settings.upload_max_pixels, file.content_type)

    photo_id = uuid4()
    storage_name = photo_id.hex
    original_name = f"{uuid4().hex}.upload"
    quarantine = _media_path(settings.media_root, ".quarantine")
    if quarantine is None:
        fail(500, "media_storage_unavailable", "Photo storage is unavailable")
    source = _media_path(settings.media_root, ".quarantine", original_name)
    if source is None:
        fail(500, "media_storage_unavailable", "Photo storage is unavailable")
    try:
        quarantine.mkdir(parents=True, exist_ok=True, mode=0o700)
        quarantine.chmod(0o700)
        source.write_bytes(raw)
        source.chmod(0o600)
    except OSError:
        source.unlink(missing_ok=True)
        fail(500, "media_storage_unavailable", "Photo storage is unavailable")
    try:
        photo = ListingPhoto(
            id=photo_id, listing_id=listing.id, storage_name=storage_name, original_name=original_name,
            status="processing", position=count, is_cover=count == 0, width=width, height=height,
            idempotency_key=idempotency_key,
        )
        db.add(photo)
        listing.revision += 1
        enqueue_job(db, "photo.process", f"photo.process:{photo_id}", {"photo_id": str(photo_id)})
        _record_photo_edit(db, listing, user, before_photos, previous_status)
        db.commit()
    except Exception:
        db.rollback()
        source.unlink(missing_ok=True)
        raise
    return {"id": str(photo.id), "status": photo.status, "url": f"/api/v1/photos/{photo.id}/768"}


@router.delete("/listings/{listing_id}/photos/{photo_id}", response_model=PhotoMutationResponse)
def delete_photo(
    listing_id: UUID, photo_id: UUID,
    payload: RevisionInput,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> PhotoMutationResponse:
    lock_owner(db, user.id)
    listing = require_owned_listing(db, listing_id, user, lock=True)
    before_photos, previous_status = _photo_state(db, listing.id), listing.status
    _draft(db, listing, user)
    check_revision(listing, payload.expected_revision)
    photo = db.scalar(select(ListingPhoto).where(ListingPhoto.id == photo_id, ListingPhoto.listing_id == listing.id).with_for_update())
    if photo is None:
        fail(404, "not_found", "Photo not found")
    media_root = get_settings().media_root
    source = _media_path(media_root, ".quarantine", photo.original_name)
    variants = _media_path(media_root, photo.storage_name)
    was_cover = photo.is_cover
    db.delete(photo)
    db.flush()
    photos = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id).order_by(ListingPhoto.position)).all()
    for index, item in enumerate(photos):
        item.position = index
        item.is_cover = index == 0 if was_cover else item.is_cover
    listing.revision += 1
    _record_photo_edit(db, listing, user, before_photos, previous_status)
    db.commit()
    for path in (source, variants):
        if path is None:
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            log_event(
                logger,
                logging.ERROR,
                "media_cleanup_failed",
                photo_id=str(photo_id),
                error_type=type(exc).__name__,
            )
    return {"ok": True}


@router.post("/listings/{listing_id}/photos/reorder", response_model=PhotoMutationResponse)
def reorder_photos(
    listing_id: UUID, payload: PhotoReorderInput,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> PhotoMutationResponse:
    lock_owner(db, user.id)
    listing = require_owned_listing(db, listing_id, user, lock=True)
    before_photos, previous_status = _photo_state(db, listing.id), listing.status
    _draft(db, listing, user)
    check_revision(listing, payload.expected_revision)
    photos = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)).all()
    by_id = {photo.id: photo for photo in photos}
    if len(payload.photo_ids) != len(photos) or set(payload.photo_ids) != set(by_id):
        fail(422, "photo_order_invalid", "photo_ids must contain every listing photo once")
    for index, photo_id in enumerate(payload.photo_ids):
        by_id[photo_id].position = index
        by_id[photo_id].is_cover = index == 0
    listing.revision += 1
    _record_photo_edit(db, listing, user, before_photos, previous_status)
    db.commit()
    return {"ok": True}


@router.post("/listings/{listing_id}/photos/{photo_id}/cover", response_model=PhotoMutationResponse)
def set_cover(
    listing_id: UUID, photo_id: UUID,
    payload: RevisionInput,
    user: Annotated[User, Depends(get_current_user)], csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> PhotoMutationResponse:
    lock_owner(db, user.id)
    listing = require_owned_listing(db, listing_id, user, lock=True)
    before_photos, previous_status = _photo_state(db, listing.id), listing.status
    _draft(db, listing, user)
    check_revision(listing, payload.expected_revision)
    photos = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)).all()
    selected = next((photo for photo in photos if photo.id == photo_id), None)
    if selected is None:
        fail(404, "not_found", "Photo not found")
    for photo in photos:
        photo.is_cover = photo.id == selected.id
    listing.revision += 1
    _record_photo_edit(db, listing, user, before_photos, previous_status)
    db.commit()
    return {"ok": True}


@router.get("/listings/{listing_id}/photos", response_model=ListingPhotoStatusesResponse)
def photo_statuses(
    listing_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ListingPhotoStatusesResponse:
    listing = db.scalar(select(Listing).where(Listing.id == listing_id))
    if listing is None:
        fail(404, "not_found", "Listing not found")
    owner_access = listing.owner_id == user.id
    reviewer_access = user.role in {"moderator", "admin"} and listing.status == "pending_review"
    if not owner_access and not reviewer_access and not _company_photo_access(db, listing, user):
        fail(404, "not_found", "Listing not found")
    rows = db.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id).order_by(ListingPhoto.position)).all()
    return {"items": [
        {"id": str(photo.id), "status": photo.status, "position": photo.position,
         "is_cover": photo.is_cover, "url": f"/api/v1/photos/{photo.id}/768" if photo.status == "ready" else None}
        for photo in rows
    ]}


@router.get(
    "/photos/{photo_id}/{size}",
    response_class=PhotoFileResponse,
    responses={
        200: {
            "description": "Processed WebP photo",
            "content": {"image/webp": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
def serve_photo(
    photo_id: UUID, size: int,
    request: Request, db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_user)] = None,
):
    if size not in {320, 768, 1600}:
        fail(404, "not_found", "Photo not found")
    photo = db.get(ListingPhoto, photo_id)
    if photo is None or photo.status != "ready":
        fail(404, "not_found", "Photo not found")
    listing = db.get(Listing, photo.listing_id)
    if listing is None:
        fail(404, "not_found", "Photo not found")
    owner_access = user is not None and user.id == listing.owner_id
    reviewer_access = user is not None and user.role in {"moderator", "admin"} and listing.status == "pending_review"
    authorized = listing_is_public(db, listing) or owner_access or reviewer_access or _company_photo_access(db, listing, user)
    if not authorized:
        fail(404, "not_found", "Photo not found")
    path = _media_path(get_settings().media_root, photo.storage_name, f"{size}.webp")
    if path is None or not path.is_file():
        fail(404, "not_found", "Photo not found")
    return PhotoFileResponse(
        path, media_type="image/webp",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
