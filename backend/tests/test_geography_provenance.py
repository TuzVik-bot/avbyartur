import copy
import json
import uuid
from pathlib import Path

from app.catalog_import import import_catalog
from app.models import CatalogImport, CatalogSource, LocationCity, LocationRegion
from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data/catalog.json"


def _document(suffix: str) -> dict:
    return {
        "schema_version": 1,
        "source": {
            "name": "Wikidata",
            "license": "CC0 1.0",
            "license_url": "https://www.wikidata.org/wiki/Wikidata:Reuse",
            "retrieved_at": "2026-09-26T22:45:26Z",
            "query_url": "https://query.wikidata.org/main",
            "query_sha256": "a" * 64,
        },
        "geography_source": {
            "name": "Wikidata",
            "license": "CC0 1.0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "retrieved_at": "2026-09-26T22:42:14Z",
            "query_url": "https://query.wikidata.org/geography",
            "query_sha256": "b" * 64,
        },
        "makes": [],
        "body_types": [],
        "regions": [
            {
                "qid": f"Q{suffix}1",
                "name": f"Test Region {suffix}",
                "slug": f"test-region-{suffix}",
                "cities": [
                    {
                        "qid": f"Q{suffix}2",
                        "name": f"Test City {suffix}",
                        "slug": f"test-city-{suffix}",
                    },
                ],
            },
        ],
    }


def _write_document(tmp_path, document: dict, filename: str):
    path = tmp_path / filename
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_imported_seed_keeps_geography_sources_separate_from_main_query(integration, tmp_path):
    seed = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    document = {
        "schema_version": seed["schema_version"],
        "source": seed["source"],
        "geography_source": seed["geography_source"],
        "makes": [],
        "body_types": [],
        "regions": seed["regions"],
    }
    geography_source = document["geography_source"]
    expected_regions = {region["slug"]: region for region in document["regions"]}
    expected_cities = {
        city["slug"]: city
        for region in document["regions"]
        for city in region["cities"]
    }
    path = _write_document(tmp_path, document, "geography-seed.json")

    with integration["SessionLocal"]() as db:
        prior_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))
        prior_source_values = None if prior_source is None else {
            "license": prior_source.license,
            "license_url": prior_source.license_url,
            "query_url": prior_source.query_url,
            "retrieved_at": prior_source.retrieved_at,
            "query_sha256": prior_source.query_sha256,
        }
        result = import_catalog(db, path)
        assert result["status"] == "imported"
        regions = db.scalars(select(LocationRegion).where(
            LocationRegion.slug.in_(expected_regions),
        )).all()
        cities = db.scalars(select(LocationCity).where(
            LocationCity.slug.in_(expected_cities),
        )).all()
        assert len(regions) == 7
        assert len(cities) == 12
        for row in regions:
            expected = expected_regions[row.slug]
            assert row.source_name == geography_source["name"]
            assert row.source_metadata == {
                **geography_source,
                "qid": expected["qid"],
                "url": f"https://www.wikidata.org/wiki/{expected['qid']}",
            }
        for row in cities:
            expected = expected_cities[row.slug]
            assert row.source_name == geography_source["name"]
            assert row.source_metadata == {
                **geography_source,
                "qid": expected["qid"],
                "url": f"https://www.wikidata.org/wiki/{expected['qid']}",
            }

        imported = db.scalar(select(CatalogImport).where(CatalogImport.checksum == result["checksum"]))
        assert imported is not None
        assert imported.source_metadata == {
            "source": document["source"],
            "geography_source": geography_source,
        }
        dataset_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))
        assert dataset_source is not None
        assert dataset_source.query_url == document["source"]["query_url"]
        assert dataset_source.query_sha256 == document["source"]["query_sha256"]

        db.execute(delete(LocationCity).where(LocationCity.id.in_([row.id for row in cities])))
        db.execute(delete(LocationRegion).where(LocationRegion.id.in_([row.id for row in regions])))
        db.delete(imported)
        if prior_source_values is None:
            db.delete(dataset_source)
        else:
            for field, value in prior_source_values.items():
                setattr(dataset_source, field, value)
        db.commit()


def test_import_keeps_geography_provenance_and_both_dataset_queries(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    document = _document(suffix)
    path = _write_document(tmp_path, document, "geography.json")
    geography_source = document["geography_source"]

    with integration["SessionLocal"]() as db:
        result = import_catalog(db, path)
        assert result["status"] == "imported"
        region = db.scalar(select(LocationRegion).where(LocationRegion.slug == f"test-region-{suffix}"))
        city = db.scalar(select(LocationCity).where(LocationCity.slug == f"test-city-{suffix}"))
        assert region is not None
        assert city is not None

        expected_region_source = {
            **geography_source,
            "qid": f"Q{suffix}1",
            "url": f"https://www.wikidata.org/wiki/Q{suffix}1",
        }
        expected_city_source = {
            **geography_source,
            "qid": f"Q{suffix}2",
            "url": f"https://www.wikidata.org/wiki/Q{suffix}2",
        }
        assert region.source_name == geography_source["name"]
        assert region.source_metadata == expected_region_source
        assert city.source_name == geography_source["name"]
        assert city.source_metadata == expected_city_source

        imported = db.scalar(select(CatalogImport).where(CatalogImport.checksum == result["checksum"]))
        assert imported is not None
        assert imported.source_metadata == {
            "source": document["source"],
            "geography_source": geography_source,
        }
        assert imported.source_metadata["source"]["query_sha256"] != imported.source_metadata["geography_source"]["query_sha256"]

        dataset_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))
        assert dataset_source is not None
        assert dataset_source.query_url == document["source"]["query_url"]
        assert dataset_source.query_sha256 == document["source"]["query_sha256"]

        repeated = import_catalog(db, path)
        assert repeated["status"] == "unchanged"
        assert db.scalar(select(CatalogImport).where(CatalogImport.checksum == result["checksum"])) is imported

        imported.source_metadata = None
        db.commit()
        backfilled = import_catalog(db, path)
        assert backfilled["status"] == "unchanged"
        assert imported.source_metadata == {
            "source": document["source"],
            "geography_source": geography_source,
        }
        assert len(db.scalars(select(CatalogImport).where(CatalogImport.checksum == result["checksum"])).all()) == 1


def test_geography_manual_overrides_keep_provenance_when_source_queries_change(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    document = _document(suffix)
    path = _write_document(tmp_path, document, "initial-geography.json")

    with integration["SessionLocal"]() as db:
        assert import_catalog(db, path)["status"] == "imported"
        region = db.scalar(select(LocationRegion).where(LocationRegion.slug == f"test-region-{suffix}"))
        city = db.scalar(select(LocationCity).where(LocationCity.slug == f"test-city-{suffix}"))
        assert region is not None and city is not None
        region.manual_override = True
        region.name = "Manual Region"
        region.source_name = "Manual region source"
        region.source_metadata = {"name": "Manual region source", "qid": "QManual1", "url": "https://manual.example/region"}
        city.manual_override = True
        city.name = "Manual City"
        city.source_name = "Manual city source"
        city.source_metadata = {"name": "Manual city source", "qid": "QManual2", "url": "https://manual.example/city"}
        manual_region_source = copy.deepcopy(region.source_metadata)
        manual_city_source = copy.deepcopy(city.source_metadata)
        db.commit()

        changed = copy.deepcopy(document)
        changed["source"]["query_url"] = "https://query.wikidata.org/main-updated"
        changed["source"]["query_sha256"] = "c" * 64
        changed["geography_source"]["query_url"] = "https://query.wikidata.org/geography-updated"
        changed["geography_source"]["query_sha256"] = "d" * 64
        changed["regions"][0]["name"] = "Changed Region"
        changed["regions"][0]["cities"][0]["name"] = "Changed City"
        changed_path = _write_document(tmp_path, changed, "changed-geography.json")

        changed_result = import_catalog(db, changed_path)
        assert changed_result["status"] == "imported"
        region = db.scalar(select(LocationRegion).where(LocationRegion.slug == f"test-region-{suffix}"))
        city = db.scalar(select(LocationCity).where(LocationCity.slug == f"test-city-{suffix}"))
        assert region is not None and city is not None
        assert region.name == "Manual Region"
        assert region.source_name == "Manual region source"
        assert region.source_metadata == manual_region_source
        assert city.name == "Manual City"
        assert city.source_name == "Manual city source"
        assert city.source_metadata == manual_city_source

        latest = db.scalar(select(CatalogImport).where(CatalogImport.checksum == changed_result["checksum"]))
        assert latest is not None
        assert latest.source_metadata["source"]["query_sha256"] == changed["source"]["query_sha256"]
        assert latest.source_metadata["geography_source"]["query_sha256"] == changed["geography_source"]["query_sha256"]

        dataset_source = db.scalar(select(CatalogSource).where(CatalogSource.name == document["source"]["name"]))
        assert dataset_source is not None
        assert dataset_source.query_url == changed["source"]["query_url"]
        assert dataset_source.query_sha256 == changed["source"]["query_sha256"]


def test_unchanged_legacy_import_backfills_geography_provenance_without_duplicates(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    document = _document(suffix)
    document["source"]["name"] = "Main Dataset Source"
    document["geography_source"]["name"] = "Geography Query Source"
    path = _write_document(tmp_path, document, "legacy-geography.json")

    with integration["SessionLocal"]() as db:
        first_result = import_catalog(db, path)
        assert first_result["status"] == "imported"
        region = db.scalar(select(LocationRegion).where(LocationRegion.slug == f"test-region-{suffix}"))
        city = db.scalar(select(LocationCity).where(LocationCity.slug == f"test-city-{suffix}"))
        imported = db.scalar(select(CatalogImport).where(CatalogImport.checksum == first_result["checksum"]))
        assert region is not None and city is not None and imported is not None

        region.manual_override = True
        region.name = "Manual Legacy Region"
        region.source_name = "Manual Region Source"
        region.source_metadata = {"name": "Manual Region Source", "qid": "QManualRegion"}
        city.source_name = document["source"]["name"]
        city.source_metadata = None
        imported.source_metadata = None
        db.commit()
        manual_region_metadata = copy.deepcopy(region.source_metadata)

        backfilled = import_catalog(db, path)
        assert backfilled["status"] == "unchanged"
        assert region.name == "Manual Legacy Region"
        assert region.source_name == "Manual Region Source"
        assert region.source_metadata == manual_region_metadata
        assert city.source_name == document["geography_source"]["name"]
        assert city.source_metadata == {
            **document["geography_source"],
            "qid": f"Q{suffix}2",
            "url": f"https://www.wikidata.org/wiki/Q{suffix}2",
        }
        assert imported.source_metadata == {
            "source": document["source"],
            "geography_source": document["geography_source"],
        }
        assert len(db.scalars(select(CatalogImport).where(CatalogImport.checksum == backfilled["checksum"])).all()) == 1

        repeated = import_catalog(db, path)
        assert repeated["status"] == "unchanged"
        assert len(db.scalars(select(CatalogImport).where(CatalogImport.checksum == repeated["checksum"])).all()) == 1
