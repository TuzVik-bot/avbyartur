"""Import the supplied NHTSA catalog pack using the deployed app's DB session.

Run inside the API container with --archive PATH. Defaults to a rolled back dry run.
No source URLs or archive scripts are executed. No generations/specs are invented.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select, text
from app.db import SessionLocal
from app.models import CatalogImport, CatalogMake, CatalogModel

SOURCE = "NHTSA vPIC catalog pack 01"
CATEGORY = {"motorcycle": "motorcycles", "truck": "trucks"}


def normalize(value):
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def load_archive(path):
    with zipfile.ZipFile(path) as archive:
        def rows(name):
            return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))
        brands, models = rows("01_brands.csv"), rows("03_models.csv")
    assert len(brands) == 20 and len(models) == 718, "Unexpected pack size"
    assert len({r["brand_id"] for r in brands}) == len(brands)
    assert len({r["model_id"] for r in models}) == len(models)
    brand_ids = {r["brand_id"] for r in brands}
    for row in models:
        assert row["brand_id"] in brand_ids and row["category_id"] in CATEGORY
        assert row["model_name"].strip() and len(row["model_name"]) <= 180
        assert not row["year_from"] and not row["year_to"] and not row["model_variant"]
    return brands, models


def attach(row, raw, category, checksum):
    metadata = dict(row.source_metadata or {})
    categories = set(metadata.get("category_codes", []))
    categories.add(category)
    metadata["category_codes"] = sorted(categories)
    records = dict(metadata.get("catalog_pack_01", {}))
    records[raw.get("model_id") or raw["brand_id"]] = {**raw, "archive_sha256": checksum}
    metadata["catalog_pack_01"] = records
    if metadata == row.source_metadata:
        return False
    row.source_metadata = metadata
    return True


def run(path, apply=False):
    brands, models = load_archive(path)
    checksum = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    counts = Counter()
    with SessionLocal() as db:
        db.execute(text("select pg_advisory_xact_lock(74101501)"))
        makes = list(db.scalars(select(CatalogMake)))
        by_brand = {}
        for brand in brands:
            key = normalize(brand["brand_name"])
            existing = [m for m in makes if m.external_id == brand["brand_id"] or key in {normalize(m.name), normalize(m.slug), *(normalize(a) for a in m.aliases or [])}]
            assert len(existing) <= 1, f"Ambiguous brand {brand['brand_name']}"
            if existing:
                make = existing[0]
                counts["makes_reused"] += 1
            else:
                make = CatalogMake(id=uuid5(NAMESPACE_URL, SOURCE + brand["brand_id"]), name=brand["brand_name"], slug=re.sub(r"[^a-z0-9]+", "-", brand["brand_name"].lower()).strip("-"), external_id=brand["brand_id"], source_name=SOURCE, aliases=[], manual_override=False)
                db.add(make)
                db.flush()
                makes.append(make)
                counts["makes_created"] += 1
            by_brand[brand["brand_id"]] = make
        all_models = list(db.scalars(select(CatalogModel)))
        for raw in models:
            category = CATEGORY[raw["category_id"]]
            make = by_brand[raw["brand_id"]]
            brand = next(b for b in brands if b["brand_id"] == raw["brand_id"])
            attach(make, brand, category, checksum)
            matches = [m for m in all_models if m.external_id == raw["model_id"]]
            if not matches:
                matches = [m for m in all_models if m.make_id == make.id and normalize(raw["model_name"]) in {normalize(m.name), normalize(m.slug), *(normalize(a) for a in m.aliases or [])}]
            assert len(matches) <= 1, f"Ambiguous model {raw['model_id']}"
            if matches:
                model = matches[0]
                assert model.make_id == make.id
                counts["models_reused"] += 1
            else:
                model = CatalogModel(id=uuid5(NAMESPACE_URL, SOURCE + raw["model_id"]), make_id=make.id, name=raw["model_name"], slug=raw["model_id"], external_id=raw["model_id"], source_name=SOURCE, aliases=[], manual_override=False)
                db.add(model)
                all_models.append(model)
                counts["models_created"] += 1
            counts["models_metadata_updated"] += attach(model, raw, category, checksum)
            counts[category] += 1
        db.flush()
        receipt = db.scalar(select(CatalogImport).where(CatalogImport.source_name == SOURCE, CatalogImport.checksum == checksum))
        if receipt is None:
            db.add(CatalogImport(source_name=SOURCE, schema_version=1, checksum=checksum, counts=dict(counts), source_metadata={"archive": Path(path).name, "verification_status": "source_raw", "categories": CATEGORY, "notes": "User-supplied partial NHTSA model catalog; years, generations and specs absent."}))
        if apply:
            db.commit()
        else:
            db.rollback()
    return {"applied": apply, "archive_sha256": checksum, "counts": dict(counts)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.archive, args.apply), ensure_ascii=False))
