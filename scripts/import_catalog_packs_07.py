#!/usr/bin/env python3
"""Validate and import licensed catalog pack 07.5, 07.25 and 07.26.

Dry-run is the default. Only make/model names enter the public catalog;
specifications, variants and source review statuses remain in CatalogImport.
Archive SQL and README files are never executed or interpreted as commands.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import CatalogImport, CatalogMake, CatalogModel


SOURCE_NAME = "Autorinok catalog packs 07.5, 07.25 and 07.26"
OWNER_CONFIRMATION_DATE = "2026-10-22"
PACKS = {
    "07.5": {"archive": "autorinok_pack_07_part5.zip", "source_category": "boat_jetski", "category_code": "watercraft"},
    "07.25": {"archive": "autorinok_pack_07_part25.zip", "source_category": "motorcycle_scooter", "category_code": "motorcycles"},
    "07.26": {"archive": "autorinok_pack_07_part26.zip", "source_category": "boat_motorboat", "category_code": "watercraft"},
}
CSV_FILES = {
    "models": "01_models_staging.csv",
    "specs": "02_verified_specs.csv",
    "variants": "03_variants.csv",
    "sources_rights": "04_sources_rights.csv",
    "quality_checks": "06_quality_checks.csv",
    "checked_files": "07_checked_files.csv",
}


def _member(archive: zipfile.ZipFile, basename: str) -> str:
    matches = [name for name in archive.namelist() if Path(name).name == basename]
    if len(matches) != 1:
        raise ValueError(f"Expected one {basename} in {Path(archive.filename).name}; found {len(matches)}")
    return matches[0]


def _csv_rows(archive: zipfile.ZipFile, basename: str) -> list[dict[str, str]]:
    raw = archive.read(_member(archive, basename))
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def _verify_checksums(archive: zipfile.ZipFile, manifest: dict) -> dict[str, str]:
    expected_files = manifest.get("files") or {}
    if not isinstance(expected_files, dict):
        raise ValueError(f"Manifest file checksums are malformed: {Path(archive.filename).name}")
    verified: dict[str, str] = {}
    for filename, expected in expected_files.items():
        member = _member(archive, Path(filename).name)
        actual = hashlib.sha256(archive.read(member)).hexdigest()
        if actual.lower() != str(expected).lower():
            raise ValueError(f"Internal SHA-256 mismatch for {Path(archive.filename).name}:{filename}")
        verified[filename] = actual

    sums_members = [name for name in archive.namelist() if Path(name).name == "SHA256SUMS.txt"]
    if len(sums_members) > 1:
        raise ValueError(f"Duplicate SHA256SUMS.txt in {Path(archive.filename).name}")
    if sums_members:
        sums_text = archive.read(sums_members[0]).decode("utf-8-sig")
        for line in sums_text.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                raise ValueError(f"Malformed SHA256SUMS.txt line in {Path(archive.filename).name}")
            expected, filename = parts[0], parts[1].lstrip("*")
            member = _member(archive, Path(filename).name)
            actual = hashlib.sha256(archive.read(member)).hexdigest()
            if actual.lower() != expected.lower():
                raise ValueError(f"SHA256SUMS mismatch for {Path(archive.filename).name}:{filename}")
            verified[filename] = actual
    if not verified:
        raise ValueError(f"No verifiable internal file checksums: {Path(archive.filename).name}")
    return verified


def load_archives(paths: dict[str, Path]) -> dict:
    bundles: list[dict] = []
    seen_keys: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for pack_code, expected in PACKS.items():
        path = paths[pack_code]
        if path.name != expected["archive"]:
            raise ValueError(f"Expected {expected['archive']}, received {path.name}")
        raw_archive = path.read_bytes()
        archive_sha256 = hashlib.sha256(raw_archive).hexdigest()
        with zipfile.ZipFile(io.BytesIO(raw_archive)) as archive:
            archive.filename = str(path)
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise ValueError(f"Corrupt zip member in {path.name}: {Path(corrupt_member).name}")
            manifest = json.loads(archive.read(_member(archive, "09_manifest.json")).decode("utf-8-sig"))
            if manifest.get("pack") != pack_code:
                raise ValueError(f"Manifest pack mismatch in {path.name}")
            verified_files = _verify_checksums(archive, manifest)
            records = {key: _csv_rows(archive, filename) for key, filename in CSV_FILES.items()}

        models = records["models"]
        if not models:
            raise ValueError(f"No model rows in {path.name}")
        model_count = manifest.get("models", manifest.get("counts", {}).get("new_models"))
        specs_count = manifest.get("numeric_specs", manifest.get("counts", {}).get("new_specs"))
        variants_count = manifest.get("variants", manifest.get("counts", {}).get("new_variants"))
        if model_count != len(models) or specs_count != len(records["specs"]) or variants_count != len(records["variants"]):
            raise ValueError(f"CSV counts do not match manifest in {path.name}")

        keys_in_pack: set[str] = set()
        for row in models:
            brand, model, model_key = (row.get(field, "").strip() for field in ("brand", "model", "model_key"))
            if not brand or not model or not model_key:
                raise ValueError(f"Missing brand/model/model_key in {path.name}")
            if len(brand) > 180 or len(model) > 180:
                raise ValueError(f"Brand/model label exceeds catalog limits in {path.name}")
            if row.get("category_id") != expected["source_category"]:
                raise ValueError(f"Unexpected category {row.get('category_id')} in {path.name}")
            if model_key in keys_in_pack or model_key in seen_keys:
                raise ValueError(f"Duplicate model_key across supplied archives: {model_key}")
            keys_in_pack.add(model_key)
            seen_keys.add(model_key)
            identity = (_normalize(brand), _normalize(model))
            if identity in seen_pairs:
                raise ValueError(f"Duplicate brand/model pair across supplied archives: {brand} / {model}")
            seen_pairs.add(identity)

        bundles.append({
            "pack": pack_code,
            "path": path,
            "archive_sha256": archive_sha256,
            "manifest": manifest,
            "verified_files": verified_files,
            "category_code": expected["category_code"],
            **records,
        })

    combined = "\n".join(f"{bundle['pack']}:{bundle['archive_sha256']}" for bundle in bundles).encode()
    return {"bundles": bundles, "checksum": hashlib.sha256(combined).hexdigest()}


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if character.isalnum())


def _slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def _make_external_id(brand: str) -> str:
    return f"autorinok:make:{_normalize(brand)}"


def _model_external_id(pack_code: str, model_key: str) -> str:
    value = f"autorinok:{pack_code}:model:{model_key}"
    if len(value) > 100:
        raise ValueError(f"Source model ID exceeds catalog limit: {model_key}")
    return value


def _record_metadata(bundle: dict, row: dict[str, str]) -> dict:
    return {
        "category_codes": [bundle["category_code"]],
        f"catalog_pack_{bundle['pack'].replace('.', '_')}": {
            "archive_sha256": bundle["archive_sha256"],
            "record": row,
            "publication_scope": "make_and_model_names_only_at_user_request",
        },
    }


def _updated_make_metadata(make: CatalogMake, categories: dict[str, dict]) -> dict:
    metadata = json.loads(json.dumps(make.source_metadata or {}))
    previous_codes = metadata.get("category_codes", [])
    if not isinstance(previous_codes, list) or any(not isinstance(code, str) for code in previous_codes):
        raise ValueError(f"Invalid category_codes metadata for existing make {make.name}")
    codes = set(previous_codes)
    source_rows = metadata.get("catalog_pack_sources", {})
    if not isinstance(source_rows, dict):
        raise ValueError(f"Invalid catalog_pack_sources metadata for existing make {make.name}")
    for pack_code, item in categories.items():
        codes.add(item["category_code"])
        source_rows[pack_code] = {
            "archive_sha256": item["archive_sha256"],
            "category_code": item["category_code"],
            "model_count": item["model_count"],
        }
    metadata["category_codes"] = sorted(codes)
    metadata["catalog_pack_sources"] = source_rows
    return metadata


def build_plan(db, data: dict) -> dict:
    receipt = db.scalar(select(CatalogImport).where(CatalogImport.checksum == data["checksum"]).limit(1))
    if receipt is not None:
        return {"status": "unchanged", "counts": receipt.counts, "receipt": receipt}

    makes = list(db.scalars(select(CatalogMake)))
    models = list(db.scalars(select(CatalogModel)))
    makes_by_external = {make.external_id: make for make in makes if make.external_id}
    make_candidates: dict[str, set[CatalogMake]] = defaultdict(set)
    for make in makes:
        for label in (make.name, make.slug, *(make.aliases or [])):
            normalized = _normalize(label)
            if normalized:
                make_candidates[normalized].add(make)

    model_by_external = {model.external_id: model for model in models if model.external_id}
    model_labels_by_make: dict[str, dict[str, CatalogModel]] = defaultdict(dict)
    for model in models:
        for label in (model.name, model.slug, *(model.aliases or [])):
            normalized = _normalize(label)
            if normalized:
                model_labels_by_make[str(model.make_id)][normalized] = model

    brand_groups: dict[str, dict] = {}
    for bundle in data["bundles"]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in bundle["models"]:
            grouped[_normalize(row["brand"])].append(row)
        for key, rows in grouped.items():
            if not key:
                raise ValueError(f"Brand normalizes to an empty identity in pack {bundle['pack']}")
            group = brand_groups.setdefault(key, {"name": rows[0]["brand"], "categories": {}, "rows": []})
            if group["name"].casefold() != rows[0]["brand"].casefold():
                raise ValueError(f"Brand labels normalize to the same identity but differ: {group['name']} / {rows[0]['brand']}")
            group["categories"][bundle["pack"]] = {
                "category_code": bundle["category_code"],
                "archive_sha256": bundle["archive_sha256"],
                "model_count": len(rows),
            }
            group["rows"].extend((bundle, row) for row in rows)

    make_plans: dict[str, dict] = {}
    used_make_slugs = {make.slug for make in makes}
    for key, group in brand_groups.items():
        name = group["name"]
        external_id = _make_external_id(name)
        make = makes_by_external.get(external_id)
        if make is not None and _normalize(make.name) != key:
            raise ValueError(f"Stable make ID collision for {name}")
        if make is None:
            candidates = make_candidates.get(key, set())
            if len(candidates) > 1:
                raise ValueError(f"Ambiguous existing make match for {name}")
            make = next(iter(candidates)) if candidates else None
        new = make is None
        if new:
            slug = _slug(name) or f"make-{hashlib.sha256(key.encode()).hexdigest()[:8]}"
            if slug in used_make_slugs:
                slug = f"autor-07-{slug[:110]}-{hashlib.sha256(key.encode()).hexdigest()[:8]}"
            if len(slug) > 140 or slug in used_make_slugs:
                raise ValueError(f"Could not allocate a unique make slug for {name}")
            used_make_slugs.add(slug)
            make_id = uuid5(NAMESPACE_URL, external_id)
            metadata = {"category_codes": sorted({item["category_code"] for item in group["categories"].values()})}
            for pack_code, item in group["categories"].items():
                metadata.setdefault("catalog_pack_sources", {})[pack_code] = {
                    "archive_sha256": item["archive_sha256"],
                    "category_code": item["category_code"],
                    "model_count": item["model_count"],
                }
            source_name = SOURCE_NAME
        else:
            make_id = make.id
            metadata = _updated_make_metadata(make, group["categories"])
            source_name = make.source_name or SOURCE_NAME
        make_plans[key] = {
            "name": name, "external_id": external_id, "entity": make, "new": new,
            "id": make_id, "slug": slug if new else make.slug, "metadata": metadata,
            "source_name": source_name, "categories": group["categories"],
        }

    model_plans: list[dict] = []
    used_model_slugs: dict[str, set[str]] = defaultdict(set)
    for model in models:
        used_model_slugs[str(model.make_id)].add(model.slug)
    seen_external_ids: set[str] = set()
    for bundle in data["bundles"]:
        for row in bundle["models"]:
            make_key = _normalize(row["brand"])
            make_plan = make_plans[make_key]
            external_id = _model_external_id(bundle["pack"], row["model_key"])
            if external_id in seen_external_ids:
                raise ValueError(f"Duplicate stable model ID {external_id}")
            seen_external_ids.add(external_id)
            model = model_by_external.get(external_id)
            if model is not None:
                if model.make_id != make_plan["id"]:
                    raise ValueError(f"Stable model ID belongs to another make: {row['brand']} / {row['model']}")
                metadata = json.loads(json.dumps(model.source_metadata or {}))
                previous_codes = metadata.get("category_codes", [])
                if not isinstance(previous_codes, list):
                    raise ValueError(f"Invalid category_codes metadata for {row['brand']} / {row['model']}")
                metadata["category_codes"] = sorted(set(previous_codes) | {bundle["category_code"]})
                metadata.update(_record_metadata(bundle, row))
                metadata["category_codes"] = sorted(set(previous_codes) | {bundle["category_code"]})
                new = False
                slug = model.slug
            else:
                if make_plan["entity"] is not None:
                    same_name = model_labels_by_make[str(make_plan["id"])].get(_normalize(row["model"]))
                    if same_name is not None:
                        raise ValueError(f"Same-name model already exists; refusing duplicate: {row['brand']} / {row['model']}")
                new = True
                model_id_digest = hashlib.sha256(external_id.encode()).hexdigest()[:8]
                slug = _slug(row["model"]) or f"model-{model_id_digest}"
                used = used_model_slugs[str(make_plan["id"])]
                if slug in used:
                    slug = f"{slug[:145]}-{model_id_digest}"
                if len(slug) > 160 or slug in used:
                    raise ValueError(f"Could not allocate a unique model slug for {row['brand']} / {row['model']}")
                used.add(slug)
                metadata = _record_metadata(bundle, row)
            model_plans.append({
                "bundle": bundle, "row": row, "make_key": make_key, "external_id": external_id,
                "entity": model, "new": new, "id": uuid5(NAMESPACE_URL, external_id),
                "slug": slug, "metadata": metadata,
                "source_name": (model.source_name or f"Autorinok catalog pack {bundle['pack']}") if model is not None
                else f"Autorinok catalog pack {bundle['pack']}",
            })

    make_snapshots = [
        {"id": str(plan["entity"].id), "source_name": plan["entity"].source_name,
         "source_metadata": plan["entity"].source_metadata}
        for plan in make_plans.values()
        if plan["entity"] is not None and (
            plan["entity"].source_name != plan["source_name"] or plan["entity"].source_metadata != plan["metadata"]
        )
    ]
    model_snapshots = [
        {"id": str(item["entity"].id), "source_name": item["entity"].source_name,
         "source_metadata": item["entity"].source_metadata}
        for item in model_plans
        if item["entity"] is not None and (
            item["entity"].source_name != item["source_name"]
            or item["entity"].source_metadata != item["metadata"]
        )
    ]
    counts = {
        "makes_created": sum(plan["new"] for plan in make_plans.values()),
        "makes_reused": sum(not plan["new"] for plan in make_plans.values()),
        "make_metadata_updated": len(make_snapshots),
        "models_created": sum(plan["new"] for plan in model_plans),
        "models_reused": sum(not plan["new"] for plan in model_plans),
        "public_model_names": len(model_plans),
        "public_generations": 0,
        "public_modifications": 0,
        "source_spec_rows_staged": sum(len(bundle["specs"]) for bundle in data["bundles"]),
        "source_variant_rows_staged": sum(len(bundle["variants"]) for bundle in data["bundles"]),
        "packs": {bundle["pack"]: len(bundle["models"]) for bundle in data["bundles"]},
    }
    return {
        "status": "ready",
        "counts": counts,
        "make_plans": make_plans,
        "model_plans": model_plans,
        "make_snapshots": make_snapshots,
        "model_snapshots": model_snapshots,
    }


def _catalog_import_metadata(data: dict, plan: dict, created_make_ids: list[str], created_model_ids: list[str]) -> dict:
    return {
        "import_kind": "licensed_catalog_pack_names_only",
        "rights_assertion": {
            "status": "user_confirmed_paid_license_from_rightsholder",
            "confirmed_on": OWNER_CONFIRMATION_DATE,
        },
        "publication": {
            "public_fields": ["make.name", "model.name"],
            "not_written_to_public_catalog": ["specifications", "variants", "model_year_reference"],
            "source_review_statuses_preserved": True,
        },
        "archives": [
            {
                "name": bundle["path"].name,
                "pack": bundle["pack"],
                "sha256": bundle["archive_sha256"],
                "manifest": bundle["manifest"],
                "verified_file_sha256": bundle["verified_files"],
                "models": bundle["models"],
                "specs": bundle["specs"],
                "variants": bundle["variants"],
                "sources_rights": bundle["sources_rights"],
                "quality_checks": bundle["quality_checks"],
                "checked_files": bundle["checked_files"],
            }
            for bundle in data["bundles"]
        ],
        "rollback": {
            "created_make_ids": created_make_ids,
            "created_model_ids": created_model_ids,
            "make_metadata_before": plan["make_snapshots"],
            "model_metadata_before": plan["model_snapshots"],
            "procedure": "Restore make source_name/source_metadata snapshots, delete rows by created IDs only if unreferenced, then remove this CatalogImport receipt.",
        },
    }


def import_packs(data: dict, *, apply: bool = False) -> dict:
    with SessionLocal() as db:
        try:
            db.execute(text("SELECT pg_advisory_xact_lock(74101501)"))
            plan = build_plan(db, data)
            if plan["status"] == "unchanged":
                db.rollback()
                return {"status": "unchanged", "checksum": data["checksum"], "counts": plan["counts"]}
            if not apply:
                db.rollback()
                return {"status": "dry_run", "checksum": data["checksum"], "counts": plan["counts"]}

            created_make_ids: list[str] = []
            make_by_key: dict[str, CatalogMake] = {}
            for key, item in plan["make_plans"].items():
                make = item["entity"]
                if make is None:
                    make = CatalogMake(
                        id=item["id"], slug=item["slug"], name=item["name"], aliases=[],
                        external_id=item["external_id"], source_name=item["source_name"],
                        source_metadata=item["metadata"], manual_override=False,
                    )
                    db.add(make)
                    created_make_ids.append(str(make.id))
                else:
                    make.source_name = item["source_name"]
                    make.source_metadata = item["metadata"]
                make_by_key[key] = make
            db.flush()

            created_model_ids: list[str] = []
            for item in plan["model_plans"]:
                model = item["entity"]
                if model is None:
                    model = CatalogModel(
                        id=item["id"], make_id=make_by_key[item["make_key"]].id,
                        slug=item["slug"], name=item["row"]["model"].strip(), aliases=[],
                        external_id=item["external_id"],
                        source_name=f"Autorinok catalog pack {item['bundle']['pack']}",
                        source_metadata=item["metadata"], manual_override=False,
                    )
                    db.add(model)
                    created_model_ids.append(str(model.id))
                else:
                    model.source_name = item["source_name"]
                    model.source_metadata = item["metadata"]

            counts = dict(plan["counts"])
            db.add(CatalogImport(
                source_name=SOURCE_NAME,
                schema_version=1,
                checksum=data["checksum"],
                counts=counts,
                source_metadata=_catalog_import_metadata(data, plan, created_make_ids, created_model_ids),
            ))
            db.commit()
            return {"status": "imported", "checksum": data["checksum"], "counts": counts}
        except Exception:
            db.rollback()
            raise


def _summary(data: dict) -> dict:
    return {
        "status": "archives_validated",
        "checksum": data["checksum"],
        "archives": [
            {"name": bundle["path"].name, "sha256": bundle["archive_sha256"], "pack": bundle["pack"],
             "models": len(bundle["models"]), "specs": len(bundle["specs"]), "variants": len(bundle["variants"])}
            for bundle in data["bundles"]
        ],
        "totals": {
            "models": sum(len(bundle["models"]) for bundle in data["bundles"]),
            "specs": sum(len(bundle["specs"]) for bundle in data["bundles"]),
            "variants": sum(len(bundle["variants"]) for bundle in data["bundles"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for pack_code, expected in PACKS.items():
        parser.add_argument(f"--pack-{pack_code.replace('.', '-')}", required=True, type=Path, help=expected["archive"])
    parser.add_argument("--validate-only", action="store_true", help="validate archives and checksums without connecting to a database")
    parser.add_argument("--apply", action="store_true", help="write the names-only catalog import; dry-run is the default")
    parser.add_argument("--owner-rights-confirmed", action="store_true", help="record the user's direct license confirmation")
    parser.add_argument("--publish-model-names-only", action="store_true", help="confirm publication scope excludes specs and variants")
    args = parser.parse_args()
    if args.apply and not args.owner_rights_confirmed:
        parser.error("--apply requires --owner-rights-confirmed")
    if args.apply and not args.publish_model_names_only:
        parser.error("--apply requires --publish-model-names-only")
    paths = {pack: getattr(args, f"pack_{pack.replace('.', '_')}") for pack in PACKS}
    try:
        data = load_archives(paths)
        if args.validate_only:
            result = _summary(data)
        else:
            result = import_packs(data, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as error:
        print(f"catalog pack import failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
