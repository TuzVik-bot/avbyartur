import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogImport,
    CatalogMake,
    CatalogModel,
    CatalogSource,
    LocationCity,
    LocationRegion,
)


class CatalogInputError(ValueError):
    pass


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogInputError(f"{path} must be a non-empty string")
    return value.strip()


def _slug(item: dict, path: str) -> str:
    value = item.get("slug")
    if value:
        return _required_string(value, f"{path}.slug")
    qid = item.get("qid")
    if qid:
        return str(qid).lower()
    name = _required_string(item.get("name"), f"{path}.name")
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "item"


def _qid(item: dict) -> str | None:
    value = item.get("qid") or item.get("external_id")
    return f"wikidata:{value}" if value else None


def _aliases(item: dict) -> list[str]:
    values = item.get("aliases", [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise CatalogInputError("aliases must be an array of strings")
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _source_metadata(item: dict, path: str) -> dict | None:
    if "source" not in item:
        return None
    source = item["source"]
    if not isinstance(source, dict):
        raise CatalogInputError(f"{path}.source must be an object")
    _required_string(source.get("name"), f"{path}.source.name")
    return dict(source)


def _record_source(item: dict, dataset_source_name: str, path: str) -> tuple[dict | None, str]:
    metadata = _source_metadata(item, path)
    source_name = _required_string(metadata["name"], f"{path}.source.name") if metadata is not None else dataset_source_name
    return metadata, source_name


def _validate_dataset_source(source: Any, path: str) -> None:
    if not isinstance(source, dict):
        raise CatalogInputError(f"{path} metadata is required")
    _required_string(source.get("name"), f"{path}.name")
    _required_string(source.get("license"), f"{path}.license")
    for field in ("license_url", "query_url", "retrieved_at"):
        if source.get(field) is not None:
            _required_string(source[field], f"{path}.{field}")
    query_sha256 = source.get("query_sha256")
    if query_sha256 is not None and (
        not isinstance(query_sha256, str) or re.fullmatch(r"[0-9a-fA-F]{64}", query_sha256) is None
    ):
        raise CatalogInputError(f"{path}.query_sha256 must be a 64-character SHA-256 hex digest")


def _geography_record_source(item: dict, source: dict | None, path: str) -> dict | None:
    if source is None:
        return None
    metadata = dict(source)
    qid = _required_string(item.get("qid"), f"{path}.qid")
    url = item.get("url")
    metadata["qid"] = qid
    metadata["url"] = _required_string(url, f"{path}.url") if url is not None else f"https://www.wikidata.org/wiki/{qid}"
    return metadata


def validate_document(document: Any) -> dict[str, int]:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise CatalogInputError("catalog must be an object with schema_version: 1")
    source = document.get("source")
    _validate_dataset_source(source, "source")
    geography_source = document.get("geography_source")
    if "geography_source" in document:
        _validate_dataset_source(geography_source, "geography_source")
    for collection in ("makes", "body_types", "regions"):
        if not isinstance(document.get(collection), list):
            raise CatalogInputError(f"{collection} must be an array")
    counts = {"makes": 0, "models": 0, "generations": 0, "body_types": 0, "body_variants": 0, "regions": 0, "cities": 0}
    for mi, make in enumerate(document["makes"]):
        path = f"makes[{mi}]"
        _required_string(make.get("name"), f"{path}.name")
        _slug(make, path)
        _aliases(make)
        _source_metadata(make, path)
        if not isinstance(make.get("models", []), list):
            raise CatalogInputError(f"{path}.models must be an array")
        counts["makes"] += 1
        for oi, model in enumerate(make.get("models", [])):
            model_path = f"{path}.models[{oi}]"
            _required_string(model.get("name"), f"{model_path}.name")
            _slug(model, model_path)
            _aliases(model)
            _source_metadata(model, model_path)
            if not isinstance(model.get("generations", []), list):
                raise CatalogInputError(f"{model_path}.generations must be an array")
            counts["models"] += 1
            for gi, generation in enumerate(model.get("generations", [])):
                gen_path = f"{model_path}.generations[{gi}]"
                _required_string(generation.get("name"), f"{gen_path}.name")
                _slug(generation, gen_path)
                _source_metadata(generation, gen_path)
                for year_key in ("year_from", "year_to"):
                    year = generation.get(year_key)
                    if year is not None and (not isinstance(year, int) or year < 1886 or year > 2100):
                        raise CatalogInputError(f"{gen_path}.{year_key} must be null or an integer from 1886 to 2100")
                if generation.get("year_from") and generation.get("year_to") and generation["year_from"] > generation["year_to"]:
                    raise CatalogInputError(f"{gen_path} year_from must not exceed year_to")
                if not isinstance(generation.get("body_variants", []), list):
                    raise CatalogInputError(f"{gen_path}.body_variants must be an array")
                for vi, variant in enumerate(generation.get("body_variants", [])):
                    variant_path = f"{gen_path}.body_variants[{vi}]"
                    if isinstance(variant, dict):
                        _required_string(variant.get("name"), f"{variant_path}.name")
                        _slug(variant, variant_path)
                        _source_metadata(variant, variant_path)
                    elif not isinstance(variant, str) or not variant.strip():
                        raise CatalogInputError(f"{variant_path} must be a non-empty string or object")
                counts["generations"] += 1
                counts["body_variants"] += len(generation.get("body_variants", []))
    for bi, body_type in enumerate(document["body_types"]):
        _required_string(body_type.get("name"), f"body_types[{bi}].name")
        _slug(body_type, f"body_types[{bi}]")
        _source_metadata(body_type, f"body_types[{bi}]")
        counts["body_types"] += 1
    for ri, region in enumerate(document["regions"]):
        region_path = f"regions[{ri}]"
        _required_string(region.get("name"), f"{region_path}.name")
        _slug(region, region_path)
        _geography_record_source(region, geography_source, region_path)
        if not isinstance(region.get("cities", []), list):
            raise CatalogInputError(f"regions[{ri}].cities must be an array")
        counts["regions"] += 1
        counts["cities"] += len(region.get("cities", []))
        for ci, city in enumerate(region.get("cities", [])):
            city_path = f"{region_path}.cities[{ci}]"
            _required_string(city.get("name"), f"{city_path}.name")
            _slug(city, city_path)
            _geography_record_source(city, geography_source, city_path)
    return counts


def _find_existing(db: Session, model, *, external_id: str | None, slug: str, parent=None):
    row = db.scalar(select(model).where(model.external_id == external_id)) if external_id else None
    if row is None:
        query = select(model).where(model.slug == slug)
        if parent:
            query = query.where(parent[0] == parent[1])
        row = db.scalar(query)
    return row


def _upsert(db: Session, model, *, external_id: str | None, slug: str, parent=None, initial_values: dict | None = None):
    row = _find_existing(db, model, external_id=external_id, slug=slug, parent=parent)
    if row is None:
        values = dict(initial_values or {})
        if parent:
            values[parent[0].key] = parent[1]
        row = model(slug=slug, **values)
        db.add(row)
        db.flush()
    return row


def _set_source_metadata(row, source_name: str, source_metadata: dict | None) -> bool:
    if row is None or row.manual_override:
        return False
    changed = row.source_name != source_name or row.source_metadata != source_metadata
    if changed:
        row.source_name = source_name
        row.source_metadata = source_metadata
    return changed


def _refresh_dataset_source(db: Session, metadata: dict) -> bool:
    source = db.scalar(select(CatalogSource).where(CatalogSource.name == metadata["name"]))
    if source is None:
        db.add(CatalogSource(
            name=metadata["name"],
            license=metadata["license"],
            license_url=metadata.get("license_url"),
            query_url=metadata.get("query_url"),
            retrieved_at=metadata.get("retrieved_at"),
            query_sha256=metadata.get("query_sha256"),
        ))
        return True

    values = {
        "license": metadata["license"],
        "license_url": metadata.get("license_url"),
        "query_url": metadata.get("query_url"),
        "retrieved_at": metadata.get("retrieved_at"),
        "query_sha256": metadata.get("query_sha256"),
    }
    changed = any(getattr(source, key) != value for key, value in values.items())
    if changed:
        for key, value in values.items():
            setattr(source, key, value)
    return changed


def _backfill_existing_provenance(
    db: Session,
    document: dict,
    dataset_source_name: str,
    geography_source_name: str,
    geography_metadata: dict | None,
) -> bool:
    changed = False

    for make_data in document["makes"]:
        make = _find_existing(db, CatalogMake, external_id=_qid(make_data), slug=_slug(make_data, "make"))
        if make is None:
            continue
        make_metadata, make_source_name = _record_source(make_data, dataset_source_name, "make")
        changed = _set_source_metadata(make, make_source_name, make_metadata) or changed

        for model_data in make_data.get("models", []):
            model = _find_existing(
                db,
                CatalogModel,
                external_id=_qid(model_data),
                slug=_slug(model_data, "model"),
                parent=(CatalogModel.make_id, make.id),
            )
            if model is None:
                continue
            model_metadata, model_source_name = _record_source(model_data, dataset_source_name, "model")
            changed = _set_source_metadata(model, model_source_name, model_metadata) or changed

            for generation_data in model_data.get("generations", []):
                generation = _find_existing(
                    db,
                    CatalogGeneration,
                    external_id=_qid(generation_data),
                    slug=_slug(generation_data, "generation"),
                    parent=(CatalogGeneration.model_id, model.id),
                )
                if generation is None:
                    continue
                generation_metadata, generation_source_name = _record_source(
                    generation_data, dataset_source_name, "generation",
                )
                changed = _set_source_metadata(generation, generation_source_name, generation_metadata) or changed

                for variant in generation_data.get("body_variants", []):
                    variant_data = variant if isinstance(variant, dict) else {"name": variant}
                    body_variant = _find_existing(
                        db,
                        CatalogBodyVariant,
                        external_id=_qid(variant_data),
                        slug=_slug(variant_data, "body_variant"),
                        parent=(CatalogBodyVariant.generation_id, generation.id),
                    )
                    if body_variant is None:
                        continue
                    variant_metadata, variant_source_name = _record_source(
                        variant_data, dataset_source_name, "body_variant",
                    )
                    changed = _set_source_metadata(body_variant, variant_source_name, variant_metadata) or changed

    for body_data in document["body_types"]:
        body = _find_existing(
            db, CatalogBodyType, external_id=_qid(body_data), slug=_slug(body_data, "body_type"),
        )
        if body is None:
            continue
        body_metadata, body_source_name = _record_source(body_data, dataset_source_name, "body_type")
        changed = _set_source_metadata(body, body_source_name, body_metadata) or changed

    for region_data in document["regions"]:
        region = _find_existing(
            db, LocationRegion, external_id=_qid(region_data), slug=_slug(region_data, "region"),
        )
        if region is None:
            continue
        region_metadata = _geography_record_source(region_data, geography_metadata, "region")
        changed = _set_source_metadata(region, geography_source_name, region_metadata) or changed
        for city_data in region_data.get("cities", []):
            city = _find_existing(
                db,
                LocationCity,
                external_id=_qid(city_data),
                slug=_slug(city_data, "city"),
                parent=(LocationCity.region_id, region.id),
            )
            if city is None:
                continue
            city_metadata = _geography_record_source(city_data, geography_metadata, "city")
            changed = _set_source_metadata(city, geography_source_name, city_metadata) or changed

    return changed


def import_catalog(db: Session, path: Path, *, dry_run: bool = False) -> dict:
    raw = path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    document = json.loads(raw)
    counts = validate_document(document)
    metadata = document["source"]
    geography_metadata = document.get("geography_source")
    dataset_source_name = metadata["name"]
    geography_source_name = geography_metadata["name"] if geography_metadata else dataset_source_name
    source_snapshot = {
        "source": dict(metadata),
        "geography_source": dict(geography_metadata) if geography_metadata else None,
    }
    existing_import = db.scalar(select(CatalogImport).where(CatalogImport.checksum == checksum).limit(1))
    if existing_import:
        changed = False
        if existing_import.source_metadata != source_snapshot:
            existing_import.source_metadata = source_snapshot
            changed = True
        changed = _refresh_dataset_source(db, metadata) or changed
        changed = _backfill_existing_provenance(
            db, document, dataset_source_name, geography_source_name, geography_metadata,
        ) or changed
        if changed:
            db.commit()
        return {"status": "unchanged", "checksum": checksum, "counts": existing_import.counts}

    _refresh_dataset_source(db, metadata)

    for make_data in document["makes"]:
        make_source, make_source_name = _record_source(make_data, dataset_source_name, "make")
        make = _upsert(db, CatalogMake, external_id=_qid(make_data), slug=_slug(make_data, "make"), initial_values={"name": make_data["name"]})
        if not make.manual_override:
            make.name = make_data["name"]
            make.aliases = _aliases(make_data)
            make.external_id = _qid(make_data)
            make.source_name = make_source_name
            make.source_metadata = make_source
        for model_data in make_data.get("models", []):
            model_source, model_source_name = _record_source(model_data, dataset_source_name, "model")
            model = _upsert(db, CatalogModel, external_id=_qid(model_data), slug=_slug(model_data, "model"), parent=(CatalogModel.make_id, make.id), initial_values={"name": model_data["name"]})
            if not model.manual_override:
                model.make_id = make.id
                model.name = model_data["name"]
                model.aliases = _aliases(model_data)
                model.external_id = _qid(model_data)
                model.source_name = model_source_name
                model.source_metadata = model_source
            for generation_data in model_data.get("generations", []):
                generation_source, generation_source_name = _record_source(generation_data, dataset_source_name, "generation")
                gen_slug = _slug(generation_data, "generation")
                generation = _upsert(db, CatalogGeneration, external_id=_qid(generation_data), slug=gen_slug, parent=(CatalogGeneration.model_id, model.id), initial_values={"name": generation_data["name"], "year_from": generation_data.get("year_from"), "year_to": generation_data.get("year_to")})
                if not generation.manual_override:
                    generation.model_id = model.id
                    generation.name = generation_data["name"]
                    generation.year_from = generation_data.get("year_from")
                    generation.year_to = generation_data.get("year_to")
                    generation.external_id = _qid(generation_data)
                    generation.source_name = generation_source_name
                    generation.source_metadata = generation_source
                for variant_data in generation_data.get("body_variants", []):
                    variant_name = _required_string(variant_data.get("name") if isinstance(variant_data, dict) else variant_data, "body_variant.name")
                    variant_data = variant_data if isinstance(variant_data, dict) else {"name": variant_name}
                    variant_source, variant_source_name = _record_source(variant_data, dataset_source_name, "body_variant")
                    variant = _upsert(db, CatalogBodyVariant, external_id=_qid(variant_data), slug=_slug(variant_data, "body_variant"), parent=(CatalogBodyVariant.generation_id, generation.id), initial_values={"name": variant_name})
                    if not variant.manual_override:
                        variant.generation_id = generation.id
                        variant.name = variant_name
                        variant.external_id = _qid(variant_data)
                        variant.source_name = variant_source_name
                        variant.source_metadata = variant_source

    for body_data in document["body_types"]:
        body_source, body_source_name = _record_source(body_data, dataset_source_name, "body_type")
        body = _upsert(db, CatalogBodyType, external_id=_qid(body_data), slug=_slug(body_data, "body_type"), initial_values={"name": body_data["name"]})
        if not body.manual_override:
            body.name = body_data["name"]
            body.external_id = _qid(body_data)
            body.source_name = body_source_name
            body.source_metadata = body_source
    for region_data in document["regions"]:
        region = _upsert(db, LocationRegion, external_id=_qid(region_data), slug=_slug(region_data, "region"), initial_values={"name": region_data["name"]})
        if not region.manual_override:
            region.name = region_data["name"]
            region.external_id = _qid(region_data)
            region.source_name = geography_source_name
            region.source_metadata = _geography_record_source(region_data, geography_metadata, "region")
        for city_data in region_data.get("cities", []):
            city = _upsert(db, LocationCity, external_id=_qid(city_data), slug=_slug(city_data, "city"), parent=(LocationCity.region_id, region.id), initial_values={"name": city_data["name"]})
            if not city.manual_override:
                city.region_id = region.id
                city.name = city_data["name"]
                city.external_id = _qid(city_data)
                city.source_name = geography_source_name
                city.source_metadata = _geography_record_source(city_data, geography_metadata, "city")

    if dry_run:
        db.flush()
        db.rollback()
        return {"status": "dry_run", "checksum": checksum, "counts": counts}
    db.add(CatalogImport(
        source_name=dataset_source_name, schema_version=1, checksum=checksum, counts=counts,
        source_metadata=source_snapshot,
    ))
    db.commit()
    return {"status": "imported", "checksum": checksum, "counts": counts}
