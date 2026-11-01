"""Preview/apply additive Onliner names, preserving every existing catalog row."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal
from app.models import CatalogMake, CatalogModel
if __package__:
    from .onliner_catalog_plan import reconcile
else:
    from onliner_catalog_plan import reconcile


def baseline(db):
    makes = db.scalars(select(CatalogMake).order_by(CatalogMake.slug)).all()
    models = db.scalars(select(CatalogModel).order_by(CatalogModel.slug)).all()
    return {"makes": [{"id": str(make.id), "name": make.name, "slug": make.slug, "aliases": make.aliases, "models": [{"id": str(model.id), "name": model.name, "slug": model.slug, "aliases": model.aliases, "source_metadata": model.source_metadata} for model in models if model.make_id == make.id]} for make in makes]}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--expected-plan-sha256", default="")
    args = parser.parse_args()
    try:
        raw = args.path.read_bytes()
        source = json.loads(raw)
        checksum = hashlib.sha256(raw).hexdigest()
        with SessionLocal() as db:
            if db.bind.dialect.name != "postgresql":
                raise ValueError("PostgreSQL required")
            if args.apply:
                db.execute(text("SET LOCAL lock_timeout = '10s'"))
                db.execute(text("LOCK TABLE catalog_makes, catalog_models IN SHARE ROW EXCLUSIVE MODE"))
            before = baseline(db)
            plan = reconcile(source, before)
            plan_checksum = digest({"source_sha256": checksum, "baseline": before, "plan": plan})
            report = {"status": "applied" if args.apply else "preview", "source_sha256": checksum, "plan_sha256": plan_checksum, "before_makes": len(before["makes"]), "before_models": sum(len(m["models"]) for m in before["makes"]), "plan": plan, "inserted_make_ids": [], "inserted_model_ids": []}
            if args.apply:
                if args.confirm != "ADD-ONLINER-CATALOG" or args.expected_plan_sha256 != plan_checksum:
                    raise ValueError("Apply requires explicit confirmation and the exact unchanged preview checksum")
                provenance = {"name": "Onliner", "url": source["source_url"], "retrieved_at": source["retrieved_at"], "permission": source["permission"], "snapshot_sha256": checksum}
                makes = {m.slug: m for m in db.scalars(select(CatalogMake)).all()}
                for row in plan["makes"]:
                    make = CatalogMake(slug=row["slug"], name=row["name"], aliases=["Ягуар"] if row["slug"] == "jaguar" else [], external_id=f"onliner:manufacturer:{row['source_id']}", source_name="Onliner", source_metadata={**provenance, "source_id": row["source_id"]})
                    db.add(make)
                    db.flush()
                    makes[make.slug] = make
                    report["inserted_make_ids"].append(str(make.id))
                report["added_aliases"] = []
                for row in plan["aliases"]:
                    make = makes[row["make_slug"]]
                    old_aliases = list(make.aliases or [])
                    make.aliases = [*old_aliases, row["alias"]]
                    report["added_aliases"].append({"make_id": str(make.id), "old_aliases": old_aliases, "added_alias": row["alias"]})
                db.flush()
                for row in plan["models"]:
                    model = CatalogModel(make_id=makes[row["make_slug"]].id, slug=row["slug"], name=row["name"], aliases=[], external_id=f"onliner:model:{row['source_id']}", source_name="Onliner", source_metadata={**provenance, "source_id": row["source_id"], "manufacturer_id": row["source_make_id"], "category_codes": ["cars"]})
                    db.add(model)
                    db.flush()
                    report["inserted_model_ids"].append(str(model.id))
                report["category_changes"] = []
                all_models = {(model.make_id, model.slug): model for model in db.scalars(select(CatalogModel)).all()}
                for row in plan["categories"]:
                    model = all_models[(makes[row["make_slug"]].id, row["model_slug"])]
                    old_metadata = model.source_metadata
                    metadata = dict(old_metadata or {})
                    metadata["category_codes"] = [*(metadata.get("category_codes") or []), "cars"]
                    model.source_metadata = metadata
                    report["category_changes"].append({"model_id": str(model.id), "old_metadata": old_metadata})
                db.flush()
                after = baseline(db)
                replay = reconcile(source, after)
                if replay["makes"] or replay["models"] or replay["aliases"] or replay["categories"]:
                    raise ValueError("Post-insert reconciliation is not idempotent")
                # Write the exact rollback IDs before commit; any I/O failure aborts.
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                db.commit()
            else:
                db.rollback()
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({key: report[key] for key in ("status", "source_sha256", "plan_sha256", "before_makes", "before_models")}, ensure_ascii=False))
        print(json.dumps({"add_makes": len(plan["makes"]), "add_models": len(plan["models"]), "add_aliases": len(plan["aliases"]), "add_car_categories": len(plan["categories"]), "equivalent_existing_models": len(plan["equivalent_models"]), "report": str(args.report)}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError) as error:
        print("Database operation failed; transaction not confirmed" if isinstance(error, SQLAlchemyError) else str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
