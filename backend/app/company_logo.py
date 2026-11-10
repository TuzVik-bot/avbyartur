"""Company logo storage: re-encoded WebP files under MEDIA_ROOT/company-logos."""

import io
import logging
import re
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.logging_config import configure_json_logger, log_event
from app.services import fail

LOGO_DIRECTORY = "company-logos"
LOGO_URL_PREFIX = "/api/v1/company-logos/"
LOGO_MAX_SIDE = 1024
LOGO_MAX_PIXELS = 16_000_000
LOGO_WEBP_QUALITY = 88
ALLOWED_LOGO_TYPES = {
    "JPEG": {"image/jpeg", "image/jpg"},
    "PNG": {"image/png"},
    "WEBP": {"image/webp"},
}
_STORAGE_NAME = re.compile(r"[a-f0-9]{32}\.webp")
logger = configure_json_logger(__name__)


def logo_url(storage_name: str | None) -> str | None:
    return f"{LOGO_URL_PREFIX}{storage_name}" if storage_name else None


def logo_path(media_root: Path, storage_name: str) -> Path | None:
    """Resolve a stored logo name, refusing anything but a generated WebP name."""

    if not _STORAGE_NAME.fullmatch(storage_name):
        return None
    root = media_root.resolve()
    path = (root / LOGO_DIRECTORY / storage_name).resolve()
    return path if path.is_relative_to(root) else None


def _check_source(image: Image.Image, content_type: str | None) -> None:
    if image.format not in ALLOWED_LOGO_TYPES:
        fail(415, "unsupported_photo", "Upload a JPEG, PNG, or WebP logo")
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared not in {"", "application/octet-stream"} and declared not in ALLOWED_LOGO_TYPES[image.format]:
        fail(415, "photo_mime_mismatch", "Logo content type does not match image data")
    if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1:
        fail(415, "animated_photo", "Animated images are not supported")
    if image.width * image.height > LOGO_MAX_PIXELS:
        fail(413, "photo_pixel_limit", "Logo exceeds the pixel limit")


def sanitize_logo(raw: bytes, content_type: str | None) -> bytes:
    """Validate an uploaded logo and re-encode it to WebP without metadata."""

    try:
        with Image.open(io.BytesIO(raw)) as image:
            _check_source(image, content_type)
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            clean = ImageOps.exif_transpose(image).convert("RGBA" if has_alpha else "RGB")
            clean.thumbnail((LOGO_MAX_SIDE, LOGO_MAX_SIDE), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            clean.save(output, format="WEBP", quality=LOGO_WEBP_QUALITY, method=5)
            return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        fail(413, "photo_pixel_limit", "Logo exceeds the pixel limit")
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        fail(415, "invalid_photo", "Logo data is invalid")


def store_logo(media_root: Path, data: bytes) -> tuple[str, Path]:
    storage_name = f"{uuid.uuid4().hex}.webp"
    target = logo_path(media_root, storage_name)
    if target is None:
        fail(500, "media_storage_unavailable", "Logo storage is unavailable")
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.parent.chmod(0o700)
        target.write_bytes(data)
        target.chmod(0o600)
    except OSError:
        target.unlink(missing_ok=True)
        fail(500, "media_storage_unavailable", "Logo storage is unavailable")
    return storage_name, target


def remove_logo(media_root: Path, storage_name: str | None) -> None:
    if not storage_name:
        return
    path = logo_path(media_root, storage_name)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log_event(logger, logging.ERROR, "company_logo_cleanup_failed", error_type=type(exc).__name__)
