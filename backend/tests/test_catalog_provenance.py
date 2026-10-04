import copy
import json
import uuid

from app.catalog_import import import_catalog
from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogImport,
    CatalogMake,
    CatalogModel,
    CatalogSource,
)
from sqlalchemy import select


def _record_source(name: str, kind: str, suffix: str) -> dict:
    return {
        "name": name,
        "qid": f"Q{suffix}{kind}",
        "url": f"https://sources.example/{suffix}/{kind}",
        "retrieved_at": "2026-09-27T12:00:00Z",
    }


def _catalog_document(suffix: str) -> tuple[dict, dict[str, dict]]:
    sources = {
        "make": _record_source("Wikidata", "make", suffix),
        "model": _record_source("Wikidata", "model", suffix),
        "generation": _record_source("BMW Group PressClub", "generation", suffix),
        "body_type": _record_source("Wikidata", "body_type", suffix),
        "body_variant": _record_source("BMW Group PressClub", "body_variant", suffix),
    }
    document = {
        "schema_version": 1,
        "source": {
            "name": f"Dataset {suffix}",
            "license": "CC0 1.0",
            "license_url": "https://license.example/cc0",
            "query_url": "https://query.example/catalog",
            "retrieved_at": "2026-09-27T12:00:00Z",
            "query_sha256": "a" * 64,
        },
        "makes": [
            {
                "qid": f"Q{suffix}make",
                "slug": f"make-{suffix}",
                "name": f"Make {suffix}",
                "aliases": [],
                "source": sources["make"],
                "models": [
                    {
                        "qid": f"Q{suffix}model",
                        "slug": f"model-{suffix}",
                        "name": f"Model {suffix}",
                        "aliases": [],
                        "source": sources["model"],
                        "generations": [
                            {
                                "qid": f"Q{suffix}generation",
                                "slug": f"generation-{suffix}",
                                "name": f"Generation {suffix}",
                                "year_from": 2020,
                                "year_to": None,
                                "source": sources["generation"],
                                "body_variants": [
                                    {
                                        "qid": f"Q{suffix}variant",
                                        "slug": f"variant-{suffix}",
                                        "name": f"Variant {suffix}",
                                        "source": sources["body_variant"],
                                    },
                                ],
                            },
                        ],
                    },
                ],
            },
            {
                "qid": f"Q{suffix}fallback",
                "slug": f"fallback-make-{suffix}",
                "name": f"Fallback Make {suffix}",
                "aliases": [],
                "models": [],
            },
        ],
        "body_types": [
            {
                "qid": f"Q{suffix}body",
                "slug": f"body-type-{suffix}",
                "name": f"Body Type {suffix}",
                "source": sources["body_type"],
            },
        ],
        "regions": [],
    }
    return document, sources


def _write_catalog(tmp_path, document: dict, name: str):
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_import_persists_dataset_and_per_record_provenance(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    document, sources = _catalog_document(suffix)
    path = _write_catalog(tmp_path, document, "catalog.json")

    with integration["SessionLocal"]() as db:
        result = import_catalog(db, path)
        assert result["status"] == "imported"
        make = db.scalar(select(CatalogMake).where(CatalogMake.slug == f"make-{suffix}"))
        model = db.scalar(select(CatalogModel).where(CatalogModel.slug == f"model-{suffix}"))
        generation = db.scalar(select(CatalogGeneration).where(CatalogGeneration.slug == f"generation-{suffix}"))
        body_type = db.scalar(select(CatalogBodyType).where(CatalogBodyType.slug == f"body-type-{suffix}"))
        body_variant = db.scalar(select(CatalogBodyVariant).where(CatalogBodyVariant.slug == f"variant-{suffix}"))
        fallback_make = db.scalar(select(CatalogMake).where(CatalogMake.slug == f"fallback-make-{suffix}"))
        dataset_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))

        assert make is not None and make.source_name == "Wikidata" and make.source_metadata == sources["make"]
        assert model is not None and model.source_name == "Wikidata" and model.source_metadata == sources["model"]
        assert generation is not None and generation.source_name == "BMW Group PressClub"
        assert generation.source_metadata == sources["generation"]
        assert body_type is not None and body_type.source_name == "Wikidata"
        assert body_type.source_metadata == sources["body_type"]
        assert body_variant is not None and body_variant.source_name == "BMW Group PressClub"
        assert body_variant.source_metadata == sources["body_variant"]
        assert fallback_make is not None and fallback_make.source_name == document["source"]["name"]
        assert fallback_make.source_metadata is None
        assert dataset_source is not None
        assert dataset_source.license == document["source"]["license"]
        assert dataset_source.license_url == document["source"]["license_url"]
        assert dataset_source.query_url == document["source"]["query_url"]
        assert dataset_source.retrieved_at == document["source"]["retrieved_at"]
        assert dataset_source.query_sha256 == document["source"]["query_sha256"]

        second_result = import_catalog(db, path)
        assert second_result["status"] == "unchanged"
        assert db.scalar(select(CatalogImport).where(CatalogImport.checksum == result["checksum"])) is not None
        assert db.scalar(select(CatalogMake).where(CatalogMake.slug == f"make-{suffix}")).source_metadata == sources["make"]


def test_manual_overrides_keep_record_provenance_when_catalog_changes(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    document, _sources = _catalog_document(suffix)
    path = _write_catalog(tmp_path, document, "manual-catalog.json")
    models = {
        "make": (CatalogMake, f"make-{suffix}"),
        "model": (CatalogModel, f"model-{suffix}"),
        "generation": (CatalogGeneration, f"generation-{suffix}"),
        "body_type": (CatalogBodyType, f"body-type-{suffix}"),
        "body_variant": (CatalogBodyVariant, f"variant-{suffix}"),
    }
    manual_metadata = {}

    with integration["SessionLocal"]() as db:
        assert import_catalog(db, path)["status"] == "imported"
        for key, (model_class, slug) in models.items():
            row = db.scalar(select(model_class).where(model_class.slug == slug))
            assert row is not None
            row.manual_override = True
            row.name = f"Manual {key} {suffix}"
            row.source_name = f"Manual source {key}"
            row.source_metadata = {"name": f"Manual source {key}", "url": f"https://manual.example/{key}"}
            manual_metadata[key] = copy.deepcopy(row.source_metadata)
        db.commit()

        changed = copy.deepcopy(document)
        changed["source"]["license_url"] = "https://license.example/updated"
        changed["source"]["query_url"] = "https://query.example/updated"
        changed["source"]["retrieved_at"] = "2026-09-28T12:00:00Z"
        changed["source"]["query_sha256"] = "b" * 64
        changed_sources = {
            "make": changed["makes"][0],
            "model": changed["makes"][0]["models"][0],
            "generation": changed["makes"][0]["models"][0]["generations"][0],
            "body_type": changed["body_types"][0],
            "body_variant": changed["makes"][0]["models"][0]["generations"][0]["body_variants"][0],
        }
        for key, record in changed_sources.items():
            record["source"]["name"] = f"Changed source {key}"
            record["source"]["url"] = f"https://changed.example/{key}"
            record["name"] = f"Changed {key} {suffix}"
        changed_path = _write_catalog(tmp_path, changed, "changed-catalog.json")

        assert import_catalog(db, changed_path)["status"] == "imported"
        for key, (model_class, slug) in models.items():
            row = db.scalar(select(model_class).where(model_class.slug == slug))
            assert row is not None
            assert row.manual_override is True
            assert row.name == f"Manual {key} {suffix}"
            assert row.source_name == f"Manual source {key}"
            assert row.source_metadata == manual_metadata[key]

        dataset_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))
        assert dataset_source is not None
        assert dataset_source.license_url == changed["source"]["license_url"]
        assert dataset_source.query_url == changed["source"]["query_url"]
        assert dataset_source.retrieved_at == changed["source"]["retrieved_at"]
        assert dataset_source.query_sha256 == changed["source"]["query_sha256"]


def test_unchanged_legacy_checksum_backfills_all_source_metadata(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    document, sources = _catalog_document(suffix)
    path = _write_catalog(tmp_path, document, "legacy-provenance.json")
    catalog_rows = {
        "make": (CatalogMake, f"make-{suffix}"),
        "model": (CatalogModel, f"model-{suffix}"),
        "generation": (CatalogGeneration, f"generation-{suffix}"),
        "body_type": (CatalogBodyType, f"body-type-{suffix}"),
        "body_variant": (CatalogBodyVariant, f"variant-{suffix}"),
    }

    with integration["SessionLocal"]() as db:
        first = import_catalog(db, path)
        assert first["status"] == "imported"
        imported = db.scalar(select(CatalogImport).where(CatalogImport.checksum == first["checksum"]))
        dataset_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))
        assert imported is not None and dataset_source is not None

        for key, (model_class, slug) in catalog_rows.items():
            row = db.scalar(select(model_class).where(model_class.slug == slug))
            assert row is not None
            row.source_name = document["source"]["name"]
            row.source_metadata = None
            if key == "body_variant":
                row.manual_override = True
                row.name = "Manually preserved variant"
                row.source_name = "Manual variant source"
                row.source_metadata = {"name": "Manual variant source", "qid": "QManualVariant"}

        imported.source_metadata = None
        dataset_source.license = "Legacy license"
        dataset_source.license_url = "https://legacy.example/license"
        dataset_source.query_url = "https://legacy.example/query"
        dataset_source.retrieved_at = "2020-01-01T00:00:00Z"
        dataset_source.query_sha256 = "f" * 64
        db.commit()

        unchanged = import_catalog(db, path)
        assert unchanged["status"] == "unchanged"
        expected_source_names = {
            "make": "Wikidata",
            "model": "Wikidata",
            "generation": "BMW Group PressClub",
            "body_type": "Wikidata",
        }
        for key, expected_source_name in expected_source_names.items():
            model_class, slug = catalog_rows[key]
            row = db.scalar(select(model_class).where(model_class.slug == slug))
            assert row is not None
            assert row.source_name == expected_source_name
            assert row.source_metadata == sources[key]

        variant = db.scalar(select(CatalogBodyVariant).where(CatalogBodyVariant.slug == f"variant-{suffix}"))
        assert variant is not None
        assert variant.manual_override is True
        assert variant.name == "Manually preserved variant"
        assert variant.source_name == "Manual variant source"
        assert variant.source_metadata == {"name": "Manual variant source", "qid": "QManualVariant"}

        expected_snapshot = {
            "source": document["source"],
            "geography_source": None,
        }
        assert imported.source_metadata == expected_snapshot
        assert dataset_source.license == document["source"]["license"]
        assert dataset_source.license_url == document["source"]["license_url"]
        assert dataset_source.query_url == document["source"]["query_url"]
        assert dataset_source.retrieved_at == document["source"]["retrieved_at"]
        assert dataset_source.query_sha256 == document["source"]["query_sha256"]
        assert len(db.scalars(select(CatalogImport).where(CatalogImport.checksum == first["checksum"])).all()) == 1

        repeated = import_catalog(db, path)
        assert repeated["status"] == "unchanged"
        assert len(db.scalars(select(CatalogImport).where(CatalogImport.checksum == repeated["checksum"])).all()) == 1
