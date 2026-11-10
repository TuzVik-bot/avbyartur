"""Ingest used-car listings from ab.onliner.by (автобарахолка Onlíner).

The project holds the operator's written permission from Onliner (October
2026) to mirror a bounded selection of adverts: ten used cars per
manufacturer across all Belarusian cities, including photos, descriptions,
and seller contacts.  Everything here is deliberately single-connection and
throttled; the source API is an internal frontend endpoint, so be polite:
one request per interval, retry with backoff, no parallelism.

Public entry points:

* :class:`OnlinerClient` – throttled HTTP client for the ``sdapi`` proxy.
* :func:`collect_snapshot` – write a JSONL snapshot of fresh adverts.
* :func:`import_snapshot` / :func:`import_record` – publish snapshot rows
  as active listings with processed photos (idempotent by slug).
* :func:`sync_existing` – refresh prices and retire closed adverts.
* :func:`discover_new` – import adverts that appeared since the last run.
"""

from __future__ import annotations

import io
import json
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.listing_price_history import record_active_listing_price_state
from app.models import (
    AuditEvent,
    CatalogMake,
    CatalogModel,
    Listing,
    ListingPhoto,
    ListingStatusEvent,
    LocationCity,
    LocationRegion,
    User,
)
from app.services import enqueue_saved_search_match

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 avtorinok-import/1.0"
)
MAX_HTTP_ATTEMPTS = 4
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
SNAPSHOT_FORMAT = "onliner-snapshot-v1"
SOURCE_NOTE = "Источник: Onlíner (ab.onliner.by). Оригинал объявления: {url}"

TRANSMISSION_MAP = {"automatic": "automatic", "mechanical": "manual"}
ENGINE_FUEL_MAP = {"gasoline": "petrol", "diesel": "diesel", "electric": "electric"}
COLOR_MAP = {
    "black": "black",
    "white": "white",
    "silver": "silver",
    "grey": "gray",
    "red": "red",
    "orange": "orange",
    "yellow": "yellow",
    "green": "green",
    "blue": "blue",
    "violet": "purple",
    "brown": "brown",
    "beige": "beige",
    "skyblue": "other",
    "maroon": "other",
    "golden": "other",
    "other": "other",
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "HEIF", "HEIC"}
# Photos in Onliner advert payloads are served from this CDN host only.
ONLINER_IMAGE_HOSTS = frozenset({"content.onliner.by"})
MAX_IMAGE_REDIRECTS = 3
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}

_Result = TypeVar("_Result")


@dataclass(frozen=True)
class _ImageHop:
    body: bytes
    location: str | None


class OnlinerFetchError(RuntimeError):
    """A request to the source failed after retries."""


class OnlinerBlockedError(OnlinerFetchError):
    """The source answered 403; collection must stop."""


class OnlinerClient:
    """Throttled single-connection client for the ab.onliner.by JSON API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        interval_seconds: float | None = None,
        image_interval_seconds: float = 0.25,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.onliner_base_url).rstrip("/")
        interval = (
            settings.onliner_request_interval_seconds
            if interval_seconds is None
            else interval_seconds
        )
        self._interval = max(0.05, float(interval))
        self._image_interval = max(0.05, float(image_interval_seconds))
        self._sleep = sleep
        self._last_api_at = 0.0
        self._last_image_at = 0.0
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "OnlinerClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _throttle(self, *, image: bool) -> None:
        interval = self._image_interval if image else self._interval
        last = self._last_image_at if image else self._last_api_at
        wait = last + interval - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        now = time.monotonic()
        if image:
            self._last_image_at = now
        else:
            self._last_api_at = now

    def _retry(self, url: str, *, image: bool, send: Callable[[], tuple[int, _Result]]) -> tuple[int, _Result]:
        last_error: Exception | None = None
        for attempt in range(MAX_HTTP_ATTEMPTS):
            self._throttle(image=image)
            try:
                status, result = send()
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if status < 400 or status == 404:
                    return status, result
                if status == 403:
                    raise OnlinerBlockedError(f"HTTP 403 for {url}")
                last_error = OnlinerFetchError(f"HTTP {status} for {url}")
                if status not in RETRY_STATUS_CODES:
                    raise last_error
            self._sleep(min(30.0, 2.0**attempt + 1.0))
        raise OnlinerFetchError(
            f"{url} failed after {MAX_HTTP_ATTEMPTS} attempts: {last_error}"
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        def send() -> tuple[int, httpx.Response]:
            response = self._http.request(method, url, params=params)
            return response.status_code, response

        return self._retry(url, image=False, send=send)[1]

    def dictionaries(self) -> dict:
        return self._request("GET", "/dictionaries").json()

    def get_advert(self, advert_id: int | str) -> dict | None:
        response = self._request("GET", f"/adverts/{advert_id}")
        if response.status_code == 404:
            return None
        return response.json()

    def get_phones(self, advert_id: int | str) -> list[str]:
        response = self._request("GET", f"/vehicles/{advert_id}/phones")
        if response.status_code == 404:
            return []
        payload = response.json()
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, str)]
        return []

    def search_used(
        self, manufacturer_id: int | str, *, limit: int, page: int = 1
    ) -> dict:
        params = {
            "extended": "true",
            "limit": str(limit),
            "page": str(page),
            "state[]": "owned",
            "car[0][manufacturer]": str(manufacturer_id),
        }
        payload = self._request("GET", "/search/vehicles", params=params).json()
        return payload if isinstance(payload, dict) else {}

    def download_image(self, url: str, *, max_bytes: int) -> bytes:
        """Fetch a photo from the Onliner CDN; every redirect hop is re-validated."""
        current = _allowed_image_url(url)
        for _hop in range(MAX_IMAGE_REDIRECTS + 1):
            target = current
            status, hop = self._retry(
                str(target), image=True, send=partial(self._image_hop, target, max_bytes)
            )
            if status == 404:
                raise OnlinerFetchError(f"image not found: {url}")
            if status not in REDIRECT_STATUS_CODES:
                return hop.body
            if not hop.location:
                raise OnlinerFetchError(f"image redirect without location: {url}")
            current = _allowed_image_url(str(target.join(hop.location)))
        raise OnlinerFetchError(f"image redirected too many times: {url}")

    def _image_hop(self, url: httpx.URL, max_bytes: int) -> tuple[int, _ImageHop]:
        with self._http.stream(
            "GET", url, follow_redirects=False, headers={"Accept": "image/*"}
        ) as response:
            status = response.status_code
            if status in REDIRECT_STATUS_CODES:
                return status, _ImageHop(b"", response.headers.get("location"))
            if status >= 300:
                return status, _ImageHop(b"", None)
            return status, _ImageHop(_read_capped(response, max_bytes, url), None)


def _allowed_image_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError) as exc:
        raise OnlinerFetchError(f"invalid image url: {url}") from exc
    if (
        parsed.scheme != "https"
        or parsed.host not in ONLINER_IMAGE_HOSTS
        or parsed.userinfo
        or parsed.port not in (None, 443)
    ):
        raise OnlinerFetchError(f"image url is not on the Onliner CDN: {url}")
    return parsed


def _read_capped(response: httpx.Response, max_bytes: int, url: httpx.URL) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise OnlinerFetchError(f"image exceeds size limit: {url}")
    chunks: list[bytes] = []
    received = 0
    for chunk in response.iter_bytes():
        received += len(chunk)
        if received > max_bytes:
            raise OnlinerFetchError(f"image exceeds size limit: {url}")
        chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class OnlinerRecord:
    source_id: str
    html_url: str
    manufacturer_name: str
    manufacturer_slug: str
    model_name: str
    model_slug: str
    generation_name: str | None
    year: int | None
    mileage_km: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    condition: str
    damaged: bool
    color: str | None
    engine_volume_l: Decimal | None
    power_hp: int | None
    description: str
    price_amount: Decimal
    currency: str
    exchange: bool | None
    customs_status: str | None
    seller_name: str | None
    contact_phone: str
    call_hours: str | None
    city_name: str | None
    region_name: str | None
    equipment_ids: tuple[str, ...]
    image_urls: tuple[str, ...]
    created_at: str | None
    updated_at: str | None

    @property
    def slug(self) -> str:
        return f"onliner-{self.source_id}"

    @property
    def title(self) -> str:
        return " ".join(
            part
            for part in (
                self.manufacturer_name,
                self.model_name,
                str(self.year) if self.year else "",
            )
            if part
        ).strip()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _price(price_block: dict) -> tuple[Decimal | None, str | None]:
    amount = _decimal(price_block.get("amount"))
    currency = str(price_block.get("currency") or "").upper()
    if amount is not None and amount > 0 and currency in {"USD", "BYN"}:
        return amount, currency
    converted = price_block.get("converted") or {}
    for fallback in ("USD", "BYN"):
        block = converted.get(fallback) or {}
        fallback_amount = _decimal(block.get("amount"))
        if fallback_amount is not None and fallback_amount > 0:
            return fallback_amount, fallback
    return None, None


def _fuel(engine: dict) -> str | None:
    if engine.get("hybrid"):
        return "hybrid"
    fuel_type = ENGINE_FUEL_MAP.get(str(engine.get("type") or ""))
    if fuel_type:
        return fuel_type
    if engine.get("gas"):
        return "lpg"
    return None


def _call_hours(call: dict) -> str | None:
    start = str(call.get("from") or "").split("+")[0]
    end = str(call.get("to") or "").split("+")[0]
    if start and end:
        return f"{start}–{end}"
    return None


def _image_urls(detail: dict) -> tuple[str, ...]:
    urls: list[str] = []
    for image in detail.get("images") or []:
        if isinstance(image, dict) and isinstance(image.get("original"), str):
            urls.append(image["original"])
    return tuple(urls[: get_settings().onliner_max_photos])


def _equipment_ids(detail: dict) -> tuple[str, ...]:
    ids: list[str] = []
    for section in detail.get("equipment") or []:
        if not isinstance(section, dict):
            continue
        for item in section.get("items") or []:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
    return tuple(ids)


def parse_advert(detail: dict, phones: list[str]) -> OnlinerRecord:
    source_id = str(detail.get("id") or "").strip()
    if not source_id.isdigit():
        raise ValueError("advert has no numeric id")
    specs = detail.get("specs") or {}
    engine = specs.get("engine") or {}
    amount, currency = _price(detail.get("price") or {})
    if amount is None or currency is None:
        raise ValueError(f"advert {source_id} has no usable price")
    state = str(specs.get("state") or "").strip()
    manufacturer = detail.get("manufacturer") or {}
    model = detail.get("model") or {}
    generation = detail.get("generation") or {}
    seller = detail.get("seller") or {}
    location = detail.get("location") or {}
    deal = detail.get("deal_terms") or {}
    city = location.get("city") or {}
    region = location.get("region") or {}
    odometer = specs.get("odometer") or {}
    power = engine.get("power") or {}
    phone = next((item for item in phones if item and not item.endswith("*")), "")
    return OnlinerRecord(
        source_id=source_id,
        html_url=str(detail.get("html_url") or "").strip(),
        manufacturer_name=str(manufacturer.get("name") or "").strip(),
        manufacturer_slug=str(manufacturer.get("slug") or "").strip(),
        model_name=str(model.get("name") or "").strip(),
        model_slug=str(model.get("slug") or "").strip(),
        generation_name=str(generation.get("name") or "").strip() or None,
        year=_int(specs.get("year")),
        mileage_km=_int(odometer.get("value"))
        if str(odometer.get("unit") or "km") == "km"
        else None,
        fuel=_fuel(engine),
        transmission=TRANSMISSION_MAP.get(str(specs.get("transmission") or "")),
        drive=str(specs.get("drivetrain") or "").strip() or None,
        condition="new" if state == "new" else "used",
        damaged=state == "emergency",
        color=COLOR_MAP.get(str(specs.get("color") or "")),
        engine_volume_l=_decimal(engine.get("capacity")),
        power_hp=_int(power.get("value"))
        if str(power.get("unit") or "horse") == "horse"
        else None,
        description=str(detail.get("description") or "").strip(),
        price_amount=amount,
        currency=currency,
        exchange=deal.get("exchange")
        if isinstance(deal.get("exchange"), bool)
        else None,
        customs_status="cleared_rb"
        if deal.get("customs_clearance") is True
        else "uncleared"
        if deal.get("customs_clearance") is False
        else None,
        seller_name=str(seller.get("name") or "").strip() or None,
        contact_phone=phone,
        call_hours=_call_hours(seller.get("call") or {}),
        city_name=str(city.get("name") or "").strip() or None,
        region_name=str(region.get("name") or "").strip() or None,
        equipment_ids=_equipment_ids(detail),
        image_urls=_image_urls(detail),
        created_at=str(detail.get("created_at") or "") or None,
        updated_at=str(detail.get("updated_at") or "") or None,
    )


def _selected_manufacturers(dictionaries: dict, spec: str) -> list[dict]:
    spec = (spec or "all").strip().lower()
    if spec.startswith("top"):
        makes = dictionaries.get("top_manufacturer") or []
        _, _, limit_raw = spec.partition(":")
        limit = int(limit_raw) if limit_raw.isdigit() else len(makes)
        return [make for make in makes if make.get("id") is not None][:limit]
    return [
        make
        for make in dictionaries.get("manufacturer") or []
        if make.get("id") is not None
    ]


def resolve_catalog(db: Session, record: OnlinerRecord) -> dict:
    make = None
    if record.manufacturer_slug:
        make = db.scalar(
            select(CatalogMake).where(
                func.lower(CatalogMake.slug) == record.manufacturer_slug.lower()
            )
        )
    if make is None and record.manufacturer_name:
        make = db.scalar(
            select(CatalogMake).where(
                func.lower(CatalogMake.name) == record.manufacturer_name.lower()
            )
        )
    model = None
    if make is not None:
        if record.model_slug:
            model = db.scalar(
                select(CatalogModel).where(
                    CatalogModel.make_id == make.id,
                    func.lower(CatalogModel.slug) == record.model_slug.lower(),
                )
            )
        if model is None and record.model_name:
            model = db.scalar(
                select(CatalogModel).where(
                    CatalogModel.make_id == make.id,
                    func.lower(CatalogModel.name) == record.model_name.lower(),
                )
            )
    return {
        "make_id": make.id if make is not None else None,
        "model_id": model.id if model is not None else None,
        "manual_make": None if make is not None else (record.manufacturer_name or None),
        "manual_model": None if model is not None else (record.model_name or None),
        "make_name": make.name if make is not None else record.manufacturer_name,
        "model_name": model.name if model is not None else record.model_name,
    }


def _region_matches(region: "LocationRegion | None", source_region_name: str) -> bool:
    if region is None:
        return False
    ours = region.name.lower().replace("область", "обл.")
    theirs = source_region_name.lower().replace("область", "обл.")
    return ours == theirs


def resolve_location(db: Session, record: OnlinerRecord) -> dict:
    city_name = (record.city_name or "").strip()
    region_name = (record.region_name or "").strip()
    if city_name:
        cities = db.scalars(
            select(LocationCity).where(func.lower(LocationCity.name) == city_name.lower())
        ).all()
        if len(cities) == 1:
            city = cities[0]
        elif len(cities) > 1 and region_name:
            # The source shortens region names ("Минская обл."); the catalog
            # spells them out.  Compare through the normalized form.
            city = next(
                (
                    candidate
                    for candidate in cities
                    if _region_matches(
                        db.get(LocationRegion, candidate.region_id), region_name
                    )
                ),
                None,
            )
        else:
            city = None
        if city is not None:
            return {"region_id": city.region_id, "city_id": city.id, "manual_city": None}
    return {"region_id": None, "city_id": None, "manual_city": city_name or region_name or None}


def _store_photo(
    db: Session,
    listing: Listing,
    *,
    image_bytes: bytes,
    position: int,
    idempotency_key: str,
) -> ListingPhoto | None:
    """Persist a validated source image the same way an upload does."""

    settings = get_settings()
    if not image_bytes or len(image_bytes) > settings.upload_max_bytes:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                return None
            if image.width * image.height > settings.upload_max_pixels:
                return None
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Warning):
        # app.worker turns DecompressionBombWarning into an error process-wide;
        # oversized images are simply skipped like any other invalid upload.
        return None
    photo_id = uuid.uuid4()
    quarantine = settings.media_root / ".quarantine"
    original_name = f"{uuid.uuid4().hex}.upload"
    source = quarantine / original_name
    try:
        quarantine.mkdir(parents=True, exist_ok=True, mode=0o700)
        source.write_bytes(image_bytes)
        source.chmod(0o600)
    except OSError:
        source.unlink(missing_ok=True)
        return None
    photo = ListingPhoto(
        id=photo_id,
        listing_id=listing.id,
        storage_name=photo_id.hex,
        original_name=original_name,
        status="processing",
        position=position,
        is_cover=position == 0,
        width=width,
        height=height,
        idempotency_key=idempotency_key,
    )
    db.add(photo)
    return photo


def _process_photo(photo_id: uuid.UUID) -> bool:
    """Run the worker-side variant pipeline synchronously."""

    from app.worker import PermanentJobError, _make_variants

    try:
        _make_variants(photo_id)
    except PermanentJobError:
        return False
    return True


def _discard_photo(db: Session, photo: ListingPhoto) -> None:
    settings = get_settings()
    shutil.rmtree(settings.media_root / photo.storage_name, ignore_errors=True)
    (settings.media_root / ".quarantine" / photo.original_name).unlink(missing_ok=True)
    db.delete(photo)


def _purge_unfinished(db: Session, listing: Listing) -> None:
    """Remove an aborted draft from a previous interrupted import run."""

    for photo in db.scalars(
        select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
    ).all():
        _discard_photo(db, photo)
    db.delete(listing)
    db.commit()


def _publication_description(record: OnlinerRecord) -> str:
    note = (
        SOURCE_NOTE.format(url=record.html_url)
        if record.html_url
        else SOURCE_NOTE.format(url="ab.onliner.by")
    )
    if record.description:
        return f"{record.description}\n\n{note}"[:10_000]
    return note


def import_record(
    db: Session,
    record: OnlinerRecord,
    owner: User,
    *,
    company_id: uuid.UUID | None = None,
    client: OnlinerClient | None = None,
    max_photos: int | None = None,
) -> str:
    """Publish one source advert as an active listing.

    Returns ``"imported"``, ``"existing"`` (already published or paused), or
    raises :class:`ValueError` for unusable payloads.  An interrupted draft
    from an earlier run is purged and recreated.
    """

    settings = get_settings()
    limit = settings.onliner_max_photos if max_photos is None else max(0, max_photos)
    existing = db.scalar(select(Listing).where(Listing.slug == record.slug))
    if existing is not None:
        if existing.status != "draft":
            return "existing"
        _purge_unfinished(db, existing)
    catalog = resolve_catalog(db, record)
    location = resolve_location(db, record)
    listing = Listing(
        owner_id=owner.id,
        company_id=company_id,
        slug=record.slug,
        status="draft",
        category_code="cars",
        revision=1,
        title=record.title or record.manufacturer_name or record.source_id,
        year=record.year,
        mileage_km=record.mileage_km,
        fuel=record.fuel,
        transmission=record.transmission,
        drive=record.drive,
        condition=record.condition,
        damaged=record.damaged,
        parts_only=False,
        color=record.color,
        customs_status=record.customs_status,
        exchange=record.exchange,
        equipment=list(record.equipment_ids) or None,
        engine_volume_l=record.engine_volume_l,
        power_hp=record.power_hp,
        description=_publication_description(record),
        price_amount=record.price_amount,
        currency=record.currency,
        make_id=catalog["make_id"],
        model_id=catalog["model_id"],
        manual_make=catalog["manual_make"],
        manual_model=catalog["manual_model"],
        make_name_snapshot=catalog["make_name"] or None,
        model_name_snapshot=catalog["model_name"] or None,
        generation_name_snapshot=record.generation_name,
        region_id=location["region_id"],
        city_id=location["city_id"],
        manual_city=location["manual_city"],
        contact_phone=record.contact_phone,
        call_hours=record.call_hours,
    )
    db.add(listing)
    db.flush()

    stored: list[ListingPhoto] = []
    if client is not None and limit > 0:
        for index, url in enumerate(record.image_urls[:limit]):
            try:
                raw = client.download_image(url, max_bytes=settings.upload_max_bytes)
            except OnlinerFetchError:
                continue
            photo = _store_photo(
                db,
                listing,
                image_bytes=raw,
                position=len(stored),
                idempotency_key=f"{record.slug}:{index}",
            )
            if photo is not None:
                stored.append(photo)
        db.commit()
        for photo in stored:
            if not _process_photo(photo.id):
                db.delete(photo)
                db.commit()

    listing.revision += 1
    listing.status = "active"
    listing.moderated_at = datetime.now(UTC)
    db.add(
        ListingStatusEvent(
            listing_id=listing.id,
            actor_id=owner.id,
            actor_kind="import",
            from_status="draft",
            to_status="active",
            revision=listing.revision,
            reason="onliner_import",
        )
    )
    record_active_listing_price_state(db, listing)
    enqueue_saved_search_match(db, listing)
    db.add(
        AuditEvent(
            actor_id=owner.id,
            entity_type="listing",
            entity_id=listing.id,
            action="imported_onliner_listing",
            details={
                "source": "onliner.by",
                "source_id": record.source_id,
                "source_url": record.html_url,
                "photos": len(record.image_urls[:limit]),
            },
        )
    )
    db.commit()
    return "imported"


def iter_snapshot_rows(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict) and isinstance(payload.get("detail"), dict):
                yield payload


def import_snapshot(
    db: Session,
    snapshot_path: Path,
    owner: User,
    *,
    company_id: uuid.UUID | None = None,
    client: OnlinerClient | None = None,
    max_photos: int | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Import a JSONL snapshot collected by :func:`collect_snapshot`."""

    stats = {
        "requested": 0,
        "imported": 0,
        "existing": 0,
        "failed": 0,
        "without_photos": 0,
    }
    for row in iter_snapshot_rows(snapshot_path):
        stats["requested"] += 1
        try:
            record = parse_advert(row["detail"], row.get("phones") or [])
        except (ValueError, TypeError):
            stats["failed"] += 1
            continue
        if dry_run:
            existing = db.scalar(select(Listing).where(Listing.slug == record.slug))
            if existing is not None and existing.status != "draft":
                stats["existing"] += 1
            else:
                stats["imported"] += 1
            continue
        try:
            action = import_record(
                db,
                record,
                owner,
                company_id=company_id,
                client=client,
                max_photos=max_photos,
            )
        except (ValueError, TypeError):
            stats["failed"] += 1
            continue
        stats[action] += 1
        if action == "imported":
            listing = db.scalar(select(Listing).where(Listing.slug == record.slug))
            has_photo = (
                listing is not None
                and db.scalars(
                    select(ListingPhoto.id)
                    .where(ListingPhoto.listing_id == listing.id)
                    .limit(1)
                ).first()
                is not None
            )
            if not has_photo:
                stats["without_photos"] += 1
        if limit is not None and stats["imported"] >= limit:
            break
    return stats


def collect_snapshot(
    client: OnlinerClient,
    output: Path,
    *,
    per_make_limit: int | None = None,
    manufacturers: str = "all",
    include_phones: bool = True,
) -> dict:
    """Collect fresh used cars per manufacturer into a JSONL snapshot."""

    settings = get_settings()
    per_make = (
        settings.onliner_per_make_limit
        if per_make_limit is None
        else max(1, per_make_limit)
    )
    dictionaries = client.dictionaries()
    makes = _selected_manufacturers(dictionaries, manufacturers)
    output.parent.mkdir(parents=True, exist_ok=True)
    stats = {
        "makes": len(makes),
        "adverts_seen": 0,
        "written": 0,
        "skipped": 0,
        "errors": 0,
        "output": str(output),
    }
    seen: set[str] = set()
    with output.open("w", encoding="utf-8") as handle:
        for make in makes:
            try:
                payload = client.search_used(make["id"], limit=per_make)
            except OnlinerFetchError:
                stats["errors"] += 1
                continue
            for advert in payload.get("adverts") or []:
                advert_id = (
                    str(advert.get("id") or "") if isinstance(advert, dict) else ""
                )
                if not advert_id.isdigit() or advert_id in seen:
                    continue
                seen.add(advert_id)
                stats["adverts_seen"] += 1
                try:
                    detail = client.get_advert(advert_id)
                    if detail is None:
                        stats["skipped"] += 1
                        continue
                    phones = client.get_phones(advert_id) if include_phones else []
                except OnlinerFetchError:
                    stats["errors"] += 1
                    continue
                handle.write(
                    json.dumps({"detail": detail, "phones": phones}, ensure_ascii=False)
                    + "\n"
                )
                handle.flush()
                stats["written"] += 1
    return stats


def _transition(db: Session, listing: Listing, target: str, reason: str) -> None:
    listing.revision += 1
    old_status = listing.status
    listing.status = target
    db.add(
        ListingStatusEvent(
            listing_id=listing.id,
            actor_id=listing.owner_id,
            actor_kind="import",
            from_status=old_status,
            to_status=target,
            revision=listing.revision,
            reason=reason,
        )
    )


def sync_existing(
    db: Session,
    client: OnlinerClient,
    *,
    lease_renew: Callable[[], None] | None = None,
) -> dict:
    """Refresh imported listings: price changes, closures, reopenings."""

    listings = db.scalars(
        select(Listing)
        .where(Listing.slug.like("onliner-%"), Listing.status.in_(("active", "paused")))
        .order_by(Listing.updated_at, Listing.id)
    ).all()
    stats = {
        "checked": 0,
        "price_updates": 0,
        "closed": 0,
        "reopened": 0,
        "unchanged": 0,
        "errors": 0,
    }
    for index, listing in enumerate(listings):
        if lease_renew is not None and index % 25 == 0:
            lease_renew()
        source_id = listing.slug.removeprefix("onliner-")
        stats["checked"] += 1
        try:
            detail = client.get_advert(source_id)
        except OnlinerFetchError:
            stats["errors"] += 1
            continue
        if detail is None or detail.get("closed_at"):
            if listing.status == "active":
                _transition(db, listing, "paused", "closed_on_source")
                stats["closed"] += 1
                db.commit()
            else:
                stats["unchanged"] += 1
            continue
        try:
            amount, currency = _price(detail.get("price") or {})
        except (TypeError, ValueError):
            amount, currency = None, None
        price_changed = (
            amount is not None
            and currency is not None
            and (amount != listing.price_amount or currency != listing.currency)
        )
        reopened = listing.status == "paused"
        if reopened:
            _transition(db, listing, "active", "reopened_on_source")
            stats["reopened"] += 1
        if price_changed:
            listing.price_amount = amount
            listing.currency = currency
            listing.revision += 1
            record_active_listing_price_state(db, listing)
            stats["price_updates"] += 1
        if price_changed or reopened:
            db.commit()
        else:
            stats["unchanged"] += 1
    return stats


def discover_new(
    db: Session,
    client: OnlinerClient,
    owner: User,
    *,
    per_make_limit: int | None = None,
    manufacturers: str = "all",
    max_photos: int | None = None,
    lease_renew: Callable[[], None] | None = None,
) -> dict:
    """Import adverts that appeared on the source since the previous run."""

    settings = get_settings()
    per_make = (
        settings.onliner_per_make_limit
        if per_make_limit is None
        else max(1, per_make_limit)
    )
    dictionaries = client.dictionaries()
    makes = _selected_manufacturers(dictionaries, manufacturers)
    stats = {
        "makes": len(makes),
        "adverts_seen": 0,
        "imported": 0,
        "existing": 0,
        "failed": 0,
        "errors": 0,
    }
    for make_index, make in enumerate(makes):
        if lease_renew is not None and make_index % 10 == 0:
            lease_renew()
        try:
            payload = client.search_used(make["id"], limit=per_make)
        except OnlinerFetchError:
            stats["errors"] += 1
            continue
        for advert in payload.get("adverts") or []:
            advert_id = str(advert.get("id") or "") if isinstance(advert, dict) else ""
            if not advert_id.isdigit():
                continue
            stats["adverts_seen"] += 1
            existing = db.scalar(
                select(Listing).where(Listing.slug == f"onliner-{advert_id}")
            )
            if existing is not None and existing.status != "draft":
                stats["existing"] += 1
                continue
            try:
                detail = client.get_advert(advert_id)
                if detail is None:
                    stats["failed"] += 1
                    continue
                phones = client.get_phones(advert_id)
                record = parse_advert(detail, phones)
            except (OnlinerFetchError, ValueError, TypeError):
                stats["failed"] += 1
                continue
            try:
                action = import_record(
                    db, record, owner, client=client, max_photos=max_photos
                )
            except (ValueError, TypeError):
                stats["failed"] += 1
                continue
            stats[action] += 1
    return stats
