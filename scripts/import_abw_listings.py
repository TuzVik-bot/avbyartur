#!/usr/bin/env python3
"""Import a bounded, metadata-only ABW listing snapshot.

The importer is deliberately a database-side operator tool rather than a web
endpoint.  It accepts a JSON list collected through an authorised browser
session, keeps the public source URL as the idempotency key, and creates
unpublished records.  It never imports phone numbers, VINs, photos, or source
HTML.  A later moderation step must verify each record before publication.

Typical use inside the API container::

    python scripts/import_abw_listings.py snapshot.json \
      --owner-email admin@example.invalid --status draft --dry-run

Remove ``--dry-run`` only after the database backup and operator review are
complete.  Re-running the same snapshot skips rows whose ``abw-<id>`` slug is
already present.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

# The production image has ``/app`` on ``sys.path``; a checkout keeps the
# package under ``backend``.  Supporting both makes ``--dry-run`` reproducible
# locally without changing the container entrypoint.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

DETAIL_PREFIX = "https://abw.by/cars/detail/"
ALLOWED_STATUS = {"draft", "pending_review"}
FUEL_MAP = {
    "бензин": "petrol",
    "diesel": "diesel",
    "дизель": "diesel",
    "гибрид": "hybrid",
    "hybrid": "hybrid",
    "электро": "electric",
    "электричество": "electric",
    "electric": "electric",
    "газ": "lpg",
    "lpg": "lpg",
}
TRANSMISSION_MAP = {
    "механика": "manual",
    "manual": "manual",
    "автомат": "automatic",
    "automatic": "automatic",
    "робот": "robot",
    "robot": "robot",
    "вариатор": "cvt",
    "cvt": "cvt",
}
DRIVE_MAP = {
    "передний": "front",
    "front": "front",
    "задний": "rear",
    "rear": "rear",
    "полный": "all",
    "all": "all",
}


@dataclass(frozen=True)
class Record:
    source_url: str
    source_id: str
    title: str
    make: str | None
    model: str | None
    year: int | None
    mileage_km: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    condition: str | None
    engine_volume_l: Decimal | None
    power_hp: int | None
    price_byn: Decimal | None
    city: str | None
    description: str

    @property
    def slug(self) -> str:
        return f"abw-{self.source_id}"


def _text(value: object, *, limit: int) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]*>", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _without_personal_data(value: object) -> str:
    text = _text(value, limit=2_000)
    # VINs are intentionally discarded even when a source card contains one.
    text = re.sub(r"\b[A-HJ-NPR-Z0-9]{17}\b", "", text, flags=re.I)
    text = re.sub(r"\bVIN\s*:?[\s-]*", "", text, flags=re.I)
    # Belarus and international phone forms, including common punctuation.
    text = re.sub(r"(?<!\w)(?:\+?375|8)?[\s().-]*\d[\d\s().-]{7,}\d(?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip(" ;,-")


def _url(value: object) -> tuple[str, str]:
    raw = _text(value, limit=500)
    parts = urlsplit(raw)
    canonical = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    if not canonical.startswith(DETAIL_PREFIX) or parts.scheme.lower() != "https" or parts.netloc.lower() != "abw.by":
        raise ValueError(f"source_url must be an https://abw.by/cars/detail/... URL: {raw!r}")
    match = re.fullmatch(r"[0-9]+", canonical.rsplit("/", 1)[-1])
    if match is None:
        raise ValueError(f"source_url has no numeric ABW listing id: {raw!r}")
    return canonical, match.group(0)


def _int(value: object, *, name: str, minimum: int = 0, maximum: int = 5_000_000) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    raw = str(value).replace("\u00a0", " ").strip()
    raw = re.sub(r"[^0-9-]", "", raw)
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer: {value!r}") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} is out of range: {parsed}")
    return parsed


def _price(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    raw = str(value).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    raw = re.sub(r"[^0-9.]", "", raw)
    try:
        result = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"price_byn must be a positive number: {value!r}") from exc
    if result <= 0 or result > Decimal("9999999999"):
        raise ValueError(f"price_byn is out of range: {result}")
    return result


def _engine_volume(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    raw = str(value).replace(",", ".").strip()
    raw = re.sub(r"[^0-9.]", "", raw)
    try:
        result = Decimal(raw).quantize(Decimal("0.1"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"engine_volume_l must be a number: {value!r}") from exc
    if result < 0 or result > Decimal("30"):
        raise ValueError(f"engine_volume_l is out of range: {result}")
    return result


def _enum(value: object, mapping: dict[str, str]) -> str | None:
    if value in (None, ""):
        return None
    key = _text(value, limit=40).casefold()
    return mapping.get(key, "other")


def _record(raw: object, index: int) -> Record:
    if not isinstance(raw, dict):
        raise ValueError(f"item {index} must be an object")
    source_url, source_id = _url(raw.get("url", raw.get("source_url")))
    title = _text(raw.get("title"), limit=240)
    if not title:
        raise ValueError(f"item {index} ({source_id}) has no title")
    year = _int(raw.get("year"), name="year", minimum=1886, maximum=2100)
    description = _without_personal_data(raw.get("description"))
    source_note = f"Источник: ABW.BY; карточка {source_url}. Контактные данные, идентификаторы и фотографии не импортированы; требуется ручная проверка."
    if description:
        description = f"{description} {source_note}"[:10_000]
    else:
        description = source_note
    make = _text(raw.get("make", raw.get("manual_make")), limit=180) or None
    model = _text(raw.get("model", raw.get("manual_model")), limit=180) or None
    city = _text(raw.get("city", raw.get("manual_city")), limit=160) or None
    state = _text(raw.get("condition"), limit=30).casefold()
    condition = (
        "new"
        if state in {"new", "новый", "новая"}
        else "used"
        if state in {"used", "б/у", "подержанный", "подержанная"}
        else None
    )
    return Record(
        source_url=source_url,
        source_id=source_id,
        title=title,
        make=make,
        model=model,
        year=year,
        mileage_km=_int(raw.get("mileage_km", raw.get("mileage")), name="mileage_km"),
        fuel=_enum(raw.get("fuel"), FUEL_MAP),
        transmission=_enum(raw.get("transmission"), TRANSMISSION_MAP),
        drive=_enum(raw.get("drive"), DRIVE_MAP),
        condition=condition,
        engine_volume_l=_engine_volume(raw.get("engine_volume_l")),
        power_hp=_int(raw.get("power_hp"), name="power_hp", minimum=1, maximum=3_000),
        price_byn=_price(raw.get("price_byn", raw.get("price"))),
        city=city,
        description=description,
    )


def load_records(path: Path, limit: int | None) -> list[Record]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("snapshot must be a JSON list or an object with an items list")
    result: list[Record] = []
    seen: set[str] = set()
    for index, raw in enumerate(items, 1):
        record = _record(raw, index)
        if record.source_id in seen:
            continue
        seen.add(record.source_id)
        result.append(record)
        if limit is not None and len(result) >= limit:
            break
    if not result:
        raise ValueError("snapshot contains no valid records")
    if limit is not None and len(result) != limit:
        raise ValueError(f"snapshot contains {len(result)} unique records, {limit} required")
    return result


def _owner(db, owner_email: str | None, owner_id: UUID | None):
    # Keep database imports lazy so local snapshot validation and ``--help``
    # remain usable without the backend runtime dependencies installed.
    from sqlalchemy import select

    from app.models import User

    if owner_id is not None:
        owner = db.get(User, owner_id)
    elif owner_email:
        owner = db.scalar(select(User).where(User.email == owner_email.strip().casefold()))
    else:
        owner = None
    if owner is None or owner.status != "active":
        raise LookupError("owner must be an existing active user (use --owner-email or --owner-id)")
    return owner


def import_records(records: list[Record], *, owner_email: str | None, owner_id: UUID | None, status: str, dry_run: bool) -> dict[str, int | str]:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"status must be one of {sorted(ALLOWED_STATUS)}")
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuditEvent, Listing, ListingStatusEvent

    with SessionLocal() as db:
        owner = _owner(db, owner_email, owner_id)
        existing = {
            row.slug
            for row in db.scalars(select(Listing).where(Listing.slug.in_([record.slug for record in records]))).all()
        }
        to_insert = [record for record in records if record.slug not in existing]
        if dry_run:
            return {"requested": len(records), "existing": len(existing), "would_insert": len(to_insert), "status": status}
        for record in to_insert:
            listing = Listing(
                owner_id=owner.id,
                slug=record.slug,
                status=status,
                revision=1,
                submitted_revision=1 if status == "pending_review" else None,
                make_name_snapshot=record.make,
                model_name_snapshot=record.model,
                title=record.title,
                year=record.year,
                mileage_km=record.mileage_km,
                fuel=record.fuel,
                transmission=record.transmission,
                drive=record.drive,
                condition=record.condition,
                engine_volume_l=record.engine_volume_l,
                power_hp=record.power_hp,
                description=record.description,
                price_amount=record.price_byn,
                currency="BYN" if record.price_byn is not None else None,
                manual_city=record.city,
                contact_phone="",
                vin=None,
            )
            db.add(listing)
            db.flush()
            if status == "pending_review":
                db.add(ListingStatusEvent(
                    listing_id=listing.id,
                    actor_id=owner.id,
                    actor_kind="import",
                    from_status="draft",
                    to_status="pending_review",
                    revision=1,
                    reason="ABW metadata import; manual moderation required",
                ))
            db.add(AuditEvent(
                actor_id=owner.id,
                entity_type="listing",
                entity_id=listing.id,
                action="imported_abw_metadata",
                details={"source": "abw.by", "source_url": record.source_url, "source_id": record.source_id, "status": status},
            ))
        db.commit()
        return {"requested": len(records), "existing": len(existing), "inserted": len(to_insert), "status": status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument("--owner-email")
    owner.add_argument("--owner-id", type=UUID)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUS), default="draft")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        records = load_records(args.snapshot, args.limit)
        result = import_records(records, owner_email=args.owner_email, owner_id=args.owner_id, status=args.status, dry_run=args.dry_run)
    except (OSError, ValueError, LookupError, json.JSONDecodeError) as exc:
        print(f"ABW import failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
