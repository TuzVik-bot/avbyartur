"""Publish only approved make/model names from the 07.24–07.84 receipt.

Dry run is the default. The input archive is read as data only; specs, variants,
source URLs and rights/crosscheck flags stay in the private CatalogImport receipt.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text

EXPECTED_ARCHIVE_SHA256 = "ee89f0da38ef2f09ecf88e7817f4dc0e384db9650d392558a8944af9f1b49c44"
EXPECTED_RECEIPT_SHA256 = EXPECTED_ARCHIVE_SHA256
MODEL_CSV = "consolidated/01_models_staging.csv"
MANIFEST = "reports/manifest.json"
SOURCE_NAME = "Avtorinok catalog receipt 07.24-07.84 names"
CATEGORY_BY_ID = {
    "motorcycle": "motorcycles",
    "motorcycle_scooter": "motorcycles",
    "motorcycle_electric": "motorcycles",
    "scooter": "motorcycles",
    "scooter_electric": "motorcycles",
    "atv": "motorcycles",
    "atv_utv": "motorcycles",
    "atv_utility": "motorcycles",
    "atv_buggy": "motorcycles",
    "atv_utv_electric": "motorcycles",
    "atv_youth": "motorcycles",
    "atv_sport": "motorcycles",
    "atv_sxs": "motorcycles",
    "atv_electric": "motorcycles",
    "boat": "watercraft",
    "boat_motorboat": "watercraft",
    "motorboat": "watercraft",
}
MANUAL_CAR_ALLOWLIST = {
    (make, model)
    for make, model in (
        ("BYD Auto", "BYD Atto 3"),
        ("БелДжи", "Belgee X50"),
        ("БелДжи", "Belgee X70"),
        ("Geely Holding", "Geely Coolray"),
        ("Volkswagen", "Volkswagen Passat"),
        ("BMW", "BMW 3 Series"),
    )
}


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if char.isalnum())


MANUAL_CAR_ALLOWLIST = {(normalize(make), normalize(model)) for make, model in MANUAL_CAR_ALLOWLIST}


def legacy_car_evidence(model, make) -> str | None:
    metadata = model.source_metadata or {}
    source = metadata.get("name") or model.source_name
    if (
        source == "Drom"
        and model.source_name == "Drom"
        and isinstance(metadata.get("make_slug"), str)
        and isinstance(metadata.get("model_slug"), str)
        and bool(metadata.get("model_match_status"))
    ):
        return "drom_importer_model_lineage"
    if (
        source == "Wikidata"
        and metadata.get("brand_property") == "P1716"
        and metadata.get("model_class") == "Q3231690"
    ):
        return "wikidata_direct_brand_car_model"
    if (normalize(make.name), normalize(model.name)) in MANUAL_CAR_ALLOWLIST:
        return "exact_project_manual_car_allowlist"
    return None


def slug(value: str, limit: int) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return result[:limit].strip("-") or "catalog-item"


def load_models(path: str) -> tuple[str, list[dict[str, str]]]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("input archive SHA-256 differs from reviewed receipt")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if len(archive.infolist()) != 71 or sum(item.file_size for item in archive.infolist()) > 10_000_000:
            raise ValueError("unexpected ZIP member count or expansion size")
        for item in archive.infolist():
            member = PurePosixPath(item.filename)
            if member.is_absolute() or ".." in member.parts or "\\" in item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"unsafe ZIP member path: {item.filename!r}")
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC check failed")
        manifest = json.loads(archive.read(MANIFEST))
        if manifest.get("range") != "7.24–7.84" or manifest.get("consolidated_counts", {}).get("01_models_staging.csv") != 1099:
            raise ValueError("unexpected receipt manifest")
        rows = list(csv.DictReader(io.StringIO(archive.read(MODEL_CSV).decode("utf-8-sig"))))
    if len(rows) != 1099 or len({row.get("model_key") for row in rows}) != len(rows):
        raise ValueError("unexpected or duplicate staged model rows")
    for row in rows:
        if row.get("rights_status") != "needs_rights_clearance" or row.get("crosscheck_status") != "needs_crosscheck":
            raise ValueError("receipt review flags differ from the approved names-only staging set")
        if row.get("import_status") != "hold_for_rights_and_crosscheck":
            raise ValueError("receipt import status differs from the reviewed staging set")
        if row.get("category_id") not in CATEGORY_BY_ID:
            raise ValueError(f"unmapped category id: {row.get('category_id')!r}")
        if not row.get("brand", "").strip() or not row.get("model", "").strip():
            raise ValueError("empty make/model name")
        if len(row["brand"].strip()) > 180 or len(row["model"].strip()) > 180:
            raise ValueError("make/model name exceeds catalog limits")
        key_parts = row.get("model_key", "").split("|", 2)
        if len(key_parts) != 3 or key_parts[0] != row["category_id"] or not key_parts[1] or not key_parts[2]:
            raise ValueError(f"model_key does not match its category row: {row.get('model_key')!r}")
        row["category_code"] = CATEGORY_BY_ID[row["category_id"]]
    if Counter(row["category_code"] for row in rows) != {"motorcycles": 535, "watercraft": 564}:
        raise ValueError("receipt category counts differ from reviewed mapping")
    return digest, rows


def identity_values(row) -> set[str]:
    return {normalize(value) for value in [row.name, row.slug, *(row.aliases or [])] if value}


def _display_order(value: str) -> tuple[str, str]:
    value = value.strip()
    return value.casefold(), value


def group_source_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge spelling variants by category and normalized make/model identity."""
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (row["category_code"], normalize(row["brand"]), normalize(row["model"]))
        grouped[key].append(row)

    result: list[dict[str, str]] = []
    for key in sorted(grouped):
        group = grouped[key]
        ordered = sorted(
            group,
            key=lambda row: (
                *_display_order(row["brand"]),
                *_display_order(row["model"]),
                row["model_key"],
            ),
        )
        canonical = dict(ordered[0])
        brand_variants = sorted({row["brand"].strip() for row in group}, key=_display_order)
        model_variants = sorted({row["model"].strip() for row in group}, key=_display_order)
        canonical.update(
            brand_aliases=[value for value in brand_variants if value != canonical["brand"].strip()],
            model_aliases=[value for value in model_variants if value != canonical["model"].strip()],
            model_keys=sorted({row["model_key"] for row in group}),
            source_category_ids=sorted({row["category_id"] for row in group}),
            duplicate_source_rows=len(group) - 1,
        )
        result.append(canonical)
    return result


def run(path: str, *, apply: bool = False, phase: str = "all") -> dict:
    from app.db import SessionLocal
    from app.models import CatalogImport, CatalogMake, CatalogModel

    if phase not in {"all", "legacy-cars", "receipt-names"}:
        raise ValueError(f"unsupported promotion phase: {phase}")
    digest, source_rows = load_models(path)
    grouped_source_rows = group_source_rows(source_rows)
    rows_by_make: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        rows_by_make[normalize(row["brand"])].append(row)
    brand_names_by_make = {
        key: sorted({row["brand"].strip() for row in rows}, key=_display_order)
        for key, rows in rows_by_make.items()
    }
    stats: Counter[str] = Counter()
    category_counts = Counter(row["category_code"] for row in source_rows)
    row_decisions: list[dict[str, str]] = []

    with SessionLocal.begin() as db:
        db.execute(text("select pg_advisory_xact_lock(74101501)"))
        receipt = db.scalar(select(CatalogImport).where(CatalogImport.checksum == EXPECTED_RECEIPT_SHA256).limit(1))
        if receipt is None:
            raise RuntimeError("private CatalogImport receipt for this archive is absent")
        makes = list(db.scalars(select(CatalogMake)))
        models = list(db.scalars(select(CatalogModel)))
        make_by_id = {make.id: make for make in makes}
        legacy_candidates: dict[object, str] = {}
        legacy_make_ids: set[object] = set()
        legacy_counts: Counter[str] = Counter()
        legacy_holds_by_source: Counter[str] = Counter()
        unclassified_models = [model for model in models if not (model.source_metadata or {}).get("category_codes")]
        for model in unclassified_models:
            make = make_by_id.get(model.make_id)
            evidence = legacy_car_evidence(model, make) if make else None
            if evidence:
                legacy_candidates[model.id] = evidence
                legacy_make_ids.add(model.make_id)
                legacy_counts[evidence] += 1
            else:
                legacy_counts["unclassified_held"] += 1
                legacy_holds_by_source[model.source_name or "unknown"] += 1
        resolved_makes: dict[str, CatalogMake] = {}
        make_decisions: dict[str, str] = {}
        for make_key, make_rows in rows_by_make.items():
            brand_variants = brand_names_by_make[make_key]
            name = brand_variants[0]
            matches = [make for make in makes if make_key in identity_values(make)]
            if len(matches) > 1:
                make_decisions[make_key] = "ambiguous_make"
                stats["ambiguous_makes"] += 1
                continue
            if matches and matches[0].manual_override:
                make_decisions[make_key] = "manual_make_review"
                stats["manual_make_review"] += 1
                continue
            if matches:
                resolved_makes[make_key] = matches[0]
                make_decisions[make_key] = "existing"
                stats["makes_existing"] += 1
            else:
                make_slug = slug(name, 120)
                if any(make.slug == make_slug for make in makes) or any(existing.slug == make_slug for existing in resolved_makes.values()):
                    make_slug = f"{make_slug[:110]}-{hashlib.sha256(make_key.encode()).hexdigest()[:10]}"
                resolved_makes[make_key] = CatalogMake(
                    id=uuid5(NAMESPACE_URL, f"{digest}:make:{make_key}"),
                    slug=make_slug[:140], name=name, aliases=[], source_name=SOURCE_NAME,
                    source_metadata={}, manual_override=False,
                )
                make_decisions[make_key] = "new"
                stats["makes_new"] += 1
        for raw in grouped_source_rows:
            make_key = normalize(raw["brand"])
            make = resolved_makes.get(make_key)
            if make is None:
                row_decisions.append({"model_key": raw["model_key"], "model_keys": raw["model_keys"], "category_code": raw["category_code"], "decision": make_decisions[make_key]})
                stats[make_decisions[make_key]] += 1
                continue
            name_key = normalize(raw["model"])
            same_name = [model for model in models if model.make_id == make.id and name_key in identity_values(model)]
            exact = [model for model in same_name if raw["category_code"] in set((model.source_metadata or {}).get("category_codes", []))]
            if len(exact) > 1:
                decision = "ambiguous_model"
            elif exact and exact[0].manual_override:
                decision = "manual_model_review"
            elif exact:
                decision = "existing"
            elif any(not (model.source_metadata or {}).get("category_codes") for model in same_name):
                decision = "unclassified_existing_match"
            elif same_name:
                decision = "new_category_identity"
            else:
                decision = "new"
            stats[decision] += 1
            row_decisions.append({
                "model_key": raw["model_key"], "model_keys": raw["model_keys"],
                "category_code": raw["category_code"], "decision": decision,
            })
        held_decisions = {"ambiguous_model", "manual_model_review", "ambiguous_make", "manual_make_review", "unclassified_existing_match"}
        held = sum(1 for decision in row_decisions if decision["decision"] in held_decisions)
        result = {
            "status": ("dry_run_partial_ready" if held else "dry_run_ready") if not apply else ("applied_with_holds" if held else "applied"),
            "phase": phase,
            "archive_sha256": digest,
            "receipt_id": str(receipt.id),
            "source_rows": len(source_rows),
            "source_identity_groups": len(grouped_source_rows),
            "source_alias_duplicates": sum(row["duplicate_source_rows"] for row in grouped_source_rows),
            "category_counts": dict(sorted(category_counts.items())),
            "unique_category_counts": dict(sorted(Counter(row["category_code"] for row in grouped_source_rows).items())),
            "counts": dict(sorted(stats.items())),
            "legacy_category_backfill": {
                "unclassified_models_before": len(unclassified_models),
                "cars_candidates": sum(legacy_counts.values()) - legacy_counts["unclassified_held"],
                "cars_makes": len(legacy_make_ids),
                "held_unclassified": legacy_counts["unclassified_held"],
                "candidates_by_evidence": dict(sorted((key, count) for key, count in legacy_counts.items() if key != "unclassified_held")),
                "held_by_source": dict(sorted(legacy_holds_by_source.items())),
            },
            "held_rows": held,
            "row_decisions": row_decisions,
            "public_fields_changed": ["make/model names", "category_codes metadata"],
            "private_fields_unchanged": ["specs", "variants", "source URLs", "rights", "crosscheck status", "listings"],
        }
        if not apply:
            db.rollback()
            return result

        if phase == "legacy-cars":
            legacy_make_additions: dict[object, set[str]] = defaultdict(set)
            for model_id, evidence in legacy_candidates.items():
                model = next(row for row in models if row.id == model_id)
                metadata = dict(model.source_metadata or {})
                codes = set(metadata.get("category_codes", []))
                if codes and "cars" not in codes:
                    continue
                codes.add("cars")
                metadata["category_codes"] = sorted(codes)
                metadata["catalog_category_classification"] = {
                    "rule": evidence,
                    "approved_category_code": "cars",
                }
                model.source_metadata = metadata
                legacy_make_additions[model.make_id].add("cars")
            for make_id, categories in legacy_make_additions.items():
                make = make_by_id[make_id]
                metadata = dict(make.source_metadata or {})
                metadata["category_codes"] = sorted(set(metadata.get("category_codes", [])) | categories)
                make.source_metadata = metadata
            db.flush()
            return result

        decisions_by_key = {decision["model_key"]: decision["decision"] for decision in row_decisions}
        additions: dict[str, set[str]] = defaultdict(set)
        legacy_make_additions: dict[object, set[str]] = defaultdict(set)
        source_brand_aliases: dict[str, set[str]] = defaultdict(set)
        for raw in grouped_source_rows:
            decision = decisions_by_key[raw["model_key"]]
            if decision not in {"existing", "new", "new_category_identity"}:
                continue
            make_key = normalize(raw["brand"])
            additions[make_key].add(raw["category_code"])
            source_brand_aliases[make_key].update(brand_names_by_make[make_key])
            make = resolved_makes[make_key]
            if decision == "new" or decision == "new_category_identity":
                stem = slug(raw["model"], 120)
                candidate = f"{stem}-{hashlib.sha256(raw['model_key'].encode()).hexdigest()[:10]}"
                slug_value = candidate[:160]
                if any(model.make_id == make.id and model.slug == slug_value for model in models):
                    raise RuntimeError(f"generated model slug already exists: {raw['model_key']}")
                model = CatalogModel(
                    id=uuid5(NAMESPACE_URL, f"{digest}:model:{raw['model_key']}"),
                    make_id=make.id, slug=slug_value, name=raw["model"].strip(), aliases=list(raw["model_aliases"]),
                    source_name=SOURCE_NAME, source_metadata={}, manual_override=False,
                )
                db.add(model)
                models.append(model)
            elif decision == "existing":
                candidates = [model for model in models if model.make_id == make.id and normalize(raw["model"]) in identity_values(model)]
                candidates = [model for model in candidates if raw["category_code"] in set((model.source_metadata or {}).get("category_codes", []))]
                if len(candidates) != 1:
                    raise RuntimeError(f"identity changed during transaction: {raw['model_key']}")
                model = candidates[0]
            else:
                raise RuntimeError(f"unexpected non-publishable decision {decision}")
            aliases = list(model.aliases or [])
            for alias in [raw["model"].strip(), *raw["model_aliases"]]:
                if alias != model.name and alias not in aliases:
                    aliases.append(alias)
            if aliases != model.aliases:
                model.aliases = aliases
            metadata = dict(model.source_metadata or {})
            codes = set(metadata.get("category_codes", []))
            codes.add(raw["category_code"])
            metadata["category_codes"] = sorted(codes)
            metadata["catalog_name_publication"] = {
                "receipt_id": str(receipt.id), "archive_sha256": digest,
                "model_key": raw["model_key"], "model_keys": raw["model_keys"],
                "category_id": raw["category_id"], "category_ids": raw["source_category_ids"],
            }
            model.source_metadata = metadata
        if phase == "all":
            for model_id, evidence in legacy_candidates.items():
                model = next(row for row in models if row.id == model_id)
                metadata = dict(model.source_metadata or {})
                codes = set(metadata.get("category_codes", []))
                if codes and "cars" not in codes:
                    continue
                codes.add("cars")
                metadata["category_codes"] = sorted(codes)
                metadata["catalog_category_classification"] = {
                    "rule": evidence,
                    "approved_category_code": "cars",
                }
                model.source_metadata = metadata
                legacy_make_additions[model.make_id].add("cars")
        for make_key, categories in additions.items():
            make = resolved_makes[make_key]
            metadata = dict(make.source_metadata or {})
            metadata["category_codes"] = sorted(set(metadata.get("category_codes", [])) | categories)
            make.source_metadata = metadata
            aliases = list(make.aliases or [])
            for alias in sorted(source_brand_aliases[make_key], key=_display_order):
                if alias != make.name and alias not in aliases:
                    aliases.append(alias)
            if aliases != make.aliases:
                make.aliases = aliases
            if make not in makes:
                db.add(make)
        for make_id, categories in legacy_make_additions.items():
            make = make_by_id[make_id]
            metadata = dict(make.source_metadata or {})
            metadata["category_codes"] = sorted(set(metadata.get("category_codes", [])) | categories)
            make.source_metadata = metadata
        db.flush()
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--apply", action="store_true", help="commit the names-only promotion; default is rollback dry run")
    parser.add_argument("--phase", choices=("all", "legacy-cars", "receipt-names"), default="all")
    args = parser.parse_args()
    print(json.dumps(run(args.archive, apply=args.apply, phase=args.phase), ensure_ascii=False, sort_keys=True))
