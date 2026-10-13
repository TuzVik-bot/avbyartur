import json
import logging
import math
import os
import shutil
import socket
import time
import urllib.request
import uuid
import warnings
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from sqlalchemy import func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.category_search import CATEGORY_PATHS
from app.db import SessionLocal, engine
from app.email_delivery import EmailDeliveryUnavailable, get_email_sender
from app.identity_models import (
    AccountRecoveryChallenge,
    EmailVerificationChallenge,
    IdentityEmailOutbox,
    VerifiedEmailContact,
)
from app.logging_config import configure_json_logger, log_event
from app.models import (
    ExchangeRate,
    Listing,
    ListingPhoto,
    ListingStatusEvent,
    NotificationOutbox,
    RateLimitBucket,
    SavedSearch,
    SavedSearchNotificationBatch,
    SavedSearchNotificationMatch,
    User,
    UserNotification,
    WorkerJob,
)
from app.notification_service import (
    saved_search_digest_email_content,
    saved_search_email_content,
    saved_search_filters,
    saved_search_matches,
)
from app.profile_identity_service import notification_delivery_allowed
from app.services import enqueue_job

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 60_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
logger = configure_json_logger("avtorinok.worker")
LEASE = timedelta(minutes=3)
ADVISORY_LOCK_KEY = 617245319
MINSK = ZoneInfo("Europe/Minsk")
HEIF_ORIENTATION_TRANSPOSE = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}


def perceptual_hash(image: Image.Image) -> str:
    """Return a stable 64-bit DCT perceptual hash for a decoded photo."""
    grayscale = image.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    pixels = list(grayscale.getdata())
    cosine = [
        [math.cos((2 * position + 1) * frequency * math.pi / 64) for position in range(32)]
        for frequency in range(8)
    ]
    horizontal = [
        [sum(pixels[y * 32 + x] * cosine[u][x] for x in range(32)) for u in range(8)]
        for y in range(32)
    ]
    coefficients = [
        [sum(horizontal[y][u] * cosine[v][y] for y in range(32)) for u in range(8)]
        for v in range(8)
    ]
    flattened = [value for row in coefficients for value in row]
    threshold = sorted(flattened[1:])[len(flattened[1:]) // 2]
    value = 0
    for coefficient in flattened:
        value = (value << 1) | (coefficient > threshold)
    return f"{value:016x}"


class PermanentJobError(ValueError):
    pass


def _claim_one(worker_id: str) -> uuid.UUID | None:
    with SessionLocal() as db:
        now = db.scalar(select(func.now()))
        job = db.scalar(
            select(WorkerJob)
            .where(
                or_(
                    (WorkerJob.status == "queued") & (WorkerJob.run_after <= now),
                    (WorkerJob.status == "running") & (WorkerJob.lease_until <= now),
                )
            )
            .order_by(WorkerJob.run_after, WorkerJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_by = worker_id
        job.lease_until = now + LEASE
        db.commit()
        return job.id


def _variants_are_valid(target_dir: Path) -> bool:
    for edge in (320, 768, 1600):
        try:
            with Image.open(target_dir / f"{edge}.webp") as variant:
                if variant.format != "WEBP":
                    return False
                variant.verify()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return False
    return True


def _make_variants(photo_id: uuid.UUID) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        photo = db.get(ListingPhoto, photo_id)
        if photo is None:
            raise PermanentJobError("Photo record is missing")
        if photo.status not in {"processing", "ready"}:
            raise PermanentJobError("Photo is not processable")
        root = settings.media_root.resolve()
        quarantine = root / ".quarantine"
        source = (quarantine / photo.original_name).resolve()
        target_dir = (root / photo.storage_name).resolve()
        if not source.is_relative_to(quarantine.resolve()) or target_dir == root or not target_dir.is_relative_to(root):
            raise PermanentJobError("Invalid photo storage location")
        staging_dir = root / f".photo-{photo.id.hex}-{uuid.uuid4().hex}.tmp"
        try:
            if photo.status == "ready":
                if _variants_are_valid(target_dir):
                    if photo.perceptual_hash is None:
                        try:
                            with Image.open(target_dir / "768.webp") as ready_image:
                                ready_image.load()
                                photo.perceptual_hash = perceptual_hash(ready_image)
                            db.commit()
                        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError) as exc:
                            raise PermanentJobError("Ready photo fingerprint could not be computed") from exc
                    try:
                        source.unlink(missing_ok=True)
                    except OSError as exc:
                        log_event(
                            logger,
                            logging.WARNING,
                            "photo_original_cleanup_failed",
                            photo_id=str(photo_id),
                            error_type=type(exc).__name__,
                        )
                    return
                if not source.is_file():
                    raise PermanentJobError("Ready photo variants are missing")
                photo.status = "processing"
            try:
                raw = Image.open(source)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise PermanentJobError("Image data is invalid") from exc
            with raw:
                if raw.format not in {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}:
                    raise PermanentJobError("Unsupported image format")
                if getattr(raw, "is_animated", False) or getattr(raw, "n_frames", 1) > 1:
                    raise PermanentJobError("Animated images are not supported")
                if raw.width * raw.height > settings.upload_max_pixels:
                    raise PermanentJobError("Image pixel limit exceeded")
                try:
                    raw.load()
                except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                    raise PermanentJobError("Image data is invalid") from exc
                if raw.width * raw.height > settings.upload_max_pixels:
                    raise PermanentJobError("Image pixel limit exceeded")
                exif_orientation = raw.getexif().get(274, 1)
                image = ImageOps.exif_transpose(raw)
                # pillow-heif resets EXIF tag 274 and keeps its original value here.
                original_orientation = raw.info.get("original_orientation")
                if (
                    raw.format in {"HEIF", "HEIC"}
                    and exif_orientation == 1
                    and original_orientation in HEIF_ORIENTATION_TRANSPOSE
                ):
                    image = image.transpose(HEIF_ORIENTATION_TRANSPOSE[original_orientation])
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                photo.width, photo.height = image.size
                photo.perceptual_hash = perceptual_hash(image)
                staging_dir.mkdir(mode=0o700)
                for edge in (320, 768, 1600):
                    longest = max(image.size)
                    if longest <= edge:
                        variant = image
                    else:
                        scale = edge / longest
                        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                        variant = image.resize(size, Image.Resampling.LANCZOS)
                    tmp = staging_dir / f"{edge}.webp.tmp"
                    final = staging_dir / f"{edge}.webp"
                    variant.save(tmp, format="WEBP", quality=86, method=5, exif=b"")
                    os.replace(tmp, final)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            os.replace(staging_dir, target_dir)
            photo.status = "ready"
            db.commit()
            try:
                source.unlink(missing_ok=True)
            except OSError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "photo_original_cleanup_failed",
                    photo_id=str(photo_id),
                    error_type=type(exc).__name__,
                )
        except PermanentJobError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(target_dir, ignore_errors=True)
            photo.status = "failed"
            db.commit()
            try:
                source.unlink(missing_ok=True)
            except OSError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "rejected_photo_cleanup_failed",
                    photo_id=str(photo_id),
                    error_type=type(exc).__name__,
                )
            raise PermanentJobError(str(exc)) from exc
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise


def _refresh_usd_rate() -> None:
    endpoint = "https://api.nbrb.by/exrates/rates/USD?parammode=2"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json", "User-Agent": "AvtorinokPilot/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.load(response)
    rate_date, official_rate, scale = _parse_nbrb_usd_rate(payload)
    values = {
        "id": uuid.uuid4(), "currency": "USD", "rate_date": rate_date,
        "official_rate": official_rate,
        "scale": scale, "source": endpoint,
        "fetched_at": datetime.now(timezone.utc),
    }
    with SessionLocal() as db:
        statement = pg_insert(ExchangeRate).values(**values).on_conflict_do_update(
            constraint="uq_exchange_rate_currency_date",
            set_={"official_rate": values["official_rate"], "scale": values["scale"], "source": endpoint, "fetched_at": values["fetched_at"]},
        )
        db.execute(statement)
        db.commit()


def _parse_nbrb_usd_rate(payload: object, *, today: date | None = None) -> tuple[str, Decimal, int]:
    """Validate the NBRB response before it can become a price-conversion input."""

    if not isinstance(payload, dict):
        raise ValueError("NBRB USD rate response must be an object")

    raw_date = payload.get("Date")
    if not isinstance(raw_date, str) or not raw_date.strip():
        raise ValueError("NBRB USD rate response has no valid date")
    try:
        rate_date = datetime.fromisoformat(raw_date.strip().replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("NBRB USD rate response has no valid date") from exc
    current_date = today or datetime.now(timezone.utc).date()
    if rate_date > current_date:
        raise ValueError("NBRB USD rate response is dated in the future")

    try:
        official_rate = Decimal(str(payload["Cur_OfficialRate"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("NBRB USD rate response has no valid official rate") from exc
    if not official_rate.is_finite() or official_rate <= 0:
        raise ValueError("NBRB USD official rate must be finite and positive")

    scale = payload.get("Cur_Scale")
    if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
        raise ValueError("NBRB USD rate scale must be a positive integer")

    return rate_date.isoformat(), official_rate, scale


def _latest_usd_rate_statement(as_of: date):
    """Exclude invalid future-dated rows left by older worker versions."""

    return (
        select(ExchangeRate)
        .where(ExchangeRate.currency == "USD", ExchangeRate.rate_date <= as_of.isoformat())
        .order_by(ExchangeRate.rate_date.desc())
        .limit(1)
    )


def _cleanup_retention() -> None:
    now = datetime.now(timezone.utc)
    sold_cutoff = now - timedelta(days=30)
    upload_cutoff = now - timedelta(hours=24)
    with SessionLocal() as db:
        sold = db.scalars(select(Listing).where(
            Listing.status == "sold", Listing.sold_at.is_not(None), Listing.sold_at <= sold_cutoff,
        ).with_for_update(skip_locked=True)).all()
        for listing in sold:
            old_status = listing.status
            listing.status = "archived"
            listing.revision += 1
            db.add(ListingStatusEvent(
                listing_id=listing.id, actor_id=None, actor_kind="system", from_status=old_status,
                to_status="archived", revision=listing.revision, reason="sold_retention_expired",
            ))
        stale_photos = db.scalars(select(ListingPhoto).where(
            ListingPhoto.status.in_(["processing", "failed"]), ListingPhoto.created_at <= upload_cutoff,
        ).with_for_update(skip_locked=True)).all()
        expired_names: set[str] = set()
        expired_storage_names: set[str] = set()
        for photo in stale_photos:
            related_jobs = db.scalars(select(WorkerJob).where(
                WorkerJob.kind == "photo.process",
                WorkerJob.payload["photo_id"].as_string() == str(photo.id),
            ).with_for_update()).all()
            # A worker with a live lease may still be processing this row. Leave
            # it for the next retention pass rather than deleting its DB record
            # while the worker can still commit variants.
            if any(job.status == "running" and job.lease_until and job.lease_until > now for job in related_jobs):
                continue
            # Remove jobs before the photo row so cleanup remains valid if a
            # foreign key is added later, and never leaves dangling photo jobs.
            for job in related_jobs:
                db.delete(job)
            db.flush()
            db.delete(photo)
            db.flush()
            expired_names.add(photo.original_name)
            expired_storage_names.add(photo.storage_name)
        db.query(WorkerJob).filter(
            WorkerJob.status.in_(["succeeded", "failed"]), WorkerJob.created_at < now - timedelta(days=30),
        ).delete(synchronize_session=False)
        # Current abuse-control windows are at most one hour. Keep two days
        # of keys so cleanup cannot reset a live quota, while expired random
        # guest-device/IP fingerprints cannot accumulate indefinitely.
        db.query(RateLimitBucket).filter(
            RateLimitBucket.window_started < now - timedelta(days=2),
        ).delete(synchronize_session=False)
        db.commit()

    media_root = get_settings().media_root.resolve()
    quarantine = media_root / ".quarantine"
    if quarantine.exists():
        for path in quarantine.iterdir():
            if path.name in expired_names:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            elif path.is_file() and datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < upload_cutoff:
                path.unlink(missing_ok=True)

    for name in expired_storage_names:
        path = (media_root / name).resolve()
        if path != media_root and path.is_relative_to(media_root):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    with SessionLocal() as db:
        referenced_storage = set(db.scalars(select(ListingPhoto.storage_name)).all())
    for path in media_root.iterdir():
        if not path.is_dir() or path.name == ".quarantine":
            continue
        if path.name in referenced_storage:
            continue
        is_photo_dir = path.name.startswith(".photo-") and path.name.endswith(".tmp")
        if not is_photo_dir:
            try:
                uuid.UUID(hex=path.name)
                is_photo_dir = True
            except ValueError:
                pass
        try:
            stale = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < upload_cutoff
        except OSError:
            continue
        if is_photo_dir and stale:
            shutil.rmtree(path, ignore_errors=True)


def _next_notification_at(now: datetime, frequency: str) -> datetime:
    """Return a deterministic delivery bucket for a saved-search preference."""

    if frequency == "daily":
        local_now = now.astimezone(MINSK)
        target = local_now.replace(hour=9, minute=0, second=0, microsecond=0)
        if local_now >= target:
            target += timedelta(days=1)
        return target.astimezone(timezone.utc)
    if frequency == "weekly":
        days_until_next_monday = 7 - now.weekday()
        next_week = now + timedelta(days=days_until_next_monday)
        return next_week.replace(hour=0, minute=0, second=0, microsecond=0)
    return now


def _first_publication_at(db, listing: Listing) -> datetime | None:
    first = db.scalar(
        select(ListingStatusEvent.created_at)
        .where(ListingStatusEvent.listing_id == listing.id, ListingStatusEvent.to_status == "active")
        .order_by(ListingStatusEvent.created_at, ListingStatusEvent.id)
        .limit(1)
    )
    if first is not None and first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    return first


def _listing_url(listing: Listing) -> str:
    segment = listing.slug or str(listing.id)
    category = getattr(listing, "category_code", None) or "cars"
    if category != "cars":
        return f"{CATEGORY_PATHS[category]}/{segment}/{listing.id}"
    return f"/cars/{segment}/{segment}/{listing.id}"


def _enqueue_daily_notification_batch(db, saved_search: SavedSearch, listing: Listing, channel: str, available_at: datetime) -> None:
    period_date = available_at.astimezone(MINSK).date()
    period = period_date.isoformat()
    started_at = saved_search.subscription_started_at
    if started_at is None:
        return
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    subscription_started_at = started_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    subscription_key = started_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dedupe_key = f"saved-search:{saved_search.id}:channel:{channel}:daily:{period}:subscription:{subscription_key}"

    already_matched = db.scalar(
        select(SavedSearchNotificationMatch.id)
        .where(
            SavedSearchNotificationMatch.saved_search_id == saved_search.id,
            SavedSearchNotificationMatch.listing_id == listing.id,
        )
        .with_for_update()
    )
    if already_matched is not None:
        return

    db.execute(
        pg_insert(SavedSearchNotificationBatch).values(
            id=uuid.uuid4(),
            saved_search_id=saved_search.id,
            channel=channel,
            period=period_date,
            outbox_id=None,
        ).on_conflict_do_nothing(constraint="uq_saved_search_notification_batch_period")
    )
    batch = db.scalar(
        select(SavedSearchNotificationBatch)
        .where(
            SavedSearchNotificationBatch.saved_search_id == saved_search.id,
            SavedSearchNotificationBatch.channel == channel,
            SavedSearchNotificationBatch.period == period_date,
        )
        .with_for_update()
    )
    if batch is None:
        return

    outbox = None
    if batch.outbox_id is not None:
        outbox = db.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == batch.outbox_id)
            .with_for_update()
        )
    if outbox is not None:
        current_filters = saved_search_filters(saved_search)
        prior_payload = dict(outbox.payload or {})
        same_snapshot = (
            prior_payload.get("notification_frequency") == saved_search.notification_frequency
            and prior_payload.get("search_url") == saved_search.search_url
            and prior_payload.get("filters") == current_filters
            and prior_payload.get("subscription_started_at") == subscription_started_at
        )
        if outbox.status in {"delivered", "running"}:
            return
        if outbox.status == "queued" and same_snapshot:
            pass
        else:
            if outbox.status == "queued":
                outbox.status = "cancelled"
                outbox.last_error = "notification_preference_changed"
                outbox.locked_by = None
                outbox.lease_until = None
                stale_jobs = db.scalars(
                    select(WorkerJob)
                    .where(
                        WorkerJob.kind == "notification.deliver",
                        WorkerJob.payload["outbox_id"].as_string() == str(outbox.id),
                        WorkerJob.status.in_(["queued", "running"]),
                    )
                    .with_for_update()
                ).all()
                for job in stale_jobs:
                    job.status = "failed"
                    job.last_error = "notification_preference_changed"
                    job.locked_by = None
                    job.lease_until = None
            outbox = None

    base_payload = {
        "batch": True,
        "title": f"Новые объявления по поиску «{saved_search.name}»",
        "body": "Новые объявления по сохранённому поиску.",
        "url": saved_search.search_url,
        "search_url": saved_search.search_url,
        "filters": saved_search_filters(saved_search),
        "notification_frequency": saved_search.notification_frequency,
        "subscription_started_at": subscription_started_at,
        "period": period,
        "total_count": 0,
        "listings": [],
    }
    if outbox is None:
        insert = pg_insert(NotificationOutbox).values(
            id=uuid.uuid4(),
            dedupe_key=dedupe_key,
            saved_search_id=saved_search.id,
            conversation_id=None,
            user_id=saved_search.user_id,
            listing_id=None,
            channel=channel,
            status="queued",
            payload=base_payload,
            attempts=0,
            available_at=available_at,
        ).on_conflict_do_nothing(constraint="uq_notification_outbox_dedupe")
        db.execute(insert)
        outbox = db.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.dedupe_key == dedupe_key)
            .with_for_update()
        )
    if outbox is None or outbox.status != "queued":
        return
    batch.outbox_id = outbox.id

    listing_title = (listing.title or "Новое объявление").strip() or "Новое объявление"
    match_insert = pg_insert(SavedSearchNotificationMatch).values(
        id=uuid.uuid4(),
        saved_search_id=saved_search.id,
        listing_id=listing.id,
        listing_revision=listing.revision,
        outbox_id=outbox.id,
        title=listing_title[:240],
        url=_listing_url(listing),
    ).on_conflict_do_nothing(constraint="uq_saved_search_notification_match").returning(
        SavedSearchNotificationMatch.id
    )
    match_id = db.scalar(match_insert)
    if match_id is None:
        return

    matches = db.execute(
        select(SavedSearchNotificationMatch.listing_id, SavedSearchNotificationMatch.title, SavedSearchNotificationMatch.url)
        .where(SavedSearchNotificationMatch.outbox_id == outbox.id)
        .order_by(SavedSearchNotificationMatch.created_at, SavedSearchNotificationMatch.id)
        .limit(20)
    ).all()
    total_count = int(
        db.scalar(
            select(func.count(SavedSearchNotificationMatch.id)).where(
                SavedSearchNotificationMatch.outbox_id == outbox.id
            )
        )
        or 0
    )
    payload = dict(outbox.payload or {})
    payload["total_count"] = total_count
    payload["listings"] = [
        {"id": str(listing_id), "title": title, "url": url}
        for listing_id, title, url in matches
    ]
    outbox.payload = payload
    enqueue_job(
        db,
        "notification.deliver",
        f"notification.deliver:{outbox.id}",
        {"outbox_id": str(outbox.id)},
        run_after=available_at,
    )


def _match_saved_searches(listing_id: uuid.UUID, listing_revision: int) -> None:
    """Create one durable outbox item for every matching enabled search."""

    with SessionLocal() as db:
        listing = db.get(Listing, listing_id)
        # A seller edit turns a listing back into a draft and increments the
        # revision. In that case the publication event is no longer current.
        if listing is None or listing.status != "active" or listing.revision != listing_revision:
            return
        now = db.scalar(select(func.now()))
        if now is None:
            now = datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        first_publication_at = _first_publication_at(db, listing)
        searches = db.scalars(
            select(SavedSearch)
            .join(User, User.id == SavedSearch.user_id)
            .where(
                SavedSearch.status == "active",
                SavedSearch.notifications_enabled.is_(True),
                SavedSearch.notification_channel.is_not(None),
                User.status == "active",
            )
            .order_by(SavedSearch.id)
        ).all()
        email_settings = get_settings()
        email_sender = get_email_sender(email_settings)
        public_app_url = str(getattr(email_settings, "public_app_url", "") or "").strip()
        title = (listing.title or "Новое объявление").strip() or "Новое объявление"
        for saved_search in searches:
            # Older rows predate subscription_started_at. Preserve their
            # existing notification behavior; the publication boundary only
            # applies once the subscription has an explicit start timestamp.
            if first_publication_at is None:
                continue
            if saved_search.subscription_started_at is not None and (
                first_publication_at < saved_search.subscription_started_at
            ):
                continue
            if not saved_search_matches(db, saved_search, listing):
                continue
            channel = saved_search.notification_channel
            if channel not in {"web", "email"}:
                continue
            available_at = _next_notification_at(now, saved_search.notification_frequency)
            if saved_search.notification_frequency == "daily" and saved_search.subscription_started_at is not None:
                _enqueue_daily_notification_batch(db, saved_search, listing, channel, available_at)
                continue

            dedupe_key = f"saved-search:{saved_search.id}:listing:{listing.id}:channel:{channel}"
            payload = {
                "title": f"Новое объявление по поиску «{saved_search.name}»",
                "body": title,
                "url": saved_search.search_url,
                "listing_id": str(listing.id),
                "listing_revision": listing.revision,
                "notification_frequency": saved_search.notification_frequency,
                "search_url": saved_search.search_url,
                "filters": saved_search_filters(saved_search),
            }
            email_ready = False
            email_error = "email_provider_unconfigured"
            if channel == "email":
                if email_sender.is_configured:
                    email_error = "email_public_url_unconfigured"
                    if public_app_url:
                        user = db.get(User, saved_search.user_id)
                        contact = None
                        if user is not None and user.email:
                            contact = db.scalar(
                                select(VerifiedEmailContact).where(
                                    VerifiedEmailContact.user_id == user.id,
                                    VerifiedEmailContact.email == user.email,
                                )
                            )
                        email_error = "email_recipient_unverified"
                        if contact is not None:
                            try:
                                saved_search_email_content(payload, public_app_url)
                            except ValueError:
                                email_error = "invalid_notification_url"
                            else:
                                email_ready = True
            status = "queued" if channel == "web" or email_ready else "unsupported"
            insert = pg_insert(NotificationOutbox).values(
                id=uuid.uuid4(),
                dedupe_key=dedupe_key,
                saved_search_id=saved_search.id,
                user_id=saved_search.user_id,
                listing_id=listing.id,
                channel=channel,
                status=status,
                payload=payload,
                attempts=0,
                available_at=available_at,
                last_error=None if channel == "web" or email_ready else email_error,
            ).on_conflict_do_nothing(constraint="uq_notification_outbox_dedupe").returning(NotificationOutbox.id)
            outbox_id = db.scalar(insert)
            if outbox_id is not None and (channel == "web" or email_ready):
                db.execute(
                    pg_insert(SavedSearchNotificationMatch).values(
                        id=uuid.uuid4(),
                        saved_search_id=saved_search.id,
                        listing_id=listing.id,
                        listing_revision=listing.revision,
                        outbox_id=outbox_id,
                        title=title[:240],
                        url=_listing_url(listing),
                    ).on_conflict_do_nothing(constraint="uq_saved_search_notification_match")
                )
                enqueue_job(
                    db,
                    "notification.deliver",
                    f"notification.deliver:{outbox_id}",
                    {"outbox_id": str(outbox_id)},
                    run_after=available_at,
                )
        db.commit()


def _safe_email_error_code(error: Exception) -> str:
    if isinstance(error, EmailDeliveryUnavailable) and error.code in {
        "email_delivery_failed",
        "email_message_invalid",
        "email_provider_unconfigured",
        "email_public_url_unconfigured",
        "email_recipient_unverified",
        "invalid_notification_url",
    }:
        return error.code
    return "email_delivery_failed"


def _subscription_started_at_snapshot(saved_search: SavedSearch) -> str | None:
    started_at = saved_search.subscription_started_at
    if started_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _saved_search_delivery_snapshot(
    saved_search: SavedSearch, filters: dict[str, object]
) -> dict[str, object]:
    return {
        "id": saved_search.id,
        "status": saved_search.status,
        "notifications_enabled": saved_search.notifications_enabled,
        "notification_channel": saved_search.notification_channel,
        "notification_frequency": saved_search.notification_frequency,
        "search_url": saved_search.search_url,
        "filters": filters,
        "subscription_started_at": _subscription_started_at_snapshot(saved_search),
    }


def _cancel_running_notification(db, outbox: NotificationOutbox, error_code: str) -> None:
    outbox.status = "cancelled"
    outbox.last_error = error_code
    outbox.locked_by = None
    outbox.lease_until = None
    db.commit()


def _batch_listing_snapshot(db, outbox: NotificationOutbox, saved_search: SavedSearch) -> tuple[list[dict[str, str]], int]:
    matches = db.scalars(
        select(SavedSearchNotificationMatch)
        .where(SavedSearchNotificationMatch.outbox_id == outbox.id)
        .order_by(SavedSearchNotificationMatch.created_at, SavedSearchNotificationMatch.id)
        .with_for_update()
    ).all()
    valid: list[SavedSearchNotificationMatch] = []
    for match in matches:
        listing = db.scalar(select(Listing).where(Listing.id == match.listing_id).with_for_update())
        if (
            listing is None
            or listing.status != "active"
            or listing.revision != match.listing_revision
            or not saved_search_matches(db, saved_search, listing)
        ):
            # Keep the permanent match row, but remove this now-invalid item
            # from the pending batch so a later reapproval cannot alert again.
            match.outbox_id = None
            continue
        valid.append(match)
    total_count = len(valid)
    payload_listings = [{"id": str(item.listing_id), "title": item.title, "url": item.url} for item in valid[:20]]
    payload = dict(outbox.payload or {})
    payload["total_count"] = total_count
    payload["listings"] = payload_listings
    outbox.payload = payload
    return payload_listings, total_count


def _deliver_identity_email(outbox_id: uuid.UUID) -> None:
    """Deliver one verification or recovery email with retry-safe identity."""

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        outbox = db.scalar(
            select(IdentityEmailOutbox)
            .where(IdentityEmailOutbox.id == outbox_id)
            .with_for_update()
        )
        if outbox is None or outbox.status in {"delivered", "failed"}:
            return

        user = db.get(User, outbox.user_id)
        challenge_model = (
            EmailVerificationChallenge
            if outbox.message_type == "email_verification"
            else AccountRecoveryChallenge
        )
        challenge = db.get(challenge_model, outbox.challenge_id)
        if (
            user is None
            or user.status != "active"
            or challenge is None
            or challenge.user_id != outbox.user_id
            or challenge.consumed_at is not None
            or challenge.invalidated_at is not None
        ):
            outbox.status = "failed"
            outbox.last_error = "identity_challenge_inactive"
            outbox.locked_by = None
            outbox.lease_until = None
            db.commit()
            return
        expires_at = challenge.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            outbox.status = "failed"
            outbox.last_error = "identity_challenge_inactive"
            outbox.locked_by = None
            outbox.lease_until = None
            db.commit()
            return
        if outbox.message_type == "email_verification":
            valid_recipient = challenge.email == outbox.recipient
        else:
            contact = db.scalar(
                select(VerifiedEmailContact).where(
                    VerifiedEmailContact.user_id == user.id,
                    VerifiedEmailContact.email == user.email,
                )
            )
            valid_recipient = bool(contact and contact.email == outbox.recipient)
        if not valid_recipient:
            outbox.status = "failed"
            outbox.last_error = "identity_recipient_unavailable"
            outbox.locked_by = None
            outbox.lease_until = None
            db.commit()
            return

        sender = get_email_sender(get_settings())
        if not sender.is_configured:
            outbox.status = "failed"
            outbox.last_error = "email_provider_unconfigured"
            outbox.locked_by = None
            outbox.lease_until = None
            db.commit()
            return

        outbox.status = "running"
        outbox.attempts += 1
        outbox.locked_by = f"worker:{os.getpid()}"
        outbox.lease_until = now + LEASE
        recipient, subject, body, dedupe_key = (
            outbox.recipient,
            outbox.subject,
            outbox.body,
            outbox.dedupe_key,
        )
        db.commit()

    try:
        sender.send_email(recipient, subject, body, idempotency_key=dedupe_key)
    except Exception as exc:
        error_code = _safe_email_error_code(exc)
        with SessionLocal() as db:
            outbox = db.scalar(
                select(IdentityEmailOutbox)
                .where(IdentityEmailOutbox.id == outbox_id)
                .with_for_update()
            )
            if outbox is not None and outbox.status == "running":
                outbox.status = "queued"
                outbox.last_error = error_code
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
        raise EmailDeliveryUnavailable(error_code) from None

    with SessionLocal() as db:
        outbox = db.scalar(
            select(IdentityEmailOutbox)
            .where(IdentityEmailOutbox.id == outbox_id)
            .with_for_update()
        )
        if outbox is not None and outbox.status == "running":
            outbox.status = "delivered"
            outbox.delivered_at = datetime.now(timezone.utc)
            outbox.last_error = None
            outbox.locked_by = None
            outbox.lease_until = None
            # The challenge stores only a digest. Remove the delivered token
            # from the outbox once retries are no longer needed.
            outbox.body = ""
            db.commit()


def _deliver_notification(outbox_id: uuid.UUID) -> None:
    """Deliver an email or materialise a web notification exactly once."""

    with SessionLocal() as db:
        probe = db.get(NotificationOutbox, outbox_id)
        if probe is None or probe.status in {"delivered", "failed", "unsupported", "cancelled"}:
            return
        saved_search = None
        if probe.saved_search_id is not None:
            saved_search = db.scalar(
                select(SavedSearch)
                .where(SavedSearch.id == probe.saved_search_id)
                .with_for_update()
            )
        outbox = db.scalar(
            select(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .with_for_update()
        )
        if outbox is None or outbox.status in {"delivered", "failed", "unsupported", "cancelled"}:
            return
        saved_search_id = outbox.saved_search_id
        if outbox.status == "running" and outbox.lease_until is not None:
            lease_until = outbox.lease_until
            if lease_until.tzinfo is None:
                lease_until = lease_until.replace(tzinfo=timezone.utc)
            if lease_until > datetime.now(timezone.utc):
                return

        user = db.get(User, outbox.user_id)
        if user is None or user.status != "active":
            outbox.status = "failed"
            outbox.last_error = "notification_recipient_inactive"
            outbox.locked_by = None
            outbox.lease_until = None
            db.commit()
            return

        payload = dict(outbox.payload or {})
        is_batch = bool(payload.get("batch"))
        digest_listings: list[dict[str, str]] = []
        single_listing_snapshot: list[dict[str, str]] = []
        single_listing_revision: int | None = None
        saved_search_snapshot: dict[str, object] | None = None
        digest_total = 0
        if outbox.saved_search_id is not None:
            try:
                current_filters = saved_search_filters(saved_search) if saved_search is not None else None
            except ValueError:
                current_filters = None
            current_subscription_started_at = (
                _subscription_started_at_snapshot(saved_search) if saved_search is not None else None
            )
            if (
                saved_search is None
                or current_filters is None
                or saved_search.user_id != user.id
                or saved_search.status != "active"
                or not saved_search.notifications_enabled
                or saved_search.notification_channel != outbox.channel
                or (payload.get("notification_frequency") is not None and saved_search.notification_frequency != payload["notification_frequency"])
                or (payload.get("search_url") is not None and saved_search.search_url != payload["search_url"])
                or (payload.get("filters") is not None and current_filters != payload["filters"])
                or ("subscription_started_at" in payload and current_subscription_started_at != payload["subscription_started_at"])
            ):
                outbox.status = "cancelled" if is_batch else "unsupported"
                outbox.last_error = "notification_preference_changed"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return
            saved_search_snapshot = _saved_search_delivery_snapshot(saved_search, current_filters)
            if is_batch:
                digest_listings, digest_total = _batch_listing_snapshot(db, outbox, saved_search)
                if digest_total < 1:
                    outbox.status = "unsupported"
                    outbox.last_error = "notification_batch_empty"
                    outbox.locked_by = None
                    outbox.lease_until = None
                    db.commit()
                    return
            elif outbox.listing_id is not None:
                listing = db.scalar(select(Listing).where(Listing.id == outbox.listing_id).with_for_update())
                expected_revision = payload.get("listing_revision")
                if (
                    listing is None
                    or listing.status != "active"
                    or (expected_revision is not None and listing.revision != int(expected_revision))
                    or not saved_search_matches(db, saved_search, listing)
                ):
                    outbox.status = "unsupported"
                    outbox.last_error = "listing_no_longer_matches"
                    outbox.locked_by = None
                    outbox.lease_until = None
                    db.commit()
                    return
                single_listing_revision = listing.revision
                single_listing_snapshot = [{
                    "id": str(listing.id),
                    "title": " ".join(str(listing.title or payload.get("body") or "Новое объявление").split())[:240],
                    "url": _listing_url(listing),
                }]

        if outbox.channel == "email":
            if not notification_delivery_allowed(db, outbox.user_id, "email"):
                outbox.status = "unsupported"
                outbox.last_error = "email_preference_disabled"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return
            if (
                saved_search is None
                or saved_search.user_id != user.id
                or saved_search.status != "active"
                or not saved_search.notifications_enabled
                or saved_search.notification_channel != "email"
            ):
                outbox.status = "unsupported"
                outbox.last_error = "email_preference_disabled"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return

            contact = None
            if user.email:
                contact = db.scalar(
                    select(VerifiedEmailContact).where(
                        VerifiedEmailContact.user_id == user.id,
                        VerifiedEmailContact.email == user.email,
                    )
                )
            if contact is None or contact.email != user.email:
                outbox.status = "unsupported"
                outbox.last_error = "email_recipient_unverified"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return

            settings = get_settings()
            public_app_url = str(getattr(settings, "public_app_url", "") or "").strip()
            if not public_app_url:
                outbox.status = "unsupported"
                outbox.last_error = "email_public_url_unconfigured"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return
            sender = get_email_sender(settings)
            if not sender.is_configured:
                outbox.status = "unsupported"
                outbox.last_error = "email_provider_unconfigured"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return

            try:
                if is_batch:
                    payload["listings"] = digest_listings
                    subject, body = saved_search_digest_email_content(payload, public_app_url, digest_total)
                else:
                    subject, body = saved_search_email_content(payload, public_app_url)
            except ValueError:
                outbox.status = "unsupported"
                outbox.last_error = "invalid_notification_url"
                outbox.locked_by = None
                outbox.lease_until = None
                db.commit()
                return

            if not is_batch:
                from app.managed_content import render_notification_template
                subject, body = render_notification_template(db, "saved_search_email", {
                    "listing_title": " ".join(str(payload.get("body") or "Новое объявление").split())[:2000],
                    "listing_url": public_app_url.rstrip("/") + str(payload.get("url") or "/cars"),
                    "search_name": saved_search.name,
                }, default_subject=subject, default_body=body)

            outbox.status = "running"
            outbox.attempts += 1
            delivery_worker_id = f"worker:{os.getpid()}"
            outbox.locked_by = delivery_worker_id
            outbox.lease_until = datetime.now(timezone.utc) + LEASE
            recipient = contact.email
            dedupe_key = outbox.dedupe_key
            db.commit()

            with SessionLocal() as guard_db:
                guarded_search = guard_db.scalar(
                    select(SavedSearch)
                    .where(SavedSearch.id == saved_search_id)
                    .with_for_update()
                )
                guarded_outbox = guard_db.scalar(
                    select(NotificationOutbox)
                    .where(NotificationOutbox.id == outbox_id)
                    .with_for_update()
                )
                if (
                    guarded_outbox is None
                    or guarded_outbox.status != "running"
                    or guarded_outbox.locked_by != delivery_worker_id
                ):
                    return

                try:
                    guarded_filters = (
                        saved_search_filters(guarded_search)
                        if guarded_search is not None
                        else None
                    )
                except ValueError:
                    guarded_filters = None
                guarded_snapshot = (
                    _saved_search_delivery_snapshot(guarded_search, guarded_filters)
                    if guarded_search is not None and guarded_filters is not None
                    else None
                )
                if (
                    saved_search_snapshot is None
                    or guarded_snapshot != saved_search_snapshot
                ):
                    _cancel_running_notification(
                        guard_db, guarded_outbox, "notification_preference_changed"
                    )
                    return

                guarded_user = guard_db.scalar(
                    select(User)
                    .where(User.id == guarded_outbox.user_id)
                    .with_for_update()
                )
                if (
                    guarded_user is None
                    or guarded_user.status != "active"
                    or guarded_user.email != recipient
                    or not notification_delivery_allowed(
                        guard_db, guarded_outbox.user_id, "email"
                    )
                ):
                    _cancel_running_notification(
                        guard_db, guarded_outbox, "email_preference_disabled"
                    )
                    return
                guarded_contact = guard_db.scalar(
                    select(VerifiedEmailContact)
                    .where(
                        VerifiedEmailContact.user_id == guarded_user.id,
                        VerifiedEmailContact.email == guarded_user.email,
                    )
                    .with_for_update()
                )
                if guarded_contact is None or guarded_contact.email != recipient:
                    _cancel_running_notification(
                        guard_db, guarded_outbox, "email_recipient_unverified"
                    )
                    return

                if is_batch:
                    guarded_listings, guarded_total = _batch_listing_snapshot(
                        guard_db, guarded_outbox, guarded_search
                    )
                    if (
                        guarded_listings != digest_listings
                        or guarded_total != digest_total
                    ):
                        _cancel_running_notification(
                            guard_db, guarded_outbox, "notification_batch_changed"
                        )
                        return
                elif guarded_outbox.listing_id is not None:
                    guarded_listing = guard_db.scalar(
                        select(Listing)
                        .where(Listing.id == guarded_outbox.listing_id)
                        .with_for_update()
                    )
                    if (
                        guarded_listing is None
                        or guarded_listing.status != "active"
                        or guarded_listing.revision != single_listing_revision
                        or not saved_search_matches(
                            guard_db, guarded_search, guarded_listing
                        )
                    ):
                        _cancel_running_notification(
                            guard_db, guarded_outbox, "listing_no_longer_matches"
                        )
                        return

                try:
                    sender.send_email(
                        recipient, subject, body, idempotency_key=dedupe_key
                    )
                except Exception as exc:
                    error_code = _safe_email_error_code(exc)
                    guard_db.rollback()
                    with SessionLocal() as retry_db:
                        retry_outbox = retry_db.scalar(
                            select(NotificationOutbox)
                            .where(NotificationOutbox.id == outbox_id)
                            .with_for_update()
                        )
                        if (
                            retry_outbox is not None
                            and retry_outbox.status == "running"
                        ):
                            retry_outbox.status = "queued"
                            retry_outbox.last_error = error_code
                            retry_outbox.locked_by = None
                            retry_outbox.lease_until = None
                            retry_db.commit()
                    raise EmailDeliveryUnavailable(error_code) from None

                guarded_outbox.status = "delivered"
                guarded_outbox.last_error = None
                guarded_outbox.delivered_at = datetime.now(timezone.utc)
                guarded_outbox.locked_by = None
                guarded_outbox.lease_until = None
                guard_db.commit()
            return

        if outbox.channel != "web":
            outbox.status = "unsupported"
            outbox.last_error = "notification_channel_not_supported"
            db.commit()
            return

        if not notification_delivery_allowed(db, outbox.user_id, "web"):
            outbox.status = "unsupported"
            outbox.last_error = "web_preference_disabled"
            outbox.locked_by = None
            outbox.lease_until = None
            db.commit()
            return

        outbox.status = "running"
        outbox.attempts += 1
        outbox.locked_by = f"worker:{os.getpid()}"
        outbox.lease_until = datetime.now(timezone.utc) + LEASE
        db.execute(
            pg_insert(UserNotification).values(
                id=uuid.uuid4(),
                outbox_id=outbox.id,
                user_id=outbox.user_id,
                saved_search_id=outbox.saved_search_id,
                conversation_id=outbox.conversation_id,
                listing_id=outbox.listing_id,
                title=str(payload.get("title") or "Новое объявление")[:240],
                body=str(payload.get("body") or "Новое объявление"),
                url=str(payload.get("url") or "/cars")[:2048],
                listings=digest_listings if is_batch else single_listing_snapshot,
                total_count=digest_total if is_batch else 1,
            ).on_conflict_do_nothing(constraint="uq_user_notification_outbox")
        )
        outbox.status = "delivered"
        outbox.delivered_at = datetime.now(timezone.utc)
        outbox.last_error = None
        outbox.locked_by = None
        outbox.lease_until = None
        db.commit()


def _run_job(job_id: uuid.UUID, worker_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(WorkerJob, job_id)
        if job is None or job.status != "running" or job.locked_by != worker_id:
            return
        kind, payload = job.kind, dict(job.payload or {})
    try:
        if kind == "photo.process":
            _make_variants(uuid.UUID(payload["photo_id"]))
        elif kind == "rates.refresh":
            _refresh_usd_rate()
        elif kind == "cleanup.retention":
            _cleanup_retention()
        elif kind == "saved-search.match":
            _match_saved_searches(uuid.UUID(payload["listing_id"]), int(payload["listing_revision"]))
        elif kind == "notification.deliver":
            _deliver_notification(uuid.UUID(payload["outbox_id"]))
        elif kind == "identity.email.deliver":
            _deliver_identity_email(uuid.UUID(payload["outbox_id"]))
        else:
            raise PermanentJobError(f"Unsupported job kind: {kind}")
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(WorkerJob, job_id)
            if job is None:
                return
            notification_outbox = None
            if kind == "notification.deliver":
                try:
                    notification_outbox = db.get(NotificationOutbox, uuid.UUID(payload["outbox_id"]))
                except (KeyError, ValueError):
                    notification_outbox = None
            is_saved_search_email = bool(
                notification_outbox is not None
                and notification_outbox.channel == "email"
            )
            delivery_error = (
                _safe_email_error_code(exc)
                if kind == "identity.email.deliver" or is_saved_search_email
                else None
            )
            job.last_error = delivery_error or str(exc)[:500]
            job.locked_by = None
            job.lease_until = None
            terminal_failure = isinstance(exc, PermanentJobError) or job.attempts >= job.max_attempts
            if terminal_failure:
                job.status = "failed"
                if kind == "photo.process":
                    photo = db.get(ListingPhoto, uuid.UUID(payload["photo_id"]))
                    if photo and photo.status in {"processing", "ready"}:
                        photo.status = "failed"
                elif kind == "identity.email.deliver":
                    try:
                        outbox = db.get(IdentityEmailOutbox, uuid.UUID(payload["outbox_id"]))
                    except (KeyError, ValueError):
                        outbox = None
                    if outbox is not None and outbox.status != "delivered":
                        outbox.status = "failed"
                        outbox.last_error = delivery_error or "email_delivery_failed"
                        outbox.locked_by = None
                        outbox.lease_until = None
                elif is_saved_search_email and notification_outbox is not None:
                    if notification_outbox.status != "delivered":
                        notification_outbox.status = "failed"
                        notification_outbox.last_error = delivery_error or "email_delivery_failed"
                        notification_outbox.locked_by = None
                        notification_outbox.lease_until = None
            else:
                job.status = "queued"
                database_now = db.scalar(select(func.now()))
                job.run_after = database_now + timedelta(seconds=min(60 * (2 ** (job.attempts - 1)), 3600))
            db.commit()
        log_event(
            logger,
            logging.WARNING,
            "worker_job_failed",
            job_id=str(job_id),
            job_kind=kind,
            attempt=job.attempts if job else None,
            error_type=type(exc).__name__,
        )
        from app.error_monitoring import capture_safe_error
        capture_safe_error("worker", type(exc).__name__)
        return
    with SessionLocal() as db:
        job = db.get(WorkerJob, job_id)
        if job:
            job.status = "succeeded"
            job.locked_by = None
            job.lease_until = None
            job.last_error = None
            db.commit()


def _schedule_daily_rates() -> None:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        rate_pending = db.scalar(select(WorkerJob.id).where(
            WorkerJob.kind == "rates.refresh",
            WorkerJob.status.in_(["queued", "running"]),
        ).limit(1))
        latest = db.scalar(_latest_usd_rate_statement(now.date()))
        refresh_rate = not rate_pending
        if refresh_rate and latest:
            fetched_at = latest.fetched_at
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            refresh_rate = fetched_at <= now - timedelta(hours=20)
        if refresh_rate:
            key = f"rates.refresh:{now.date().isoformat()}"
            insert = pg_insert(WorkerJob).values(
                id=uuid.uuid4(), job_key=key, kind="rates.refresh", payload={}, status="queued", attempts=0,
                max_attempts=6, run_after=now,
            )
            if latest is None:
                statement = insert.on_conflict_do_update(
                    constraint="uq_worker_job_key",
                    set_={
                        "status": "queued",
                        "attempts": 0,
                        "run_after": now,
                        "lease_until": None,
                        "locked_by": None,
                        "last_error": None,
                        "updated_at": now,
                    },
                    where=WorkerJob.status == "succeeded",
                )
            else:
                statement = insert.on_conflict_do_nothing(constraint="uq_worker_job_key")
            db.execute(statement)
        cleanup_pending = db.scalar(select(WorkerJob.id).where(
            WorkerJob.kind == "cleanup.retention", WorkerJob.status.in_(["queued", "running"]),
        ).limit(1))
        if not cleanup_pending:
            cleanup_key = f"cleanup.retention:{now.date().isoformat()}"
            db.execute(pg_insert(WorkerJob).values(
                id=uuid.uuid4(), job_key=cleanup_key, kind="cleanup.retention", payload={}, status="queued",
                attempts=0, max_attempts=4, run_after=now,
            ).on_conflict_do_nothing(constraint="uq_worker_job_key"))
        db.commit()


def run_forever() -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    log_event(logger, logging.INFO, "worker_started", worker_id=worker_id)
    while True:
        try:
            _schedule_daily_rates()
            with engine.connect() as lock_connection:
                got_lock = lock_connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
                if not got_lock:
                    time.sleep(2)
                    continue
                try:
                    job_id = _claim_one(worker_id)
                    if job_id is None:
                        time.sleep(2)
                    else:
                        _run_job(job_id, worker_id)
                finally:
                    lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
                    lock_connection.commit()
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "worker_loop_failed",
                error_type=type(exc).__name__,
            )
            time.sleep(3)


if __name__ == "__main__":
    run_forever()
