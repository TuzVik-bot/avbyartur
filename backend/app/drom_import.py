from __future__ import annotations

import csv
import hashlib
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogImport,
    CatalogMake,
    CatalogModel,
    CatalogModification,
)


class DromInputError(ValueError):
    pass


SOURCE_NAME = "Drom"
SOURCE_DOMAIN = "www.drom.ru"
REQUIRED_COLUMNS = {
    "source",
    "source_id",
    "source_url",
    "make",
    "make_slug",
    "model",
    "model_slug",
    "generation",
    "generation_url",
    "trim",
    "production_period",
    "engine_code",
    "frame_code",
    "engine_l",
    "power_hp",
    "fuel",
    "transmission",
    "drive",
    "summary",
}
SPEC_COLUMNS = (
    "engine_code",
    "frame_code",
    "engine_l",
    "power_hp",
    "fuel",
    "transmission",
    "drive",
)
ENGINE_SPEC_COLUMNS = ("engine_code", "frame_code", "engine_l", "power_hp")
GENERATION_RANGE = re.compile(
    r"(?<!\d)(?:(?P<start_month>\d{1,2})\.)?(?P<start>(?:18|19|20|21)\d{2})"
    r"\s*[-–—]\s*(?:(?P<end_month>\d{1,2})\.)?(?P<end>(?:18|19|20|21)\d{2})(?!\d)"
)
GENERATION_OPEN_RANGE = re.compile(
    r"(?<!\d)(?:(?P<start_month>\d{1,2})\.)?(?P<start>(?:18|19|20|21)\d{2})"
    r"\s*[-–—]\s*н\.в\.(?!\w)",
    re.IGNORECASE,
)
PRODUCTION_RANGE = re.compile(
    r"^\s*(?P<start_month>\d{1,2})\.(?P<start_year>\d{4})\s*[-–—]\s*"
    r"(?P<end_month>\d{1,2})\.(?P<end_year>\d{4})\s*$"
)
OPEN_PRODUCTION_RANGE = re.compile(
    r"^\s*(?P<start_month>\d{1,2})\.(?P<start_year>\d{4})\s*[-–—]\s*н\.в\.\s*$",
    re.IGNORECASE,
)
BODY_TYPES = {
    "sedan": {
        "name": "Седан",
        "existing_slugs": {"sedan"},
        "name_aliases": {"седан"},
        "markers": (r"\bsedan\b", r"\bседан\b"),
    },
    "station-wagon": {
        "name": "Универсал",
        "existing_slugs": {"station-wagon"},
        "name_aliases": {"универсал", "station wagon", "estate", "wagon"},
        "markers": (
            r"\bstation\s+wagon\b",
            r"\bestate\b",
            r"\bwagon\b",
            r"\bуниверсал\b",
        ),
    },
    "hatchback": {
        "name": "Хэтчбэк",
        "existing_slugs": {"hatchback"},
        "name_aliases": {"хэтчбек", "хэтчбэк", "hatchback"},
        "markers": (r"\bhatchback\b", r"\bхэтчб[еэ]к\b"),
    },
    "liftback": {
        "name": "Лифтбэк",
        "existing_slugs": {"liftback"},
        "name_aliases": {"лифтбек", "лифтбэк", "liftback"},
        "markers": (r"\bliftback\b", r"\bлифтб[еэ]к\b"),
    },
    "coupe": {
        "name": "Купе",
        "existing_slugs": {"coupe"},
        "name_aliases": {"купе", "coupe", "coupé"},
        "markers": (r"\bcoupe\b", r"\bcoupé\b", r"\bкупе\b"),
    },
    "sport-utility-vehicle": {
        "name": "SUV",
        "existing_slugs": {"sport-utility-vehicle"},
        "name_aliases": {"suv", "sport utility vehicle", "внедорожник"},
        "markers": (r"\bsuv\b", r"\bsport\s+utility\s+vehicle\b", r"\bвнедорожник\b"),
    },
    "minivan": {
        "name": "Минивэн",
        "existing_slugs": {"minivan"},
        "name_aliases": {"минивэн", "minivan", "mpv"},
        "markers": (r"\bminivan\b", r"\bmpv\b", r"\bминивэн\b"),
    },
    "pickup": {
        "name": "Пикап",
        "existing_slugs": {"pickup"},
        "name_aliases": {"пикап", "pickup"},
        "markers": (r"\bpickup\b", r"\bпикап\b"),
    },
}


@dataclass(frozen=True)
class _Record:
    raw: dict[str, str]
    make_slug: str
    model_slug: str
    generation_key: tuple[str, str, str]


def _chunks(values: list[Any], size: int = 500):
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_drom_url(value: str, field: str, row_number: int) -> str:
    value = value.strip()
    try:
        parsed = urlsplit(value)
    except ValueError:
        parsed = None
    try:
        valid_port = parsed is not None and parsed.port in (None, 443)
    except (ValueError, AttributeError):
        valid_port = False
    if (
        parsed is None
        or any(character.isspace() for character in value)
        or parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != SOURCE_DOMAIN
        or parsed.username is not None
        or parsed.password is not None
        or not valid_port
        or not parsed.path.startswith("/catalog/")
    ):
        raise DromInputError(
            f"row {row_number}: {field} must be an HTTPS www.drom.ru catalog URL"
        )

    # URLs that differ only by host casing, an explicit default port, a
    # trailing slash, or a fragment identify the same Drom catalog resource.
    # Preserve the query string because it can be meaningful to the source.
    path = parsed.path.rstrip("/") + "/"

    def normalize_percent_encoding(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        if character.isascii() and (character.isalnum() or character in "-._~"):
            return character
        return f"%{match.group(1).upper()}"

    path = re.sub(r"%([0-9a-fA-F]{2})", normalize_percent_encoding, path)
    return urlunsplit(("https", SOURCE_DOMAIN, path, parsed.query, ""))


def _month_index(month: str, year: str) -> int | None:
    parsed_month = int(month)
    parsed_year = int(year)
    if (
        parsed_month < 1
        or parsed_month > 12
        or parsed_year < 1886
        or parsed_year > 2100
    ):
        return None
    return parsed_year * 12 + parsed_month


def _period_status(value: str) -> str:
    if not value.strip():
        return "missing"
    open_match = OPEN_PRODUCTION_RANGE.fullmatch(value)
    if open_match is not None:
        start = _month_index(
            open_match.group("start_month"), open_match.group("start_year")
        )
        return "valid" if start is not None else "malformed"
    match = PRODUCTION_RANGE.fullmatch(value)
    if match is None:
        return "malformed"
    start = _month_index(match.group("start_month"), match.group("start_year"))
    end = _month_index(match.group("end_month"), match.group("end_year"))
    if start is None or end is None:
        return "malformed"
    if end < start:
        return "end_before_start"
    return "valid"


def _generation_years(label: str) -> tuple[int | None, int | None, str]:
    closed_matches = list(GENERATION_RANGE.finditer(label))
    open_matches = list(GENERATION_OPEN_RANGE.finditer(label))
    if len(closed_matches) + len(open_matches) != 1:
        return None, None, "unknown"

    if open_matches:
        match = open_matches[0]
        start = int(match.group("start"))
        month = match.group("start_month")
        if (
            start < 1886
            or start > 2100
            or (month is not None and not 1 <= int(month) <= 12)
        ):
            return None, None, "unknown"
        return start, None, "open"

    match = closed_matches[0]
    start = int(match.group("start"))
    end = int(match.group("end"))
    months = (match.group("start_month"), match.group("end_month"))
    if any(month is not None and not 1 <= int(month) <= 12 for month in months):
        return None, None, "unknown"
    if start < 1886 or end > 2100 or start > end:
        return None, None, "unknown"
    return start, end, "closed"


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold().replace("ё", "е")
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.category(character).startswith("M")
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " " for character in without_marks
        ).split()
    )


def _normalized_without_make(value: str, make_name: str) -> str:
    normalized_value = _normalize_text(value)
    normalized_make = _normalize_text(make_name)
    if normalized_make and normalized_value.startswith(f"{normalized_make} "):
        return normalized_value[len(normalized_make) + 1 :].strip()
    return normalized_value


def _body_category(label: str) -> tuple[str | None, str]:
    normalized = unicodedata.normalize("NFKC", label).casefold().replace("ё", "е")
    matches = {
        category
        for category, body_type in BODY_TYPES.items()
        if any(re.search(pattern, normalized) for pattern in body_type["markers"])
    }
    if len(matches) == 1:
        return next(iter(matches)), "recognized"
    return None, "ambiguous" if matches else "unrecognized"


def _load_batch(
    path: Path,
) -> tuple[
    list[_Record],
    dict[str, dict],
    dict[str, dict],
    dict[tuple[str, str, str], dict],
    str,
    dict[str, int],
]:
    checksum = _sha256_file(path)
    records: list[_Record] = []
    makes: dict[str, dict] = {}
    models: dict[tuple[str, str], dict] = {}
    generations: dict[tuple[str, str, str], dict] = {}
    source_urls: set[str] = set()
    quality: dict[str, int] = defaultdict(int)
    rows_by_make: dict[str, int] = defaultdict(int)

    with path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(
            set(reader.fieldnames)
        ):
            missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
            raise DromInputError(
                f"CSV is missing required columns: {', '.join(missing)}"
            )
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise DromInputError("CSV contains duplicate column names")

        for row_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise DromInputError(
                    f"row {row_number}: CSV has more values than columns"
                )
            row = {
                key: value if value is not None else ""
                for key, value in raw_row.items()
            }
            required_text = (
                "source",
                "source_id",
                "source_url",
                "make",
                "make_slug",
                "model",
                "model_slug",
                "generation",
                "generation_url",
            )
            if any(not row[field].strip() for field in required_text):
                raise DromInputError(
                    f"row {row_number}: source identity fields must be non-empty"
                )
            if row["source"].strip() != "drom.ru":
                raise DromInputError(f"row {row_number}: expected source drom.ru")
            row["source_url"] = _valid_drom_url(
                row["source_url"], "source_url", row_number
            )
            if row["source_url"] in source_urls:
                raise DromInputError(
                    f"row {row_number}: duplicate source_url {row['source_url']}"
                )
            source_urls.add(row["source_url"])
            _valid_drom_url(row["generation_url"], "generation_url", row_number)

            make_slug = row["make_slug"].strip()
            model_slug = row["model_slug"].strip()
            make = makes.setdefault(make_slug, {"name": row["make"], "slug": make_slug})
            if make["name"] != row["make"]:
                raise DromInputError(
                    f"row {row_number}: make_slug {make_slug} has inconsistent names"
                )
            rows_by_make[row["make"]] += 1
            model_key = (make_slug, model_slug)
            model = models.setdefault(
                model_key, {"name": row["model"], "slug": model_slug}
            )
            if model["name"] != row["model"]:
                raise DromInputError(
                    f"row {row_number}: model key {make_slug}/{model_slug} has inconsistent names"
                )
            generation_key = (make_slug, model_slug, row["generation_url"])
            generation = generations.setdefault(
                generation_key, {"name": row["generation"]}
            )
            if generation["name"] != row["generation"]:
                raise DromInputError(
                    f"row {row_number}: generation URL has inconsistent labels"
                )

            records.append(_Record(row, make_slug, model_slug, generation_key))
            if not row["trim"].strip():
                quality["missing_trim_rows"] += 1
            period_status = _period_status(row["production_period"])
            if period_status != "valid":
                quality[f"production_period_{period_status}_rows"] += 1
            has_engine_specs = any(row[key].strip() for key in ENGINE_SPEC_COLUMNS)
            has_summary = bool(row["summary"].strip())
            if has_summary:
                quality["summary_present_rows"] += 1
            if has_summary and not has_engine_specs:
                quality["summary_only_engine_specs_rows"] += 1
            elif not has_engine_specs:
                quality["missing_engine_specs_rows"] += 1
            for numeric_key in ("engine_l", "power_hp"):
                value = row[numeric_key].strip()
                if value:
                    try:
                        parsed_value = Decimal(value)
                        if not parsed_value.is_finite() or (
                            numeric_key == "power_hp"
                            and parsed_value != parsed_value.to_integral_value()
                        ):
                            raise InvalidOperation
                    except InvalidOperation:
                        quality[f"invalid_{numeric_key}_rows"] += 1

    generation_year_statuses = [
        _generation_years(item["name"])[2] for item in generations.values()
    ]
    quality["generation_years_open_end"] = generation_year_statuses.count("open")
    quality["generation_years_unknown"] = generation_year_statuses.count("unknown")
    quality["generation_body_markers_unrecognized"] = 0
    quality["generation_body_markers_ambiguous"] = 0
    for item in generations.values():
        _, status = _body_category(item["name"])
        if status != "recognized":
            quality[f"generation_body_markers_{status}"] += 1
    quality["makes"] = len(makes)
    quality["models"] = len(models)
    quality["generations"] = len(generations)
    quality["source_rows"] = len(records)
    quality["source_rows_by_make"] = dict(sorted(rows_by_make.items()))
    return records, makes, models, generations, checksum, dict(quality)


def _insert_ignore(db: Session, model, values: list[dict]) -> int:
    inserted = 0
    for batch in _chunks(values):
        result = db.scalars(
            pg_insert(model).values(batch).on_conflict_do_nothing().returning(model.id)
        )
        inserted += len(result.all())
    return inserted


def _select_in(db: Session, model, column, values: list[Any]) -> list[Any]:
    rows = []
    for batch in _chunks(values, 1000):
        rows.extend(db.scalars(select(model).where(column.in_(batch))).all())
    return rows


def _stable_external(prefix: str, key: str) -> str:
    return f"drom:{prefix}:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _modification_external_id(source_url: str) -> str:
    return _stable_external("modification-url", source_url)


def _slug_piece(value: str) -> str:
    piece = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-_").lower()
    return piece or hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _unique_slug(base: str, suffix: str, max_length: int) -> str:
    prefix = base[: max_length - len(suffix) - 1].rstrip("-_")
    return f"{prefix}-{suffix}"


def _body_type_candidates(
    row_list: list[CatalogBodyType], category: str
) -> list[CatalogBodyType]:
    definition = BODY_TYPES[category]
    aliases = {_normalize_text(name) for name in definition["name_aliases"]}
    slugs = definition["existing_slugs"]
    return [
        row
        for row in row_list
        if row.slug in slugs or _normalize_text(row.name) in aliases
    ]


def _get_or_create_body_types(
    db: Session, categories: list[str], *, dry_run: bool, counts: dict[str, int]
) -> dict[str, tuple[Any, str]]:
    all_rows = db.scalars(select(CatalogBodyType)).all() if categories else []
    by_category: dict[str, tuple[Any, str]] = {}
    pending = []
    for category in categories:
        candidates = _body_type_candidates(all_rows, category)
        if len(candidates) > 1:
            raise DromInputError(
                f"multiple existing catalog body types match Drom marker {category}"
            )
        if len(candidates) == 1:
            by_category[category] = (candidates[0].id, candidates[0].slug)
            counts["body_types_reused"] += 1
            continue
        existing_drom = next(
            (
                row
                for row in all_rows
                if row.external_id == _stable_external("body-type", category)
                and row.source_name == SOURCE_NAME
            ),
            None,
        )
        if existing_drom is not None:
            by_category[category] = (existing_drom.id, existing_drom.slug)
            counts["body_types_reused"] += 1
            continue
        if any(
            row.external_id == _stable_external("body-type", category)
            for row in all_rows
        ):
            raise DromInputError(f"Drom body type identity collision for {category}")

        base_slug = category if not candidates else f"drom-{category}"
        used = {row.slug for row in all_rows}
        slug = base_slug
        if slug in used:
            slug = _unique_slug(
                base_slug, hashlib.sha256(category.encode()).hexdigest()[:8], 100
            )
        row_id = uuid4()
        body_name = BODY_TYPES[category]["name"]
        values = {
            "id": row_id,
            "slug": slug,
            "name": body_name,
            "external_id": _stable_external("body-type", category),
            "source_name": SOURCE_NAME,
            "source_metadata": {"name": SOURCE_NAME, "normalized_marker": category},
            "manual_override": False,
        }
        pending.append(values)
        by_category[category] = (row_id, slug)
        counts["body_types_created"] += 1

    if pending and not dry_run:
        counts["body_types_inserted"] += _insert_ignore(db, CatalogBodyType, pending)
        ids = [row["id"] for row in pending]
        inserted_rows = _select_in(db, CatalogBodyType, CatalogBodyType.id, ids)
        inserted_ids = {row.id: row for row in inserted_rows}
        for category, (row_id, _) in list(by_category.items()):
            if row_id in inserted_ids:
                by_category[category] = (row_id, inserted_ids[row_id].slug)
    return by_category


def _plan_makes(
    db: Session, makes: dict[str, dict], *, dry_run: bool, counts: dict[str, int]
) -> dict[str, Any]:
    existing_rows = db.scalars(
        select(CatalogMake).where(CatalogMake.slug.in_(list(makes)))
    ).all()
    by_slug = {row.slug: row for row in existing_rows}
    pending = []
    ids = {}
    for slug, item in makes.items():
        existing = by_slug.get(slug)
        if existing is not None:
            ids[slug] = existing.id
            counts["makes_reused"] += 1
            counts["makes_matched"] += 1
            continue
        external_id = _stable_external("make", slug)
        if any(row.external_id == external_id for row in existing_rows):
            raise DromInputError(f"Drom make identity collision for {slug}")
        row_id = uuid4()
        ids[slug] = row_id
        pending.append(
            {
                "id": row_id,
                "slug": slug,
                "name": item["name"],
                "aliases": [],
                "external_id": external_id,
                "source_name": SOURCE_NAME,
                "source_metadata": {"name": SOURCE_NAME, "make_slug": slug},
                "manual_override": False,
                "sort_order": 0,
            }
        )
        counts["makes_created"] += 1
    if pending and not dry_run:
        counts["makes_inserted"] += _insert_ignore(db, CatalogMake, pending)
        rows = db.scalars(
            select(CatalogMake).where(
                CatalogMake.slug.in_([row["slug"] for row in pending])
            )
        ).all()
        by_slug.update({row.slug: row for row in rows})
        for slug in ids:
            if slug in by_slug:
                ids[slug] = by_slug[slug].id
            else:
                raise DromInputError(f"Drom make insert did not resolve {slug}")
    return ids


def _plan_models(
    db: Session,
    models: dict[tuple[str, str], dict],
    makes: dict[str, dict],
    make_ids: dict[str, Any],
    *,
    dry_run: bool,
    counts: dict[str, int],
) -> dict[tuple[str, str], Any]:
    rows = db.scalars(
        select(CatalogModel).where(CatalogModel.make_id.in_(list(make_ids.values())))
    ).all()
    by_make: dict[Any, list[CatalogModel]] = defaultdict(list)
    for row in rows:
        by_make[row.make_id].append(row)

    result: dict[tuple[str, str], Any] = {}
    pending = []
    for key, item in models.items():
        make_slug, drom_slug = key
        make_id = make_ids[make_slug]
        current_make_name = makes[make_slug]["name"]
        external_id = _stable_external("model", f"{make_slug}/{drom_slug}")
        identity_rows = [
            row for row in by_make.get(make_id, []) if row.external_id == external_id
        ]
        if identity_rows:
            if len(identity_rows) != 1 or identity_rows[0].source_name != SOURCE_NAME:
                raise DromInputError(
                    f"Drom model identity collision for {make_slug}/{drom_slug}"
                )
            result[key] = identity_rows[0].id
            counts["models_reused"] += 1
            counts["models_drom_existing"] += 1
            resolution = (identity_rows[0].source_metadata or {}).get(
                "model_match_status"
            )
            if resolution in {"ambiguous", "unmatched"}:
                counts[f"models_{resolution}"] += 1
            continue

        drom_slug_values = {
            _normalize_text(drom_slug),
            _normalize_text(f"{make_slug}-{drom_slug}"),
        }
        drom_name_values = {
            _normalize_text(item["name"]),
            _normalized_without_make(item["name"], current_make_name),
        }
        drom_slug_values.discard("")
        drom_name_values.discard("")
        candidates = {}
        for row in by_make.get(make_id, []):
            rules = set()
            normalized_row_slug = _normalize_text(row.slug)
            if normalized_row_slug in drom_slug_values:
                rules.add(
                    "make_prefixed_slug"
                    if normalized_row_slug
                    == _normalize_text(f"{make_slug}-{drom_slug}")
                    else "slug"
                )
            row_name_values = {
                _normalize_text(row.name),
                _normalized_without_make(row.name, current_make_name),
            }
            if row_name_values & drom_name_values:
                rules.add("normalized_name")
            alias_values = {
                normalized
                for alias in (row.aliases or [])
                if isinstance(alias, str)
                for normalized in (
                    _normalize_text(alias),
                    _normalized_without_make(alias, current_make_name),
                )
            }
            if alias_values & (drom_name_values | drom_slug_values):
                rules.add("normalized_alias")
            if rules:
                candidates[row.id] = (row, rules)
        if len(candidates) == 1:
            candidate, matched_rules = next(iter(candidates.values()))
            result[key] = candidate.id
            counts["models_reused"] += 1
            counts["models_matched"] += 1
            for rule in matched_rules:
                counts[f"models_matched_by_{rule}"] += 1
            if len(matched_rules) > 1:
                counts["models_multi_rule_match"] += 1
            continue

        resolution = "ambiguous" if len(candidates) > 1 else "unmatched"
        counts[f"models_{resolution}"] += 1
        if resolution == "ambiguous":
            for rule in {rule for _, rules in candidates.values() for rule in rules}:
                counts[f"models_ambiguous_with_{rule}"] += 1

        occupied_slugs = {row.slug for row in by_make.get(make_id, [])}
        stored_slug = drom_slug
        if stored_slug in occupied_slugs:
            stored_slug = _unique_slug(
                drom_slug,
                f"drom-{hashlib.sha256(f'{make_slug}/{drom_slug}'.encode()).hexdigest()[:10]}",
                160,
            )
        row_id = uuid4()
        result[key] = row_id
        pending.append(
            {
                "id": row_id,
                "make_id": make_id,
                "slug": stored_slug,
                "name": item["name"],
                "aliases": [],
                "external_id": external_id,
                "source_name": SOURCE_NAME,
                "source_metadata": {
                    "name": SOURCE_NAME,
                    "make_slug": make_slug,
                    "model_slug": drom_slug,
                    "model_match_status": resolution,
                },
                "manual_override": False,
            }
        )
        counts["models_created"] += 1

    if pending and not dry_run:
        counts["models_inserted"] += _insert_ignore(db, CatalogModel, pending)
        inserted = _select_in(
            db,
            CatalogModel,
            CatalogModel.external_id,
            [row["external_id"] for row in pending],
        )
        by_external = {row.external_id: row for row in inserted}
        for key, item in models.items():
            external_id = _stable_external("model", f"{key[0]}/{key[1]}")
            if external_id in by_external:
                result[key] = by_external[external_id].id
            elif key not in result:
                raise DromInputError(
                    f"Drom model insert did not resolve {key[0]}/{key[1]}"
                )
    return result


def _generation_slug(generation_url: str) -> str:
    path_part = urlsplit(generation_url).path.rstrip("/").split("/")[-1]
    slug = path_part.strip()
    if not slug or len(slug) > 160:
        return f"drom-generation-{hashlib.sha256(generation_url.encode()).hexdigest()[:32]}"
    return slug


def _plan_generations(
    db: Session,
    generations: dict[tuple[str, str, str], dict],
    model_ids: dict[tuple[str, str], Any],
    body_type_ids: dict[str, tuple[Any, str]],
    *,
    dry_run: bool,
    counts: dict[str, int],
) -> dict[tuple[str, str, str], Any]:
    external_ids = {
        key: _stable_external("generation", f"{key[0]}/{key[1]}/{key[2]}")
        for key in generations
    }
    existing_external = _select_in(
        db,
        CatalogGeneration,
        CatalogGeneration.external_id,
        list(external_ids.values()),
    )
    by_external = {row.external_id: row for row in existing_external}
    existing_by_model = db.scalars(
        select(CatalogGeneration).where(
            CatalogGeneration.model_id.in_(list(model_ids.values()))
        )
    ).all()
    by_natural = {(row.model_id, row.slug): row for row in existing_by_model}
    planned_natural: set[tuple[Any, str]] = set()
    result: dict[tuple[str, str, str], Any] = {}
    pending = []
    updates = []

    for key, item in generations.items():
        model_id = model_ids[(key[0], key[1])]
        external_id = external_ids[key]
        category, _ = _body_category(item["name"])
        type_info = body_type_ids.get(category) if category else None
        metadata = {
            "name": SOURCE_NAME,
            "source": "drom.ru",
            "generation_url": key[2],
            "generation_label": item["name"],
        }
        if category and type_info:
            metadata["body_type_slug"] = type_info[1]

        current = by_external.get(external_id)
        if current is not None:
            if current.model_id != model_id:
                raise DromInputError(f"generation URL parent changed for {key[2]}")
            result[key] = current.id
            counts["generations_reused"] += 1
            years = _generation_years(item["name"])
            if current.source_name != SOURCE_NAME:
                raise DromInputError(f"Drom generation identity collision for {key[2]}")
            if not current.manual_override and (
                current.name != item["name"]
                or current.year_from != years[0]
                or current.year_to != years[1]
                or current.source_metadata != metadata
            ):
                updates.append(
                    {
                        "id": current.id,
                        "name": item["name"],
                        "year_from": years[0],
                        "year_to": years[1],
                        "source_name": SOURCE_NAME,
                        "source_metadata": metadata,
                    }
                )
            continue

        base_slug = _generation_slug(key[2])
        natural_key = (model_id, base_slug)
        occupied = natural_key in by_natural or natural_key in planned_natural
        slug = (
            _unique_slug(
                base_slug,
                f"drom-{hashlib.sha256(key[2].encode()).hexdigest()[:10]}",
                160,
            )
            if occupied
            else base_slug
        )
        while (model_id, slug) in by_natural or (model_id, slug) in planned_natural:
            slug = _unique_slug(
                base_slug,
                f"drom-{hashlib.sha256(f'{key[2]}:{slug}'.encode()).hexdigest()[:12]}",
                160,
            )
        planned_natural.add((model_id, slug))
        row_id = uuid4()
        result[key] = row_id
        years = _generation_years(item["name"])
        pending.append(
            {
                "id": row_id,
                "model_id": model_id,
                "slug": slug,
                "name": item["name"],
                "year_from": years[0],
                "year_to": years[1],
                "external_id": external_id,
                "source_name": SOURCE_NAME,
                "source_metadata": metadata,
                "manual_override": False,
            }
        )
        counts["generations_created"] += 1

    if not dry_run:
        for batch in _chunks(updates):
            db.bulk_update_mappings(CatalogGeneration, batch)
        counts["generations_updated"] += len(updates)
        if pending:
            counts["generations_inserted"] += _insert_ignore(
                db, CatalogGeneration, pending
            )
            inserted = _select_in(
                db,
                CatalogGeneration,
                CatalogGeneration.external_id,
                [row["external_id"] for row in pending],
            )
            by_external.update({row.external_id: row for row in inserted})
            for key, external_id in external_ids.items():
                if external_id in by_external:
                    result[key] = by_external[external_id].id
                elif key not in result:
                    raise DromInputError(
                        f"Drom generation insert did not resolve {key[2]}"
                    )
    return result


def _plan_body_variants(
    db: Session,
    generations: dict[tuple[str, str, str], dict],
    generation_ids: dict[tuple[str, str, str], Any],
    *,
    dry_run: bool,
    counts: dict[str, int],
) -> None:
    candidates = []
    for key, item in generations.items():
        category, status = _body_category(item["name"])
        if status != "recognized":
            continue
        candidates.append((key, category, generation_ids[key]))
    if not candidates:
        return

    generation_id_values = list({item[2] for item in candidates})
    existing = db.scalars(
        select(CatalogBodyVariant).where(
            CatalogBodyVariant.generation_id.in_(generation_id_values)
        )
    ).all()
    by_natural = {(row.generation_id, row.slug): row for row in existing}
    by_external = {row.external_id: row for row in existing if row.external_id}
    pending = []
    for key, category, generation_id in candidates:
        base_slug = category
        existing_variant = by_natural.get((generation_id, base_slug))
        body_name = BODY_TYPES[category]["name"]
        if existing_variant is not None:
            if _normalize_text(existing_variant.name) == _normalize_text(body_name):
                counts["body_variants_reused"] += 1
                continue
            base_slug = f"drom-{category}"
            existing_variant = by_natural.get((generation_id, base_slug))
            if existing_variant is not None:
                counts["body_variants_reused"] += 1
                continue

        external_id = _stable_external(
            "body-variant", f"{key[0]}/{key[1]}/{key[2]}/{category}"
        )
        matching_external = by_external.get(external_id)
        if matching_external is not None:
            if (
                matching_external.generation_id != generation_id
                or matching_external.source_name != SOURCE_NAME
            ):
                raise DromInputError(
                    f"Drom body variant identity collision for {key[2]}"
                )
            counts["body_variants_reused"] += 1
            continue
        used_slugs = {
            row.slug for row in existing if row.generation_id == generation_id
        }
        slug = base_slug
        if slug in used_slugs:
            slug = _unique_slug(
                base_slug,
                f"drom-{hashlib.sha256(key[2].encode()).hexdigest()[:8]}",
                120,
            )
        variant_id = uuid4()
        pending.append(
            {
                "id": variant_id,
                "generation_id": generation_id,
                "slug": slug,
                "name": body_name,
                "external_id": external_id,
                "source_name": SOURCE_NAME,
                "source_metadata": {
                    "name": SOURCE_NAME,
                    "generation_url": key[2],
                    "generation_label": generations[key]["name"],
                    "normalized_body_type": category,
                },
                "manual_override": False,
            }
        )
        counts["body_variants_created"] += 1

    if pending and not dry_run:
        counts["body_variants_inserted"] += _insert_ignore(
            db, CatalogBodyVariant, pending
        )


def _number(raw: str, *, integer: bool) -> int | float | None:
    if not raw.strip():
        return None
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    if integer:
        if value != value.to_integral_value():
            return None
        return int(value)
    result = float(value)
    return result if math.isfinite(result) else None


def _modification_name(row: dict[str, str]) -> str:
    trim = row["trim"]
    if trim.strip():
        return trim[:180]
    return f"Без названия Drom {row['source_id'].strip()}"[:180]


def _modification_slug(source_id: str) -> str:
    safe = _slug_piece(source_id)
    base = f"drom-{safe}"
    if len(base) <= 140:
        return base
    return f"drom-{hashlib.sha256(source_id.encode()).hexdigest()[:48]}"


def _stored_modification_source_url(row: CatalogModification) -> str | None:
    metadata = row.source_metadata
    value = metadata.get("source_url") if isinstance(metadata, dict) else None
    if not isinstance(value, str):
        return None
    try:
        return _valid_drom_url(value, "source_url", 0)
    except DromInputError:
        return None


def _plan_modifications(
    db: Session,
    records: list[_Record],
    generation_ids: dict[tuple[str, str, str], Any],
    *,
    dry_run: bool,
    counts: dict[str, int],
) -> None:
    external_ids = list(
        dict.fromkeys(
            external_id
            for record in records
            for external_id in (
                _modification_external_id(record.raw["source_url"]),
                f"drom:{record.raw['source_id'].strip()}",
            )
        )
    )
    existing_rows = _select_in(
        db, CatalogModification, CatalogModification.external_id, external_ids
    )
    by_external = {row.external_id: row for row in existing_rows}
    generation_ids_set = set(generation_ids.values())
    natural_rows = (
        db.scalars(
            select(CatalogModification).where(
                CatalogModification.generation_id.in_(generation_ids_set)
            )
        ).all()
        if generation_ids_set
        else []
    )
    by_natural = {(row.generation_id, row.slug): row for row in natural_rows}
    pending = []
    updates = []
    planned_natural: set[tuple[Any, str]] = set()

    for record in records:
        raw = record.raw
        source_id = raw["source_id"].strip()
        source_url = raw["source_url"]
        external_id = _modification_external_id(source_url)
        legacy = by_external.get(f"drom:{source_id}")
        current = by_external.get(external_id)
        migrate_legacy = False

        if (
            current is not None
            and _stored_modification_source_url(current) != source_url
        ):
            raise DromInputError(
                f"Drom modification identity collision for source_url {source_url}"
            )
        if legacy is not None:
            legacy_matches_url = _stored_modification_source_url(legacy) == source_url
            if current is not None and legacy is not current and legacy_matches_url:
                raise DromInputError(
                    f"both legacy and URL-based Drom modifications exist for source_url {source_url}"
                )
            if current is None and legacy_matches_url:
                current = legacy
                migrate_legacy = True

        generation_id = generation_ids[record.generation_key]
        name = _modification_name(raw)
        if current is not None:
            if current.generation_id != generation_id:
                raise DromInputError(
                    f"source_url {source_url} changed generation parent"
                )
            if current.source_name != SOURCE_NAME:
                raise DromInputError(
                    f"Drom modification identity collision for source_url {source_url}"
                )
            counts["modifications_reused"] += 1
            update = {"id": current.id}
            if migrate_legacy:
                update["external_id"] = external_id
            if not current.manual_override and (
                current.name != name or current.source_metadata != raw
            ):
                update.update(
                    {
                        "name": name,
                        "source_name": SOURCE_NAME,
                        "source_metadata": raw,
                    }
                )
            if len(update) > 1:
                updates.append(update)
            continue

        base_slug = _modification_slug(source_id)
        natural_key = (generation_id, base_slug)
        slug = base_slug
        if natural_key in by_natural or natural_key in planned_natural:
            slug = _unique_slug(
                base_slug,
                hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:10],
                140,
            )
        while (generation_id, slug) in by_natural or (
            generation_id,
            slug,
        ) in planned_natural:
            slug = _unique_slug(
                base_slug,
                hashlib.sha256(f"{source_url}:{slug}".encode()).hexdigest()[:12],
                140,
            )
        planned_natural.add((generation_id, slug))
        pending.append(
            {
                "id": uuid4(),
                "generation_id": generation_id,
                "slug": slug,
                "name": name,
                "external_id": external_id,
                "source_name": SOURCE_NAME,
                "source_metadata": raw,
                "manual_override": False,
            }
        )
        counts["modifications_created"] += 1

    if not dry_run:
        for batch in _chunks(updates):
            db.bulk_update_mappings(CatalogModification, batch)
        counts["modifications_updated"] += len(updates)
        if pending:
            counts["modifications_inserted"] += _insert_ignore(
                db, CatalogModification, pending
            )


def import_drom_csv(db: Session, path: Path, *, dry_run: bool = True) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise DromInputError(f"CSV file not found: {path}")

    records, makes, models, generations, checksum, quality = _load_batch(path)
    categories = sorted(
        {
            category
            for generation in generations.values()
            for category, status in [_body_category(generation["name"])]
            if status == "recognized" and category is not None
        }
    )
    counts: dict[str, int] = defaultdict(int)
    existing_import = db.scalar(
        select(CatalogImport).where(
            CatalogImport.source_name == SOURCE_NAME, CatalogImport.checksum == checksum
        )
    )

    try:
        body_type_ids = _get_or_create_body_types(
            db, categories, dry_run=dry_run, counts=counts
        )
        make_ids = _plan_makes(db, makes, dry_run=dry_run, counts=counts)
        model_ids = _plan_models(
            db, models, makes, make_ids, dry_run=dry_run, counts=counts
        )
        generation_ids = _plan_generations(
            db, generations, model_ids, body_type_ids, dry_run=dry_run, counts=counts
        )
        _plan_body_variants(
            db, generations, generation_ids, dry_run=dry_run, counts=counts
        )
        _plan_modifications(db, records, generation_ids, dry_run=dry_run, counts=counts)

        result = {
            "status": "dry_run" if dry_run else "imported",
            "source": SOURCE_NAME,
            "checksum_sha256": checksum,
            "source_file": path.name,
            "permission_provenance": "owner_confirmed_written_permission",
            "source_counts": {
                "rows": len(records),
                "makes": len(makes),
                "models": len(models),
                "generations": len(generations),
                "body_type_categories": len(categories),
            },
            "crosswalk": {
                "makes": {
                    "matched": counts["makes_matched"],
                    "new": counts["makes_created"],
                },
                "models": {
                    "matched": counts["models_matched"],
                    "drom_existing": counts["models_drom_existing"],
                    "ambiguous": counts["models_ambiguous"],
                    "unmatched": counts["models_unmatched"],
                    "new": counts["models_created"],
                },
            },
            "exact_match_rules": {
                "unique": {
                    "slug": counts["models_matched_by_slug"],
                    "make_prefixed_slug": counts[
                        "models_matched_by_make_prefixed_slug"
                    ],
                    "normalized_name": counts["models_matched_by_normalized_name"],
                    "normalized_alias": counts["models_matched_by_normalized_alias"],
                    "multi_rule_match": counts["models_multi_rule_match"],
                },
                "ambiguous": {
                    "slug": counts["models_ambiguous_with_slug"],
                    "make_prefixed_slug": counts[
                        "models_ambiguous_with_make_prefixed_slug"
                    ],
                    "normalized_name": counts["models_ambiguous_with_normalized_name"],
                    "normalized_alias": counts[
                        "models_ambiguous_with_normalized_alias"
                    ],
                },
            },
            "actions": dict(counts),
            "data_quality": quality,
            "catalog_import_exists": existing_import is not None,
        }

        if dry_run:
            return result

        if existing_import is None:
            db.add(
                CatalogImport(
                    source_name=SOURCE_NAME,
                    schema_version=1,
                    checksum=checksum,
                    counts={
                        "rows": len(records),
                        "makes": len(makes),
                        "models": len(models),
                        "generations": len(generations),
                        "body_types": len(categories),
                        "body_variants": counts["body_variants_created"],
                        "modifications": len(records),
                        "rows_by_make": quality["source_rows_by_make"],
                    },
                    source_metadata={
                        "source": "drom.ru",
                        "source_file": path.name,
                        "source_row_count": len(records),
                        "csv_sha256": checksum,
                        "source_counts": {
                            "makes": len(makes),
                            "models": len(models),
                            "generations": len(generations),
                            "body_types": len(categories),
                            "body_variants": counts["body_variants_created"],
                            "modifications": len(records),
                            "rows_by_make": quality["source_rows_by_make"],
                        },
                        "permission_provenance": {
                            "status": "owner_confirmed_written_permission",
                            "statement": "Owner confirmed Drom supplies these files under written permission.",
                        },
                        "data_quality": quality,
                    },
                )
            )
        db.commit()
        return result
    except Exception:
        if not dry_run:
            db.rollback()
        raise
