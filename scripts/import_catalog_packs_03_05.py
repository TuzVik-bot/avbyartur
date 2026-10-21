"""Import catalog delta packs 03, 04 and 05 into the existing application DB.

All SQL/psql files in the supplied archives are treated as documents and never
executed. Dry-run is the default and rolls back. The packages are applied in one
database transaction with source provenance retained in JSONB metadata.
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
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import CatalogImport, CatalogMake, CatalogModel

SOURCE_NAMES = {"03": "Autorinok catalog pack 03", "04": "Autorinok catalog pack 04", "05": "Autorinok catalog pack 05"}
SECTION_TO_CATEGORY = {
    "truck": "trucks", "commercial": "trucks", "bus": "buses",
    "motorcycle": "motorcycles", "atv": "motorcycles", "snow": "motorcycles",
    "boat": "watercraft", "trailer": "trailers", "special": "special_equipment",
    "agro": "agricultural_equipment",
}
BRAND_FILES = {"03": "01_brands_add.csv", "04": "01_brands_add.csv", "05": "01_brands_add.csv"}
MODEL_FILES = {"03": "03_models_add.csv", "04": "03_models_add.csv", "05": "03_models_add.csv"}


def norm(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


def slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = decomposed.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def read_csv(archive: zipfile.ZipFile, basename: str) -> list[dict[str, str]]:
    matches = [name for name in archive.namelist() if name == basename or name.endswith("/" + basename)]
    if len(matches) != 1:
        raise ValueError(f"Expected one {basename} in {archive.filename}, found {len(matches)}")
    return list(csv.DictReader(io.StringIO(archive.read(matches[0]).decode("utf-8-sig"))))


def optional_csv(archive: zipfile.ZipFile, basename: str) -> list[dict[str, str]]:
    matches = [name for name in archive.namelist() if name == basename or name.endswith("/" + basename)]
    if not matches:
        return []
    if len(matches) != 1:
        raise ValueError(f"Expected at most one {basename} in {archive.filename}")
    return list(csv.DictReader(io.StringIO(archive.read(matches[0]).decode("utf-8-sig"))))


def load_package(package: str, path: str) -> dict:
    with zipfile.ZipFile(path) as archive:
        brands = read_csv(archive, BRAND_FILES[package])
        models = read_csv(archive, MODEL_FILES[package])
        model_metadata = read_csv(archive, "03_models_add_metadata.csv")
        variants = read_csv(archive, "06_variants_add.csv")
        specs = read_csv(archive, "07_specs_add.csv")
        categories = optional_csv(archive, "02_brand_categories_add.csv")
        matches = optional_csv(archive, "03_matches_existing.csv")
        observations = optional_csv(archive, "03_observations.csv")
        model_audit = optional_csv(archive, "09_model_source_audit.csv")
        spec_audit = optional_csv(archive, "09_spec_source_audit.csv")
        evidence_names = (
            "02_brand_categories_add.csv", "04_attributes_add.csv", "04_attribute_rules_add.csv", "08_source_register.csv",
            "03_matches_existing.csv", "03_observations.csv", "09_model_source_audit.csv",
            "09_spec_source_audit.csv", "07_existing_model_specs_review.csv",
            "06_variants_add.csv", "07_specs_add.csv",
        )
        evidence = {name: optional_csv(archive, name) for name in evidence_names}
        manifest_names = [name for name in archive.namelist() if name.lower().endswith(("manifest.json",))]
        if len(manifest_names) != 1:
            raise ValueError(f"Expected one manifest.json in package {package}")
        manifest = json.loads(archive.read(manifest_names[0]).decode("utf-8-sig"))

    model_ids = [row["model_id"] for row in models]
    assert len(model_ids) == len(set(model_ids)), f"duplicate model IDs in package {package}"
    metadata_by_id = {row["model_id"]: row for row in model_metadata}
    assert len(metadata_by_id) == len(model_metadata) and set(metadata_by_id) == set(model_ids), f"model metadata mismatch in package {package}"
    brand_ids = {row["brand_id"] for row in brands}
    assert len(brand_ids) == len(brands), f"duplicate brand IDs in package {package}"
    assert len({row["variant_id"] for row in variants}) == len(variants), f"duplicate variant IDs in package {package}"
    variant_by_id = {row["variant_id"]: row for row in variants}
    for row in specs:
        assert row["variant_id"] in variant_by_id, f"unknown variant in package {package}: {row['variant_id']}"
        assert row["model_id"] == variant_by_id[row["variant_id"]]["model_id"], f"variant/model mismatch in package {package}"
    for row in models:
        assert row["model_name"].strip() and len(row["model_name"]) <= 180
        assert not row.get("year_from") and not row.get("year_to") and not row.get("model_variant"), f"unexpected production fields: {row}"
    for row in categories:
        assert row["brand_id"]
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {
        "package": package, "path": path, "checksum": digest, "brands": brands, "models": models,
        "metadata_by_id": metadata_by_id, "variants": variants, "specs": specs,
        "brand_categories": categories, "matches": matches, "observations": observations,
        "model_audit": model_audit, "spec_audit": spec_audit, "evidence": evidence, "manifest": manifest,
    }


def set_metadata(row, metadata: dict) -> bool:
    if row.source_metadata == metadata:
        return False
    row.source_metadata = metadata
    return True


def preserve_evidence(package: dict, code_to_category: dict[str, str]) -> dict:
    evidence = {key: value for key, value in package["evidence"].items() if value}
    evidence["manifest"] = package["manifest"]
    source_category_ids = {
        row["category_id"] for row in package["models"]
    } | {
        row["category_id"] for row in package["brand_categories"]
    }
    evidence["category_mapping"] = {
        category_id: code_to_category.get(category_id) for category_id in sorted(source_category_ids)
    }
    return evidence


def run(paths: dict[str, str], apply: bool = False) -> dict:
    if set(paths) != {"03", "04", "05"}:
        raise ValueError("Supply exactly packages 03, 04 and 05")
    packages = [load_package(code, paths[code]) for code in ("03", "04", "05")]

    # The category taxonomy was introduced by package 02. Resolve every input
    # category against that archive instead of guessing from category names.
    pack02_path = Path(paths["03"]).with_name("autorinok_catalog_pack_02.zip")
    if not pack02_path.is_file():
        raise ValueError("The adjacent package 02 archive is required to validate category IDs")
    with zipfile.ZipFile(pack02_path) as archive:
        category_sections = read_csv(archive, "00_category_sections.csv")
    category_to_section = {row["category_id"]: row["section_id"] for row in category_sections}
    category_to_code = {category: SECTION_TO_CATEGORY[section] for category, section in category_to_section.items() if section in SECTION_TO_CATEGORY}
    for package in packages:
        for row in package["models"]:
            if row["category_id"] not in category_to_code:
                raise ValueError(f"Unmapped category {row['category_id']} in package {package['package']}")
        for row in package["brand_categories"]:
            if row["category_id"] not in category_to_code:
                raise ValueError(f"Unmapped brand category {row['category_id']} in package {package['package']}")

    totals: dict[str, dict] = {}
    with SessionLocal() as db:
        db.execute(text("select pg_advisory_xact_lock(74101501)"))

        # Fail closed if the required base import (package 02) is absent.
        existing_models = list(db.scalars(select(CatalogModel)))
        existing_ids = {model.external_id for model in existing_models}
        required_base_ids = {"seed-f31763f48966b6", "seed-590ce8a26752c7"}
        if not required_base_ids.issubset(existing_ids):
            raise ValueError("Required catalog package 02 records are not present")

        current_model_ids = set(existing_ids)
        delta_model_ids = {row["model_id"] for package in packages for row in package["models"]}
        resolvable_model_ids = current_model_ids | delta_model_ids
        for package in packages:
            for variant in package["variants"]:
                if variant["model_id"] not in resolvable_model_ids:
                    raise ValueError(f"Unknown variant model {variant['model_id']} in package {package['package']}")
            for row in package["matches"]:
                if row["model_id"] not in current_model_ids:
                    raise ValueError(f"Declared existing match is absent: {row['model_id']} in package {package['package']}")
            for row in package["observations"]:
                if row["observation_status"] == "matched_existing" and row["model_id"] not in current_model_ids:
                    raise ValueError(f"Declared existing observation is absent: {row['model_id']}")

        makes = list(db.scalars(select(CatalogMake)))
        make_by_external = {make.external_id: make for make in makes if make.external_id}
        make_by_source_id: dict[str, CatalogMake] = {}
        brand_created_by_package: Counter = Counter()
        brand_reused_by_package: Counter = Counter()
        for package in packages:
            for brand in package["brands"]:
                external_id = brand["brand_id"]
                existing = make_by_external.get(external_id)
                if existing is None:
                    wanted = norm(brand["brand_name"])
                    candidates = [make for make in makes if wanted in {norm(make.name), norm(make.slug), *(norm(a) for a in make.aliases or [])}]
                    if len(candidates) > 1:
                        raise ValueError(f"Ambiguous brand {brand['brand_id']} / {brand['brand_name']}")
                    existing = candidates[0] if candidates else None
                if existing is None:
                    make_slug = slug(brand["brand_name"])
                    if not make_slug or any(item.slug == make_slug for item in makes):
                        make_slug = slug(external_id) or external_id.lower()
                    existing = CatalogMake(
                        id=uuid5(NAMESPACE_URL, SOURCE_NAMES[package["package"]] + external_id),
                        slug=make_slug, name=brand["brand_name"], external_id=external_id,
                        source_name=SOURCE_NAMES[package["package"]], aliases=[], manual_override=False,
                    )
                    db.add(existing)
                    db.flush()
                    makes.append(existing)
                    brand_created_by_package[package["package"]] += 1
                    if existing.external_id:
                        make_by_external[existing.external_id] = existing
                else:
                    brand_reused_by_package[package["package"]] += 1
                make_by_source_id[external_id] = existing

        # All brands referenced by additions must resolve, including long-lived
        # IDs supplied in package 02 rather than repeated in each delta.
        for package in packages:
            for row in package["models"]:
                if row["brand_id"] not in make_by_source_id:
                    make = make_by_external.get(row["brand_id"])
                    if make is None:
                        raise ValueError(f"Unknown brand ID {row['brand_id']} in package {package['package']}")
                    make_by_source_id[row["brand_id"]] = make

        for package in packages:
            code = package["package"]
            stats = Counter()
            stats["brands_created"] = brand_created_by_package[code]
            stats["brands_reused"] = brand_reused_by_package[code]
            source_name = SOURCE_NAMES[code]
            makes_in_package = {row["brand_id"]: make_by_source_id[row["brand_id"]] for row in package["brands"]}
            category_links: dict[str, set[str]] = defaultdict(set)
            for relation in package["brand_categories"]:
                category_links[relation["brand_id"]].add(category_to_code[relation["category_id"]])
            for model_row in package["models"]:
                category_links[model_row["brand_id"]].add(category_to_code[model_row["category_id"]])
            # Append only the new category memberships and package provenance;
            # preserve the established UUID, name, slug, aliases and source.
            all_source_brand_ids = set(category_links) | set(makes_in_package)
            for brand_id in all_source_brand_ids:
                make = make_by_source_id.get(brand_id) or make_by_external.get(brand_id)
                if make is None:
                    raise ValueError(f"Unknown category brand ID {brand_id} in package {code}")
                metadata = dict(make.source_metadata or {})
                membership = set(metadata.get("category_codes", [])) | category_links.get(brand_id, set())
                metadata["category_codes"] = sorted(membership)
                entries = dict(metadata.get(f"catalog_pack_{code}", {}))
                new_entry = {
                    "brand_id": brand_id,
                    "brand_record": next((row for row in package["brands"] if row["brand_id"] == brand_id), None),
                    "category_codes_added": sorted(category_links.get(brand_id, set())),
                    "archive_sha256": package["checksum"],
                }
                if entries.get("record") != new_entry:
                    entries["record"] = new_entry
                    metadata[f"catalog_pack_{code}"] = entries
                    stats["brand_metadata_updated"] += set_metadata(make, metadata)

            model_audit_by_id: dict[str, list] = defaultdict(list)
            for audit in package["model_audit"]:
                model_audit_by_id[audit.get("model_id", "")].append(audit)
            spec_audit_by_id: dict[str, list] = defaultdict(list)
            for audit in package["spec_audit"]:
                spec_audit_by_id[audit.get("model_id", "")].append(audit)
            variants_by_model: dict[str, list] = defaultdict(list)
            specs_by_model: dict[str, list] = defaultdict(list)
            for variant in package["variants"]:
                variants_by_model[variant["model_id"]].append(variant)
            for spec in package["specs"]:
                specs_by_model[spec["model_id"]].append(spec)

            for raw in package["models"]:
                brand_id = raw["brand_id"]
                make = make_by_source_id.get(brand_id) or make_by_external.get(brand_id)
                if make is None:
                    raise ValueError(f"Unknown model brand {brand_id}")
                category_code = category_to_code[raw["category_id"]]
                external_id = raw["model_id"]
                candidates = [model for model in existing_models if model.external_id == external_id]
                if len(candidates) > 1:
                    raise ValueError(f"Ambiguous model match: {brand_id} / {raw['model_name']}")
                if candidates:
                    matched = candidates[0]
                    if matched.make_id != make.id:
                        raise ValueError(f"Model ID {external_id} belongs to a different make")
                    categories = set((matched.source_metadata or {}).get("category_codes", []))
                    if not categories or category_code not in categories:
                        raise ValueError(f"Model ID {external_id} conflicts with category {category_code}")
                else:
                    same_name = [model for model in existing_models if model.make_id == make.id and norm(raw["model_name"]) in {norm(model.name), norm(model.slug), *(norm(alias) for alias in model.aliases or [])}]
                    uncategorized = [model for model in same_name if not (model.source_metadata or {}).get("category_codes")]
                    if uncategorized:
                        raise ValueError(f"Same-name model has no category metadata and needs review: {brand_id} / {raw['model_name']}")
                    # Model identity includes its category. Equal names in a
                    # different established section are distinct catalog rows.
                    candidates = [model for model in same_name if category_code in set((model.source_metadata or {}).get("category_codes", []))]
                if len(candidates) > 1:
                    raise ValueError(f"Ambiguous model match: {brand_id} / {raw['model_name']}")
                is_new = not candidates
                if is_new:
                    model = CatalogModel(
                        id=uuid5(NAMESPACE_URL, source_name + external_id), make_id=make.id,
                        slug=external_id, name=raw["model_name"], external_id=external_id,
                        source_name=source_name, aliases=[], manual_override=False,
                    )
                    db.add(model)
                    existing_models.append(model)
                    existing_ids.add(external_id)
                    stats["models_created"] += 1
                else:
                    model = candidates[0]
                    if model.make_id != make.id:
                        raise ValueError(f"Model ID {external_id} belongs to a different make")
                    stats["models_reused"] += 1

                source_meta = dict(model.source_metadata or {})
                memberships = set(source_meta.get("category_codes", []))
                if package["metadata_by_id"][external_id].get("import_visibility") == "public_catalog":
                    memberships.add(category_code)
                source_meta["category_codes"] = sorted(memberships)
                package_key = f"catalog_pack_{code}"
                pack_record = {
                    "record": raw,
                    "metadata": package["metadata_by_id"][external_id],
                    "source_audit": model_audit_by_id.get(external_id, []),
                    "spec_audit": spec_audit_by_id.get(external_id, []),
                    "variants": variants_by_model.get(external_id, []),
                    "variant_record_kind": "catalog_spec_profile_not_purchase_trim" if code == "05" else "supplier_recorded_variant_not_production_generation",
                    "specs": specs_by_model.get(external_id, []),
                    "archive_sha256": package["checksum"],
                }
                if source_meta.get(package_key) != pack_record:
                    source_meta[package_key] = pack_record
                    stats["model_metadata_updated"] += set_metadata(model, source_meta)
                stats[f"models_{category_code}"] += 1

            # A delta may add exact manufacturer variants for a model that was
            # already in package 02. Keep those facts on that existing model
            # without changing its name, category, generations or listing data.
            added_ids = {row["model_id"] for row in package["models"]}
            referenced_ids = set(variants_by_model) | set(specs_by_model)
            for model_id in sorted(referenced_ids - added_ids):
                model = next((item for item in existing_models if item.external_id == model_id), None)
                if model is None:
                    raise ValueError(f"Variant/spec references a model not in the catalog: {model_id}")
                source_meta = dict(model.source_metadata or {})
                package_key = f"catalog_pack_{code}"
                pack_record = dict(source_meta.get(package_key, {}))
                pack_record.setdefault("record", None)
                pack_record.setdefault("metadata", None)
                pack_record.setdefault("source_audit", [])
                pack_record.setdefault("spec_audit", spec_audit_by_id.get(model_id, []))
                pack_record["variants"] = variants_by_model.get(model_id, [])
                pack_record["variant_record_kind"] = "manufacturer_exact_variant"
                pack_record["specs"] = specs_by_model.get(model_id, [])
                pack_record["archive_sha256"] = package["checksum"]
                if source_meta.get(package_key) != pack_record:
                    source_meta[package_key] = pack_record
                    stats["existing_variant_metadata_updated"] += set_metadata(model, source_meta)

            # Package 03's manufacturer observations that matched package 02
            # remain observations; names and category links are not rewritten.
            if code == "03":
                observation_by_id: dict[str, list] = defaultdict(list)
                for row in package["observations"]:
                    if row.get("observation_status") == "matched_existing":
                        observation_by_id[row["model_id"]].append(row)
                for model_id, rows in observation_by_id.items():
                    model = next((item for item in existing_models if item.external_id == model_id), None)
                    if model is None:
                        raise ValueError(f"Package 03 claims matched existing model not found: {model_id}")
                    meta = dict(model.source_metadata or {})
                    if meta.get("catalog_pack_03_observations") != rows:
                        meta["catalog_pack_03_observations"] = rows
                        stats["existing_observation_metadata_updated"] += set_metadata(model, meta)

            stats["reference_variants"] = len(package["variants"])
            stats["reference_spec_values"] = len(package["specs"])
            stats["matches_retained_as_evidence"] = len(package["matches"])
            stats["observations_retained_as_evidence"] = len(package["observations"])
            stats["model_source_audit_rows"] = len(package["model_audit"])
            stats["spec_source_audit_rows"] = len(package["spec_audit"])

            receipt = db.scalar(select(CatalogImport).where(CatalogImport.checksum == package["checksum"]).limit(1))
            if receipt is None:
                db.add(CatalogImport(
                    source_name=source_name, schema_version=1, checksum=package["checksum"],
                    counts=dict(stats),
                    source_metadata={
                        "archive": Path(package["path"]).name,
                        "category_mapping": SECTION_TO_CATEGORY,
                        "evidence": preserve_evidence(package, category_to_code),
                        "exclusions": "Delta rows only; matches/review files are retained as evidence and never imported as new catalog models.",
                    },
                ))
            totals[code] = {"source": source_name, "checksum": package["checksum"], "counts": dict(stats)}

        db.flush()
        if apply:
            db.commit()
        else:
            db.rollback()
    return {"applied": apply, "packages": totals}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack03", required=True)
    parser.add_argument("--pack04", required=True)
    parser.add_argument("--pack05", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run({"03": args.pack03, "04": args.pack04, "05": args.pack05}, args.apply), ensure_ascii=False))
