"""Read-only, moderator-facing listing risk hints.

Signals use evidence already stored with listings and submission events. They
are advisory only: this module never changes listing state. Photo similarity
is intentionally absent because no perceptual-hash value is stored today.
"""

from __future__ import annotations

import hashlib
import re
import csv
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import StringIO
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuditEvent, Listing, ListingPhoto, ListingStatusEvent

ELIGIBLE_STATUSES = ("pending_review", "active")
MIN_PRICE_PEERS = 5
LOW_PRICE_RATIO = Decimal("0.50")
HIGH_SUBMISSION_COUNT = 5
SUBMISSION_WINDOW_MINUTES = 60
MIN_DUPLICATE_DESCRIPTION_LENGTH = 100
MAX_PHASH_DISTANCE = 7

_SIGNAL_ORDER = (
    "duplicate_vin",
    "similar_photo",
    "repeated_phone",
    "repeated_description",
    "external_link",
    "contact_token",
    "configured_stop_word",
    "suspicious_city_change",
    "suspicious_seller_change",
    "unusually_low_price",
    "high_submission_velocity",
)
_SIGNAL_SEVERITY = {
    "duplicate_vin": "high",
    "similar_photo": "medium",
    "repeated_phone": "medium",
    "repeated_description": "medium",
    "external_link": "low",
    "contact_token": "low",
    "configured_stop_word": "low",
    "suspicious_city_change": "medium",
    "suspicious_seller_change": "medium",
    "unusually_low_price": "medium",
    "high_submission_velocity": "high",
}
_FIELD_BY_CODE = {
    "duplicate_vin": "vin",
    "repeated_phone": "contact_phone",
    "repeated_description": "description",
}
_DUPLICATE_SUMMARY = {
    "duplicate_vin": "Совпадение VIN найдено еще в {count} объявлениях",
    "repeated_phone": "Совпадение телефона найдено еще в {count} объявлениях",
    "repeated_description": "Совпадение описания найдено еще в {count} объявлениях",
}

_URL_RE = re.compile(
    r"(?i)(?:https?://|www\.)\S+|\b(?:[a-z0-9-]+\.)+(?:by|com|ru|net|org|io|me|info|site|pro|xyz)\b"
)
_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
_HANDLE_RE = re.compile(r"(?<![\w.])@[a-z0-9_]{4,}", re.IGNORECASE)
_PHONE_TOKEN_RE = re.compile(
    r"(?<!\w)(?:\+\d[\d().\s-]{6,}\d|\(\d{2,4}\)[\d().\s-]{5,}\d)(?!\w)"
)


def _vin_key(value: str | None) -> str | None:
    key = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    # Only compare complete, standard 17-character VINs to avoid flagging
    # partial chassis identifiers or arbitrary seller-entered notes.
    if len(key) != 17 or any(char in key for char in "IOQ"):
        return None
    return key


def _phone_key(value: str | None) -> str | None:
    key = re.sub(r"[^0-9]", "", value or "")
    return key if len(key) >= 7 else None


def _description_key(value: str | None) -> str | None:
    normalized = re.sub(r"\s+", " ", (value or "").strip()).lower()
    if len(normalized) < MIN_DUPLICATE_DESCRIPTION_LENGTH:
        return None
    # md5 is used only as a compact equality key, not for security.
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _signal(
    code: str,
    summary: str,
    related_count: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "severity": _SIGNAL_SEVERITY[code],
        "summary": summary,
    }
    if related_count is not None:
        result["related_count"] = related_count
    return result


def _configured_stop_word_tokens() -> tuple[tuple[str, ...], ...]:
    raw = getattr(get_settings(), "listing_stop_words_csv", "") or ""
    try:
        configured = next(csv.reader(StringIO(str(raw)), skipinitialspace=True), [])
    except csv.Error:
        return ()
    normalized: list[tuple[str, ...]] = []
    for value in configured:
        tokens = tuple(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))
        if tokens and tokens not in normalized:
            normalized.append(tokens)
    return tuple(normalized)


def _contains_token_sequence(text: str, sequence: tuple[str, ...]) -> bool:
    tokens = re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
    width = len(sequence)
    return any(tuple(tokens[index:index + width]) == sequence for index in range(len(tokens) - width + 1))


def _add_configured_stop_word_signals(
    listings: list[Listing],
    output: dict[UUID, list[dict[str, Any]]],
) -> None:
    configured = _configured_stop_word_tokens()
    if not configured:
        return
    for listing in listings:
        description = listing.description or ""
        if any(_contains_token_sequence(description, phrase) for phrase in configured):
            output[listing.id].append(
                _signal(
                    "configured_stop_word",
                    "В описании найдено совпадение с настроенным стоп-словом",
                )
            )


def _add_change_risk_signals(
    db: Session,
    listings: list[Listing],
    output: dict[UUID, list[dict[str, Any]]],
) -> None:
    listing_ids = {listing.id for listing in listings}
    if not listing_ids:
        return
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "listing",
            AuditEvent.entity_id.in_(listing_ids),
            AuditEvent.action == "listing_edited",
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    ).all()
    latest: dict[UUID, AuditEvent] = {}
    for event in events:
        if isinstance(event.details, dict) and event.details.get("reason") == "seller_photo_edit":
            continue
        latest.setdefault(event.entity_id, event)

    for listing in listings:
        event = latest.get(listing.id)
        if event is None or not isinstance(event.details, dict):
            continue
        if event.details.get("from_status") not in {"active", "pending_review"}:
            continue
        raw_keys = event.details.get("changed_field_keys", ())
        if not isinstance(raw_keys, (list, tuple)):
            continue
        field_keys = {key for key in raw_keys[:64] if isinstance(key, str)}
        if field_keys.intersection({"region_id", "city_id", "manual_city"}):
            output[listing.id].append(
                _signal("suspicious_city_change", "В последней редакции изменено местоположение объявления")
            )
        if field_keys.intersection({"seller_type", "company_id"}):
            output[listing.id].append(
                _signal("suspicious_seller_change", "В последней редакции изменён тип продавца")
            )


def _add_duplicate_signals(
    db: Session,
    listings: list[Listing],
    *,
    code: str,
    python_key,
    database_expression,
    output: dict[UUID, list[dict[str, Any]]],
) -> None:
    candidate_keys = {
        listing.id: key
        for listing in listings
        if (key := python_key(getattr(listing, _FIELD_BY_CODE[code])))
    }
    if not candidate_keys:
        return

    keys = set(candidate_keys.values())
    rows = db.execute(
        select(Listing.id, database_expression.label("normalized_key")).where(
            Listing.status.in_(ELIGIBLE_STATUSES),
            database_expression.in_(keys),
        )
    ).all()
    counts = Counter(key for _, key in rows if key)
    for listing_id, key in candidate_keys.items():
        matching_count = counts.get(key, 0) - 1
        if matching_count > 0:
            summary = _DUPLICATE_SUMMARY[code].format(count=matching_count)
            output[listing_id].append(_signal(code, summary, matching_count))


def _add_low_price_signals(
    db: Session,
    listings: list[Listing],
    output: dict[UUID, list[dict[str, Any]]],
) -> None:
    candidates = {
        listing.id: (listing.model_id, listing.year, listing.currency, Decimal(listing.price_amount))
        for listing in listings
        if listing.model_id is not None
        and listing.year is not None
        and listing.currency
        and listing.price_amount is not None
        and Decimal(listing.price_amount) > 0
    }
    if not candidates:
        return

    peer_groups = {(model_id, year, currency) for model_id, year, currency, _ in candidates.values()}
    peer_rows = db.execute(
        select(
            Listing.id,
            Listing.model_id,
            Listing.year,
            Listing.currency,
            Listing.price_amount,
        ).where(
            Listing.status.in_(ELIGIBLE_STATUSES),
            Listing.price_amount.is_not(None),
            Listing.price_amount > 0,
            tuple_(Listing.model_id, Listing.year, Listing.currency).in_(peer_groups),
        )
    ).all()
    prices: dict[tuple[UUID, int, str], list[tuple[UUID, Decimal]]] = defaultdict(list)
    for listing_id, model_id, year, currency, amount in peer_rows:
        prices[(model_id, year, currency)].append((listing_id, Decimal(amount)))

    for listing_id, (model_id, year, currency, amount) in candidates.items():
        peers = [
            peer_amount
            for peer_id, peer_amount in prices[(model_id, year, currency)]
            if peer_id != listing_id
        ]
        if len(peers) < MIN_PRICE_PEERS:
            continue
        peer_median = median(peers)
        if amount < peer_median * LOW_PRICE_RATIO:
            output[listing_id].append(
                _signal(
                    "unusually_low_price",
                    f"Цена ниже половины медианы по {len(peers)} объявлениям той же модели, года и валюты",
                    len(peers),
                )
            )


def _add_submission_velocity_signals(
    db: Session,
    listings: list[Listing],
    output: dict[UUID, list[dict[str, Any]]],
) -> None:
    owner_ids = {listing.owner_id for listing in listings}
    if not owner_ids:
        return

    now = db.scalar(select(func.now()))
    if now is None:
        now = datetime.now(UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    cutoff = now - timedelta(minutes=SUBMISSION_WINDOW_MINUTES)
    events = db.execute(
        select(ListingStatusEvent.listing_id, Listing.owner_id)
        .join(Listing, Listing.id == ListingStatusEvent.listing_id)
        .where(
            Listing.owner_id.in_(owner_ids),
            ListingStatusEvent.to_status == "pending_review",
            ListingStatusEvent.created_at >= cutoff,
        )
    ).all()
    recent_by_owner: dict[UUID, set[UUID]] = defaultdict(set)
    recent_listing_ids: set[UUID] = set()
    for listing_id, owner_id in events:
        recent_by_owner[owner_id].add(listing_id)
        recent_listing_ids.add(listing_id)

    for listing in listings:
        count = len(recent_by_owner.get(listing.owner_id, ()))
        if listing.id in recent_listing_ids and count >= HIGH_SUBMISSION_COUNT:
            output[listing.id].append(
                _signal(
                    "high_submission_velocity",
                    f"За последние {SUBMISSION_WINDOW_MINUTES} минут с аккаунта подано {count} объявлений",
                    count,
                )
            )


def _phash_key(value: str | None) -> int | None:
    normalized = (value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{16}", normalized) is None:
        return None
    return int(normalized, 16)


def _add_similar_photo_signals(
    db: Session,
    listings: list[Listing],
    output: dict[UUID, list[dict[str, Any]]],
) -> None:
    listing_ids = [listing.id for listing in listings]
    rows = db.execute(
        select(ListingPhoto.listing_id, ListingPhoto.perceptual_hash).where(
            ListingPhoto.listing_id.in_(listing_ids),
            ListingPhoto.status == "ready",
            ListingPhoto.perceptual_hash.is_not(None),
        )
    ).all()
    target_hashes: dict[UUID, set[int]] = defaultdict(set)
    for listing_id, raw_hash in rows:
        parsed = _phash_key(raw_hash)
        if parsed is not None:
            target_hashes[listing_id].add(parsed)
    if not target_hashes:
        return

    targets_by_band: list[dict[str, list[tuple[UUID, int]]]] = [
        defaultdict(list) for _ in range(8)
    ]
    for listing_id, hashes in target_hashes.items():
        for parsed in hashes:
            fingerprint = f"{parsed:016x}"
            for band_index in range(8):
                start = band_index * 2
                targets_by_band[band_index][fingerprint[start:start + 2]].append(
                    (listing_id, parsed)
                )

    band_filters = [
        func.substr(ListingPhoto.perceptual_hash, start, 2).in_(set(targets_by_band[index]))
        for index, start in enumerate(range(1, 17, 2))
    ]
    candidates = db.execute(
        select(ListingPhoto.listing_id, ListingPhoto.perceptual_hash)
        .join(Listing, Listing.id == ListingPhoto.listing_id)
        .where(
            Listing.status.in_(ELIGIBLE_STATUSES),
            ListingPhoto.status == "ready",
            ListingPhoto.perceptual_hash.is_not(None),
            or_(*band_filters),
        )
    ).all()

    related: dict[UUID, set[UUID]] = defaultdict(set)
    for other_listing_id, raw_hash in candidates:
        other_hash = _phash_key(raw_hash)
        if other_hash is None:
            continue
        fingerprint = f"{other_hash:016x}"
        possible_targets: set[tuple[UUID, int]] = set()
        for band_index in range(8):
            start = band_index * 2
            possible_targets.update(
                targets_by_band[band_index].get(fingerprint[start:start + 2], ())
            )
        for target_id, target_hash in possible_targets:
            if target_id != other_listing_id and (target_hash ^ other_hash).bit_count() <= MAX_PHASH_DISTANCE:
                related[target_id].add(other_listing_id)

    for listing_id, matches in related.items():
        output[listing_id].append(
            _signal(
                "similar_photo",
                f"Похожие фотографии найдены ещё в {len(matches)} объявлениях",
                len(matches),
            )
        )


def collect_listing_risk_signals(
    db: Session,
    listings: list[Listing],
) -> dict[UUID, list[dict[str, Any]]]:
    """Return sanitized, non-blocking risk hints for one moderation page.

    The grouped/look-up queries are independent of the queue page size; no
    per-listing queries are issued here.
    """
    eligible = [listing for listing in listings if listing.status in ELIGIBLE_STATUSES]
    output: dict[UUID, list[dict[str, Any]]] = {listing.id: [] for listing in listings}
    if not eligible:
        return output

    vin_expression = func.regexp_replace(func.upper(Listing.vin), "[^A-Z0-9]", "", "g")
    _add_duplicate_signals(
        db,
        eligible,
        code="duplicate_vin",
        python_key=_vin_key,
        database_expression=vin_expression,
        output=output,
    )

    phone_expression = func.regexp_replace(Listing.contact_phone, "[^0-9]", "", "g")
    _add_duplicate_signals(
        db,
        eligible,
        code="repeated_phone",
        python_key=_phone_key,
        database_expression=phone_expression,
        output=output,
    )

    description_expression = func.md5(
        func.lower(
            func.regexp_replace(
                func.trim(Listing.description),
                "[[:space:]]+",
                " ",
                "g",
            )
        )
    )
    _add_duplicate_signals(
        db,
        eligible,
        code="repeated_description",
        python_key=_description_key,
        database_expression=description_expression,
        output=output,
    )

    for listing in eligible:
        if _URL_RE.search(listing.description or ""):
            output[listing.id].append(
                _signal("external_link", "В описании найдена внешняя ссылка")
            )
        if (
            _EMAIL_RE.search(listing.description or "")
            or _HANDLE_RE.search(listing.description or "")
            or _PHONE_TOKEN_RE.search(listing.description or "")
        ):
            output[listing.id].append(
                _signal("contact_token", "В описании найдены телефон, email или аккаунт")
            )

    _add_configured_stop_word_signals(eligible, output)
    _add_change_risk_signals(db, eligible, output)
    _add_low_price_signals(db, eligible, output)
    _add_submission_velocity_signals(db, eligible, output)
    _add_similar_photo_signals(db, eligible, output)

    for signals in output.values():
        signals.sort(key=lambda item: _SIGNAL_ORDER.index(item["code"]))
    return output
