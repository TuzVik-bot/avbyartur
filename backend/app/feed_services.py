import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.feed_schemas import DealerFeedRecord, FEED_FIELDS, FEED_SCHEMA_FIELDS
from app.models import (
    Company,
    DealerExternalListingKey,
    DealerFeed,
    FeedImportRow,
    FeedImportRun,
    Listing,
    ListingStatusEvent,
    ListingPhoto,
    User,
)
from app.schemas import ListingForm
from app.services import fail


MAX_FEED_BYTES = 10 * 1024 * 1024
MAX_FEED_ROWS = 5000


class FeedParseError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _mapping(field_mapping: Mapping[str, str] | None) -> dict[str, str]:
    if field_mapping:
        return dict(field_mapping)
    return {field: field for field in FEED_FIELDS}


def _equipment_values(value: object) -> object:
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.startswith("["):
        try:
            decoded = json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned
        return decoded if isinstance(decoded, list) else cleaned
    return [item.strip() for item in cleaned.split("|") if item.strip()]


def _record_values(raw: Mapping[str, object], mapping: Mapping[str, str]) -> dict[str, Any | None]:
    normalized_keys = {str(key).strip().casefold(): value for key, value in raw.items()}
    values: dict[str, Any | None] = {}
    for target, source in mapping.items():
        if target not in FEED_FIELDS:
            continue
        value = normalized_keys.get(source.strip().casefold())
        if value is None:
            continue
        cleaned = str(value).strip()
        values[target] = _equipment_values(cleaned) if target == "equipment" else (cleaned or None)
    return values


def _parse_csv(content: bytes, mapping: Mapping[str, str]) -> list[dict]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FeedParseError("invalid_encoding", "CSV must use UTF-8 encoding") from exc

    try:
        reader = csv.DictReader(io.StringIO(decoded, newline=""), strict=True)
        headers = reader.fieldnames
        if not headers or not any(header and header.strip() for header in headers):
            raise FeedParseError("invalid_csv_headers", "CSV header row is missing")
        cleaned_headers = [header.strip() if header else "" for header in headers]
        folded = [header.casefold() for header in cleaned_headers if header]
        if len(folded) != len(set(folded)):
            raise FeedParseError("duplicate_csv_headers", "CSV contains duplicate column names")
        reader.fieldnames = cleaned_headers

        normalized_headers = {header.casefold() for header in cleaned_headers if header}
        absent = [source for source in mapping.values() if source.strip().casefold() not in normalized_headers]
        # Default mappings are opportunistic: a CSV may contain only a subset of
        # the canonical fields. Explicit mappings, however, must all exist.
        if absent and any(mapping.get(field) != field for field in mapping):
            raise FeedParseError("feed_mapping_column_missing", "A configured CSV column is missing")

        records = []
        for row_number, row in enumerate(reader, start=2):
            if row_number - 1 > MAX_FEED_ROWS:
                raise FeedParseError("too_many_rows", f"Feed cannot contain more than {MAX_FEED_ROWS} rows")
            if row is None:
                continue
            overflow = row.get(None)
            if overflow:
                records.append({
                    "row_number": row_number,
                    "values": {},
                    "error_code": "malformed_row",
                    "error_message": "CSV row contains more values than the header",
                })
                continue
            values = _record_values(row, mapping)
            if not any(value not in (None, "") for value in values.values()):
                continue
            records.append({"row_number": row_number, "values": values})
        return records
    except FeedParseError:
        raise
    except (csv.Error, UnicodeError) as exc:
        raise FeedParseError("invalid_csv", "CSV could not be parsed") from exc


def _xml_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].casefold() if isinstance(element.tag, str) else ""


def _xml_records(content: bytes, mapping: Mapping[str, str]) -> list[dict]:
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", content, flags=re.IGNORECASE):
        raise FeedParseError("unsafe_xml", "XML document type and entity declarations are not allowed")
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as exc:
        raise FeedParseError("invalid_xml", "XML could not be parsed") from exc

    record_tags = {"listing", "vehicle", "item", "car", "ad", "offer"}
    if _xml_tag(root) in record_tags:
        elements = [root]
    else:
        elements = [child for child in root if len(child) or child.attrib]
        if not elements and list(root):
            elements = list(root)
    if not elements:
        raise FeedParseError("empty_feed", "XML contains no listing records")

    records = []
    for row_number, element in enumerate(elements, start=1):
        if row_number > MAX_FEED_ROWS:
            raise FeedParseError("too_many_rows", f"Feed cannot contain more than {MAX_FEED_ROWS} rows")
        raw: dict[str, str] = {}
        for child in element:
            tag = _xml_tag(child)
            if tag:
                raw[tag] = "".join(child.itertext()).strip()
        raw.update({key.casefold(): value for key, value in element.attrib.items()})
        values = _record_values(raw, mapping)
        if not any(value not in (None, "") for value in values.values()):
            continue
        records.append({"row_number": row_number, "values": values})
    return records


def parse_feed_bytes(
    content: bytes,
    *,
    feed_format: str,
    field_mapping: Mapping[str, str] | None,
) -> list[dict]:
    if len(content) > MAX_FEED_BYTES:
        raise FeedParseError("feed_too_large", f"Feed cannot exceed {MAX_FEED_BYTES} bytes")
    if feed_format not in {"csv", "xml"}:
        raise FeedParseError("unsupported_feed_format", "Uploaded feeds must use CSV or XML")
    mapping = _mapping(field_mapping)
    records = _parse_csv(content, mapping) if feed_format == "csv" else _xml_records(content, mapping)
    if not records:
        raise FeedParseError("empty_feed", "Feed contains no listing rows")
    return records


def digest_feed_payload(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def issue_api_token() -> tuple[str, str, str]:
    token = f"avf_{secrets.token_urlsafe(32)}"
    return token, hashlib.sha256(token.encode()).hexdigest(), token[:12]


def api_token_matches(token: str, digest: str | None) -> bool:
    if digest is None:
        return False
    return hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), digest)


def feed_out(feed: DealerFeed) -> dict:
    return {
        "id": feed.id,
        "name": feed.name,
        "format": feed.format,
        "status": feed.status,
        "field_mapping": feed.field_mapping or {},
        "manual_conflict_policy": feed.manual_conflict_policy,
        "missing_retirement_enabled": feed.missing_retirement_enabled,
        "missing_retirement_delay_hours": feed.missing_retirement_delay_hours,
        "api_token_prefix": feed.api_token_prefix,
        "created_at": feed.created_at,
    }


def import_run_out(run: FeedImportRun) -> dict:
    return {
        "id": run.id,
        "feed_id": run.feed_id,
        "status": run.status,
        "dry_run": run.dry_run,
        "source_filename": run.source_filename,
        "total_rows": run.total_rows,
        "applied_rows": run.applied_rows,
        "rejected_rows": run.rejected_rows,
        "error_code": run.error_code,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
    }


def import_row_out(row: FeedImportRow) -> dict:
    return {
        "id": row.id,
        "row_number": row.row_number,
        "dealer_external_id": row.dealer_external_id,
        "listing_id": row.listing_id,
        "status": row.status,
        "action": row.action,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "field_errors": row.field_errors or {},
    }


def _missing_candidate_out(
    feed: DealerFeed,
    link: DealerExternalListingKey,
    listing: Listing,
    *,
    now: datetime | None = None,
    preview: bool = False,
) -> dict:
    now = now or datetime.now(timezone.utc)
    due_at = (
        link.missing_since + timedelta(hours=feed.missing_retirement_delay_hours)
        if link.missing_since is not None
        else None
    )
    expected_revision = link.missing_listing_revision
    reason: str | None = "preview_only" if preview else None
    if not preview:
        if not feed.missing_retirement_enabled:
            reason = "retirement_disabled"
        elif expected_revision is None or listing.revision != expected_revision:
            reason = "listing_changed"
        elif listing.status != "active":
            reason = "listing_not_active"
        elif due_at is None or now < due_at:
            reason = "confirmation_delay"
    return {
        "dealer_external_id": link.dealer_external_id,
        "listing_id": listing.id,
        "title": listing.title,
        "status": listing.status,
        "listing_revision": listing.revision,
        "expected_listing_revision": expected_revision,
        "snapshot_digest": link.missing_snapshot_digest,
        "missing_since": link.missing_since,
        "due_at": due_at,
        "eligible": not preview and reason is None,
        "reason": reason,
    }


def list_missing_candidates(db: Session, feed: DealerFeed) -> list[dict]:
    rows = db.execute(
        select(DealerExternalListingKey, Listing)
        .join(Listing, Listing.id == DealerExternalListingKey.listing_id)
        .where(
            DealerExternalListingKey.feed_id == feed.id,
            DealerExternalListingKey.missing_since.is_not(None),
            DealerExternalListingKey.missing_confirmed_at.is_(None),
        )
        .order_by(DealerExternalListingKey.missing_since, DealerExternalListingKey.dealer_external_id)
    ).all()
    now = datetime.now(timezone.utc)
    return [_missing_candidate_out(feed, link, listing, now=now) for link, listing in rows]


def preview_missing_candidates(
    db: Session,
    feed: DealerFeed,
    *,
    present_external_ids: set[str],
    payload_digest: str,
) -> list[dict]:
    rows = db.execute(
        select(DealerExternalListingKey, Listing)
        .join(Listing, Listing.id == DealerExternalListingKey.listing_id)
        .where(DealerExternalListingKey.feed_id == feed.id)
        .order_by(DealerExternalListingKey.dealer_external_id)
    ).all()
    result = []
    now = datetime.now(timezone.utc)
    for link, listing in rows:
        if link.dealer_external_id in present_external_ids or link.missing_confirmed_at is not None:
            continue
        if link.missing_since is None:
            candidate = {
                "dealer_external_id": link.dealer_external_id,
                "listing_id": listing.id,
                "title": listing.title,
                "status": listing.status,
                "listing_revision": listing.revision,
                "expected_listing_revision": listing.revision,
                "snapshot_digest": payload_digest,
                "missing_since": None,
                "due_at": None,
                "eligible": False,
                "reason": "preview_only",
            }
        else:
            candidate = _missing_candidate_out(feed, link, listing, now=now)
        result.append(candidate)
    return result


def update_missing_candidate_state(
    db: Session,
    feed: DealerFeed,
    *,
    present_external_ids: set[str],
    payload_digest: str,
    record_absent: bool,
) -> None:
    rows = db.execute(
        select(DealerExternalListingKey, Listing)
        .join(Listing, Listing.id == DealerExternalListingKey.listing_id)
        .where(DealerExternalListingKey.feed_id == feed.id)
        .order_by(DealerExternalListingKey.dealer_external_id)
    ).all()
    now = datetime.now(timezone.utc)
    for link, listing in rows:
        if link.dealer_external_id in present_external_ids:
            link.missing_since = None
            link.missing_snapshot_digest = None
            link.missing_listing_revision = None
            link.missing_confirmed_at = None
            link.missing_confirmed_by = None
        elif record_absent and link.missing_confirmed_at is None:
            if link.missing_since is None:
                link.missing_since = now
                link.missing_listing_revision = listing.revision
            link.missing_snapshot_digest = payload_digest


def confirm_missing_candidates(
    db: Session,
    *,
    feed: DealerFeed,
    company_id: UUID,
    initiated_by: UUID,
    items: list[Mapping[str, Any]],
    idempotency_key: str | None,
) -> tuple[FeedImportRun, list[str]]:
    if idempotency_key is None:
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    key = idempotency_key.strip()
    if not key or len(key) > 120:
        fail(422, "invalid_idempotency_key", "Idempotency-Key must contain at most 120 characters")

    canonical_items = sorted(
        (
            str(item["dealer_external_id"]),
            int(item["expected_listing_revision"]),
            str(item["snapshot_digest"]),
        )
        for item in items
    )
    payload_digest = hashlib.sha256(
        json.dumps(canonical_items, separators=(",", ":")).encode()
    ).hexdigest()
    request_hash = hashlib.sha256(f"missing-confirmation:{payload_digest}".encode()).hexdigest()
    prior = db.scalar(select(FeedImportRun).where(
        FeedImportRun.feed_id == feed.id,
        FeedImportRun.idempotency_key == key,
    ))
    if prior is not None:
        if prior.source_filename != "missing-confirmation" or not hmac.compare_digest(prior.payload_digest, request_hash):
            fail(409, "idempotency_conflict", "Idempotency-Key was already used for a different operation")
        paused = db.scalars(select(FeedImportRow.dealer_external_id).where(
            FeedImportRow.run_id == prior.id,
            FeedImportRow.action == "missing_paused",
        )).all()
        return prior, paused

    if not feed.missing_retirement_enabled:
        fail(409, "missing_retirement_disabled", "Enable delayed missing-listing retirement for this feed first")

    external_ids = [external_id for external_id, _revision, _digest in canonical_items]
    links = db.scalars(
        select(DealerExternalListingKey)
        .where(
            DealerExternalListingKey.feed_id == feed.id,
            DealerExternalListingKey.dealer_external_id.in_(external_ids),
        )
        .order_by(DealerExternalListingKey.dealer_external_id)
        .with_for_update()
    ).all()
    links_by_external_id = {link.dealer_external_id: link for link in links}
    listing_ids = sorted({link.listing_id for link in links}, key=str)
    listings = db.scalars(
        select(Listing).where(Listing.id.in_(listing_ids)).order_by(Listing.id).with_for_update()
    ).all() if listing_ids else []
    listings_by_id = {listing.id: listing for listing in listings}
    now = datetime.now(timezone.utc)
    for external_id, expected_revision, snapshot_digest in canonical_items:
        link = links_by_external_id.get(external_id)
        listing = listings_by_id.get(link.listing_id) if link else None
        if (
            link is None
            or listing is None
            or link.missing_since is None
            or link.missing_confirmed_at is not None
        ):
            fail(409, "missing_candidate_stale", "A selected missing-listing candidate is no longer available")
        due_at = link.missing_since + timedelta(hours=feed.missing_retirement_delay_hours)
        if now < due_at:
            fail(409, "missing_confirmation_too_early", "Wait until the configured confirmation delay has passed")
        if (
            link.missing_snapshot_digest != snapshot_digest
            or link.missing_listing_revision != expected_revision
            or listing.revision != expected_revision
        ):
            fail(409, "missing_candidate_stale", "A selected listing changed after the missing preview; refresh the candidates")
        if listing.status != "active":
            fail(409, "listing_not_active", "Only currently active listings can be paused by this confirmation")

    run = FeedImportRun(
        feed_id=feed.id,
        company_id=company_id,
        initiated_by=initiated_by,
        idempotency_key=key,
        payload_digest=request_hash,
        dry_run=False,
        status="succeeded",
        source_filename="missing-confirmation",
        total_rows=len(canonical_items),
        applied_rows=len(canonical_items),
        rejected_rows=0,
        completed_at=now,
    )
    db.add(run)
    db.flush()
    paused_external_ids = []
    for row_number, (external_id, _expected_revision, _snapshot_digest) in enumerate(canonical_items, start=1):
        link = links_by_external_id[external_id]
        listing = listings_by_id[link.listing_id]
        previous_status = listing.status
        listing.status = "paused"
        listing.revision += 1
        link.missing_confirmed_at = now
        link.missing_confirmed_by = initiated_by
        db.add(ListingStatusEvent(
            listing_id=listing.id,
            actor_id=initiated_by,
            from_status=previous_status,
            to_status="paused",
            revision=listing.revision,
            reason="feed_missing_confirmed",
        ))
        db.add(FeedImportRow(
            run_id=run.id,
            row_number=row_number,
            dealer_external_id=external_id,
            listing_id=listing.id,
            status="unchanged",
            action="missing_paused",
            field_errors={},
        ))
        paused_external_ids.append(external_id)
    db.commit()
    db.refresh(run)
    return run, paused_external_ids


def _request_digest(payload_digest: str, dry_run: bool, complete_snapshot: bool) -> str:
    return hashlib.sha256(
        f"{payload_digest}:{int(dry_run)}:{int(complete_snapshot)}".encode()
    ).hexdigest()


def feed_schema_out() -> dict:
    return {
        "version": "1",
        "formats": ["csv", "xml", "api"],
        "stable_key": "dealer_external_id",
        "fields": FEED_SCHEMA_FIELDS,
    }


def feed_sample(format_: str) -> tuple[bytes, str, str]:
    if format_ == "csv":
        content = (
            "dealer_external_id,manual_make,manual_model,title,year,mileage_km,fuel,transmission,drive,condition,color,customs_status,technical_condition,body_condition,exchange,bargaining,credit,leasing,equipment,district,call_hours,damaged,parts_only,engine_volume_l,power_hp,description,price_amount,currency,manual_city\n"
            'DEMO-CAR-001,Example Auto,Demo Model,Example Auto Demo Model,2020,45000,petrol,automatic,front,used,gray,cleared_rb,good,good,false,true,false,false,"abs|heated_seats",Central,09:00-18:00,false,false,1.6,125,"Synthetic sample only",14500.00,BYN,Minsk\n'
        ).encode("utf-8")
        return content, "dealer-feed-sample.csv", "text/csv; charset=utf-8"
    if format_ == "xml":
        content = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<listings>\n"
            "  <listing>\n"
            "    <dealer_external_id>DEMO-CAR-001</dealer_external_id>\n"
            "    <manual_make>Example Auto</manual_make>\n"
            "    <manual_model>Demo Model</manual_model>\n"
            "    <title>Example Auto Demo Model</title>\n"
            "    <year>2020</year>\n"
            "    <mileage_km>45000</mileage_km>\n"
            "    <fuel>petrol</fuel>\n"
            "    <transmission>automatic</transmission>\n"
            "    <drive>front</drive>\n"
            "    <condition>used</condition>\n"
            "    <color>gray</color>\n"
            "    <customs_status>cleared_rb</customs_status>\n"
            "    <technical_condition>good</technical_condition>\n"
            "    <body_condition>good</body_condition>\n"
            "    <exchange>false</exchange>\n"
            "    <bargaining>true</bargaining>\n"
            "    <credit>false</credit>\n"
            "    <leasing>false</leasing>\n"
            "    <equipment>abs|heated_seats</equipment>\n"
            "    <district>Central</district>\n"
            "    <call_hours>09:00-18:00</call_hours>\n"
            "    <damaged>false</damaged>\n"
            "    <parts_only>false</parts_only>\n"
            "    <engine_volume_l>1.6</engine_volume_l>\n"
            "    <power_hp>125</power_hp>\n"
            "    <description>Synthetic sample only</description>\n"
            "    <price_amount>14500.00</price_amount>\n"
            "    <currency>BYN</currency>\n"
            "    <manual_city>Minsk</manual_city>\n"
            "  </listing>\n"
            "</listings>\n"
        ).encode("utf-8")
        return content, "dealer-feed-sample.xml", "application/xml; charset=utf-8"
    if format_ == "api":
        content = json.dumps(
            {
                "items": [
                    {
                        "dealer_external_id": "DEMO-CAR-001",
                        "manual_make": "Example Auto",
                        "manual_model": "Demo Model",
                        "title": "Example Auto Demo Model",
                        "year": 2020,
                        "mileage_km": 45000,
                        "fuel": "petrol",
                        "transmission": "automatic",
                        "drive": "front",
                        "condition": "used",
                        "color": "gray",
                        "customs_status": "cleared_rb",
                        "technical_condition": "good",
                        "body_condition": "good",
                        "exchange": False,
                        "bargaining": True,
                        "credit": False,
                        "leasing": False,
                        "equipment": ["abs", "heated_seats"],
                        "district": "Central",
                        "call_hours": "09:00-18:00",
                        "damaged": False,
                        "parts_only": False,
                        "engine_volume_l": "1.6",
                        "power_hp": 125,
                        "description": "Synthetic sample only",
                        "price_amount": "14500.00",
                        "currency": "BYN",
                        "manual_city": "Minsk",
                    }
                ],
                "dry_run": True,
                "complete_snapshot": False,
            },
            indent=2,
            ensure_ascii=False,
        ).encode("utf-8")
        return content, "dealer-feed-sample-api.json", "application/json; charset=utf-8"
    if format_ == "schema":
        content = json.dumps(feed_schema_out(), indent=2, ensure_ascii=False).encode("utf-8")
        return content, "dealer-feed-schema.json", "application/json; charset=utf-8"
    raise FeedParseError("unsupported_sample_format", "Sample format must be csv, xml, api, or schema")


def _pydantic_field_errors(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for item in exc.errors(include_input=False):
        field = str(item.get("loc", ["row"])[0])
        errors.setdefault(field, str(item.get("msg", "Invalid value")))
    return errors


def _normalized_record(raw: Mapping[str, Any]) -> tuple[str, ListingForm, str, list[str]]:
    record = DealerFeedRecord.model_validate(raw)
    external_id = record.dealer_external_id.strip()
    if not external_id:
        raise ValueError("dealer_external_id cannot be empty")
    listing_values = record.model_dump(exclude_unset=True, exclude={"dealer_external_id"})
    amount = listing_values.pop("price_amount", None)
    currency = listing_values.pop("currency", None)
    if amount is not None or currency is not None:
        if amount is None or currency is None:
            raise ValueError("price_amount and currency must be supplied together")
        listing_values["price"] = {"amount": amount, "currency": currency}
    listing_values["seller_type"] = "company"
    form = ListingForm.model_validate(listing_values)
    canonical = json.dumps(form.model_dump(exclude_unset=True, mode="json"), sort_keys=True, separators=(",", ":"))
    return (
        external_id,
        form,
        hashlib.sha256(canonical.encode()).hexdigest(),
        sorted(listing_values.keys()),
    )


def _validation_problem(exc: Exception) -> tuple[str, str, dict[str, str]]:
    if isinstance(exc, ValidationError):
        return "invalid_listing_row", "Listing fields are invalid", _pydantic_field_errors(exc)
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return (
            str(detail.get("code", "invalid_listing_row")),
            str(detail.get("message", "Listing fields are invalid")),
            detail.get("field_errors", {}) if isinstance(detail.get("field_errors", {}), dict) else {},
        )
    return "invalid_listing_row", str(exc), {}


def _valid_draft_fields(db: Session, company: Company, raw: Mapping[str, Any]) -> tuple[str, ListingForm, str, list[str]]:
    from app.api.listings import _apply_fields

    external_id, form, payload_hash, source_fields = _normalized_record(raw)
    owner = db.get(User, company.owner_id)
    if owner is None or owner.status != "active":
        fail(403, "seller_unavailable", "Company owner account is not active")
    probe = Listing(
        owner_id=owner.id,
        company_id=company.id,
        slug=f"feed-validation-{uuid4().hex}",
        status="draft",
        revision=1,
        title="",
        description="",
        contact_phone="",
        damaged=False,
        parts_only=False,
    )
    values = form.model_dump(exclude_unset=True)
    _apply_fields(db, probe, dict(values), owner, creating=True)
    return external_id, form, payload_hash, source_fields


def listing_state_digest(db: Session, listing: Listing) -> str:
    fields = {
        field: getattr(listing, field)
        for field in sorted(FEED_FIELDS - {"dealer_external_id"})
    }
    photos = db.scalars(
        select(ListingPhoto)
        .where(ListingPhoto.listing_id == listing.id)
        .order_by(ListingPhoto.position, ListingPhoto.id)
    ).all()
    state = {
        "status": listing.status,
        "fields": fields,
        "photos": [
            {
                "id": str(photo.id),
                "status": photo.status,
                "position": photo.position,
                "is_cover": photo.is_cover,
                "width": photo.width,
                "height": photo.height,
                "perceptual_hash": photo.perceptual_hash,
            }
            for photo in photos
        ],
    }
    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _record_import_error(
    db: Session,
    run: FeedImportRun,
    *,
    row_number: int,
    external_id: str | None,
    code: str,
    message: str,
    field_errors: dict[str, str] | None = None,
) -> None:
    db.add(FeedImportRow(
        run_id=run.id,
        row_number=row_number,
        dealer_external_id=external_id,
        listing_id=None,
        status="rejected",
        action=None,
        error_code=code,
        error_message=message[:2000],
        field_errors=field_errors or {},
    ))
    run.rejected_rows += 1


def create_feed_import(
    db: Session,
    *,
    feed: DealerFeed,
    company_id: UUID,
    initiated_by: UUID,
    rows: list[dict],
    payload_digest: str,
    idempotency_key: str | None,
    dry_run: bool,
    source_filename: str,
    complete_snapshot: bool = False,
    parse_error: FeedParseError | None = None,
) -> FeedImportRun:
    request_hash = _request_digest(payload_digest, dry_run, complete_snapshot)
    if idempotency_key is None:
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    key = idempotency_key.strip()
    if not key or len(key) > 120:
        fail(422, "invalid_idempotency_key", "Idempotency-Key must contain at most 120 characters")
    prior = db.scalar(select(FeedImportRun).where(
        FeedImportRun.feed_id == feed.id,
        FeedImportRun.idempotency_key == key,
    ))
    if prior is not None:
        if not hmac.compare_digest(prior.payload_digest, request_hash):
            fail(409, "idempotency_conflict", "Idempotency-Key was already used for a different import")
        return prior

    run = FeedImportRun(
        feed_id=feed.id,
        company_id=company_id,
        initiated_by=initiated_by,
        idempotency_key=key,
        payload_digest=request_hash,
        dry_run=dry_run,
        status="preview" if dry_run else "failed",
        source_filename=source_filename[:180] or "upload",
        total_rows=0,
        applied_rows=0,
        rejected_rows=0,
    )
    db.add(run)
    db.flush()

    if parse_error is not None:
        run.total_rows = 1
        run.error_code = parse_error.code
        _record_import_error(
            db,
            run,
            row_number=1,
            external_id=None,
            code=parse_error.code,
            message=str(parse_error),
        )
        run.status = "failed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        return run

    run.total_rows = len(rows)
    prepared: list[dict] = []
    validation_company = db.get(Company, company_id)
    if validation_company is None:
        fail(404, "not_found", "Company not found")
    for raw_row in rows:
        row_number = int(raw_row.get("row_number", len(prepared) + 1))
        if raw_row.get("error_code"):
            prepared.append({
                "row_number": row_number,
                "external_id": None,
                "error": (str(raw_row["error_code"]), str(raw_row.get("error_message", "Malformed row")), {}),
            })
            continue
        try:
            external_id, form, content_hash, source_fields = _valid_draft_fields(db, validation_company, raw_row.get("values", {}))
            prepared.append({
                "row_number": row_number,
                "external_id": external_id,
                "form": form,
                "content_hash": content_hash,
                "source_fields": source_fields,
                "values": form.model_dump(exclude_unset=True),
            })
        except (ValidationError, HTTPException, ValueError) as exc:
            code, message, field_errors = _validation_problem(exc)
            raw_id = raw_row.get("values", {}).get("dealer_external_id")
            prepared.append({
                "row_number": row_number,
                "external_id": str(raw_id)[:120] if raw_id else None,
                "error": (code, message, field_errors),
            })

    external_ids = [item["external_id"] for item in prepared if item.get("external_id")]
    seen_ids: set[str] = set()
    duplicate_positions: set[int] = set()
    successfully_processed_external_ids: set[str] = set()
    for index, item in enumerate(prepared):
        external_id = item.get("external_id")
        if external_id is None:
            continue
        if external_id in seen_ids:
            duplicate_positions.add(index)
        else:
            seen_ids.add(external_id)
    for index in duplicate_positions:
        prepared[index]["error"] = (
            "duplicate_external_id",
            "The same dealer_external_id appears more than once in this import",
            {"dealer_external_id": "Must be unique within the import"},
        )

    links_query = (
        select(DealerExternalListingKey)
        .where(
            DealerExternalListingKey.feed_id == feed.id,
            DealerExternalListingKey.dealer_external_id.in_(sorted(set(external_ids)) or ["__no_external_ids__"]),
        )
        .order_by(DealerExternalListingKey.dealer_external_id)
    )
    if not dry_run:
        links_query = links_query.with_for_update(of=DealerExternalListingKey)
    links = db.scalars(links_query).all() if external_ids else []
    links_by_external_id = {link.dealer_external_id: link for link in links}

    linked_listing_ids = sorted({link.listing_id for link in links_by_external_id.values()}, key=str)
    listings_query = select(Listing).where(Listing.id.in_(linked_listing_ids)).order_by(Listing.id)
    if not dry_run:
        listings_query = listings_query.with_for_update(of=Listing)
    locked_listings = db.scalars(listings_query).all() if linked_listing_ids else []
    listings_by_id = {listing.id: listing for listing in locked_listings}

    company_query = select(Company).where(Company.id == company_id)
    if not dry_run:
        company_query = company_query.with_for_update(of=Company)
    company = db.scalar(company_query)
    if company is None or company.status != "approved":
        fail(403, "company_not_approved", "An approved company is required")

    from app.api.listings import _apply_fields

    owner = db.get(User, company.owner_id)
    if owner is None or owner.status != "active":
        fail(403, "seller_unavailable", "Company owner account is not active")

    for item in prepared:
        if item.get("error"):
            continue
        external_id = item["external_id"]
        link = links_by_external_id.get(external_id)
        listing = listings_by_id.get(link.listing_id) if link is not None else None
        if listing is None and link is not None:
            item["error"] = (
                "linked_listing_missing",
                "The listing previously linked to this external ID is unavailable",
                {},
            )
            continue
        if listing is None:
            continue
        changed = link.last_applied_hash != item["content_hash"]
        if changed and listing.status in {"paused", "sold", "blocked", "archived"}:
            item["error"] = (
                "listing_not_editable",
                "A paused, sold, blocked, or archived listing cannot be updated by a feed",
                {},
            )
            continue
        if changed and feed.manual_conflict_policy == "review":
            listing_digest = listing_state_digest(db, listing)
            changed_since_sync = (
                link.last_applied_revision is None
                or listing.revision != link.last_applied_revision
                or link.last_applied_listing_digest is None
                or not hmac.compare_digest(link.last_applied_listing_digest, listing_digest)
            )
            if changed_since_sync:
                item["error"] = (
                    "manual_edit_conflict",
                    "The listing changed after the last feed update; review the listing before resolving this conflict",
                    {"listing": "A manual or photo change needs owner/admin review"},
                )

    if complete_snapshot and not dry_run and any(item.get("error") for item in prepared):
        for item in prepared:
            error = item.get("error") or (
                "complete_snapshot_rejected",
                "The complete snapshot was not applied because at least one row was rejected",
                {},
            )
            _record_import_error(
                db,
                run,
                row_number=item["row_number"],
                external_id=item.get("external_id"),
                code=error[0],
                message=error[1],
                field_errors=error[2],
            )
        run.status = "failed"
        run.error_code = "complete_snapshot_rejected"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    for index, item in enumerate(prepared):
        row_number = item["row_number"]
        external_id = item.get("external_id")
        if item.get("error"):
            code, message, field_errors = item["error"]
            _record_import_error(
                db,
                run,
                row_number=row_number,
                external_id=external_id,
                code=code,
                message=message,
                field_errors=field_errors,
            )
            continue

        link = links_by_external_id.get(external_id)
        listing = listings_by_id.get(link.listing_id) if link is not None else None
        action = "create" if listing is None else ("unchanged" if link.last_applied_hash == item["content_hash"] else "update")
        if listing is not None and action == "update" and listing.revision != link.last_applied_revision:
            action = "overrode_manual"

        if dry_run:
            db.add(FeedImportRow(
                run_id=run.id,
                row_number=row_number,
                dealer_external_id=external_id,
                listing_id=listing.id if listing is not None else None,
                status="preview",
                action=action,
                field_errors={},
            ))
            continue

        try:
            with db.begin_nested():
                values = item["values"]
                if listing is None:
                    listing = Listing(
                        owner_id=company.owner_id,
                        company_id=company.id,
                        slug=f"listing-{uuid4().hex}",
                        status="draft",
                        revision=1,
                        title="",
                        description="",
                        contact_phone="",
                        damaged=False,
                        parts_only=False,
                    )
                    _apply_fields(db, listing, dict(values), owner, creating=True)
                    db.add(listing)
                    db.flush()
                    link = DealerExternalListingKey(
                        feed_id=feed.id,
                        company_id=company.id,
                        dealer_external_id=external_id,
                        listing_id=listing.id,
                        last_applied_hash=item["content_hash"],
                        source_fields=item["source_fields"],
                        last_applied_revision=listing.revision,
                        last_applied_listing_digest=listing_state_digest(db, listing),
                    )
                    db.add(link)
                    action = "created"
                elif action in {"update", "overrode_manual"}:
                    manual_override = action == "overrode_manual"
                    _apply_fields(db, listing, dict(values), owner, creating=False)
                    previous_status = listing.status
                    if previous_status != "draft":
                        db.add(ListingStatusEvent(
                            listing_id=listing.id,
                            actor_id=initiated_by,
                            from_status=previous_status,
                            to_status="draft",
                            revision=listing.revision + 1,
                            reason="feed_update:feed_wins" if manual_override else "feed_update",
                        ))
                    listing.status = "draft"
                    listing.submitted_revision = None
                    listing.moderation_reason = None
                    listing.revision += 1
                    link.last_applied_hash = item["content_hash"]
                    link.source_fields = item["source_fields"]
                    link.last_applied_revision = listing.revision
                    link.last_applied_listing_digest = listing_state_digest(db, listing)
                    action = "overrode_manual" if manual_override else "updated"
                else:
                    action = "unchanged"
                db.add(FeedImportRow(
                    run_id=run.id,
                    row_number=row_number,
                    dealer_external_id=external_id,
                    listing_id=listing.id,
                    status="unchanged" if action == "unchanged" else "draft",
                    action=action,
                    field_errors={},
                ))
                successfully_processed_external_ids.add(external_id)
                if action != "unchanged":
                    run.applied_rows += 1
        except (ValidationError, HTTPException, ValueError) as exc:
            code, message, field_errors = _validation_problem(exc)
            _record_import_error(
                db,
                run,
                row_number=row_number,
                external_id=external_id,
                code=code,
                message=message,
                field_errors=field_errors,
            )

    if run.rejected_rows and run.applied_rows:
        run.status = "partial"
    elif run.rejected_rows:
        run.status = "failed"
    elif dry_run:
        run.status = "preview"
    else:
        run.status = "succeeded"
    run.completed_at = datetime.now(timezone.utc)
    if not dry_run and (not complete_snapshot or run.rejected_rows == 0):
        update_missing_candidate_state(
            db,
            feed,
            present_external_ids=successfully_processed_external_ids,
            payload_digest=payload_digest,
            record_absent=complete_snapshot,
        )
    db.commit()
    db.refresh(run)
    return run
