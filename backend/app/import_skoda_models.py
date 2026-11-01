"""Preview or insert only manufacturer-sourced Škoda model names from the seed."""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from uuid import uuid5

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.catalog_import import validate_document
from app.db import SessionLocal
from app.models import CatalogMake, CatalogModel


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return re.sub(r"^skoda\s+", "", value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--expected-plan-sha256", default="")
    args = parser.parse_args()
    try:
        raw = args.path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        if args.apply and (args.confirm != "ADD-SKODA-MODELS" or args.expected_sha256 != checksum or not re.fullmatch(r"[0-9a-f]{64}", args.expected_plan_sha256)):
            raise ValueError("Apply requires confirmation and the previewed seed and plan SHA256 values")
        document = json.loads(raw)
        validate_document(document)
        makes = [m for m in document["makes"] if m.get("qid") == "Q135700024" and m.get("slug") == "skoda"]
        if len(makes) != 1:
            raise ValueError("Expected exactly one Škoda seed make")
        models = [m for m in makes[0]["models"] if m.get("source", {}).get("name") == "Škoda Storyboard"]
        if not models or any(m.get("qid") or m.get("external_id") or m.get("generations") or not m.get("source", {}).get("url", "").startswith("https://") for m in models):
            raise ValueError("Unexpected manufacturer model record")
        keys = [(m["slug"], normalized_name(m["name"])) for m in models]
        if len({s for s, _ in keys}) != len(keys) or len({n for _, n in keys}) != len(keys) or any(not n for _, n in keys):
            raise ValueError("Duplicate or empty seed model identity")

        with SessionLocal() as db:
            if db.bind.dialect.name != "postgresql":
                raise ValueError("Only PostgreSQL is supported")
            if args.apply:
                db.execute(text("LOCK TABLE catalog_models IN SHARE ROW EXCLUSIVE MODE"))
            make_query = select(CatalogMake).where(CatalogMake.slug == "skoda")
            if args.apply:
                make_query = make_query.with_for_update(read=True)
            make = db.scalar(make_query)
            if make is None or make.external_id not in {"Q135700024", "wikidata:Q135700024"} or normalized_name(make.name) != "skoda":
                raise ValueError("Existing Škoda make identity does not match")
            existing = db.scalars(select(CatalogModel).where(CatalogModel.make_id == make.id)).all()
            missing, present = [], []
            for model in models:
                name = normalized_name(model["name"])
                slug_matches = [row for row in existing if row.slug == model["slug"]]
                name_matches = [row for row in existing if name in {
                    normalized_name(value) for value in [row.name, *(row.aliases or [])]
                    if isinstance(value, str)
                }]
                matches = {row.id: row for row in slug_matches + name_matches}
                if len(matches) > 1 or (slug_matches and slug_matches[0] not in name_matches):
                    raise ValueError(f"Ambiguous existing model: {model['name']}")
                if matches:
                    present.append(model["name"])
                else:
                    missing.append(model)
            planned = [
                {"id": str(uuid5(make.id, f"skoda:model:{model['slug']}")), "name": model["name"], "slug": model["slug"]}
                for model in missing
            ]
            canonical_plan = json.dumps(sorted(planned, key=lambda item: item["id"]), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            plan_sha256 = hashlib.sha256(canonical_plan).hexdigest()
            if args.apply and plan_sha256 != args.expected_plan_sha256:
                raise ValueError("Model insertion plan changed since preview; no changes committed")
            planned_ids = [uuid5(make.id, f"skoda:model:{model['slug']}") for model in missing]
            if len(set(planned_ids)) != len(planned_ids):
                raise ValueError("Duplicate planned model ID")
            if planned_ids and db.scalar(select(CatalogModel.id).where(CatalogModel.id.in_(planned_ids)).limit(1)) is not None:
                raise ValueError("Planned model ID collides with an existing catalog model")
            if args.apply:
                for model, model_id in zip(missing, planned_ids, strict=True):
                    db.add(CatalogModel(id=model_id, make_id=make.id, slug=model["slug"], name=model["name"], aliases=model.get("aliases", []), source_name=model["source"]["name"], source_metadata={**model["source"], "category_codes": ["cars"]}))
                db.commit()
            else:
                db.rollback()
        print(json.dumps({"status": "applied" if args.apply else "preview", "sha256": checksum, "present": present, "missing": [m["name"] for m in missing], "planned": planned, "plan_sha256": plan_sha256}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, SQLAlchemyError) as error:
        # Database exceptions can contain credentials or connection details.
        message = "Database operation failed; no changes committed" if isinstance(error, SQLAlchemyError) else str(error)
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
