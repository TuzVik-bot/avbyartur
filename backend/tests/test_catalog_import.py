import copy
import json
import uuid
from pathlib import Path

from app.api.catalog import makes as search_makes
from app.api.catalog import models as search_models
from app.catalog_import import _aliases, import_catalog, validate_document
from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
)
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "data/catalog.json"
CATALOG_COVERAGE_PATH = ROOT / "data/catalog-coverage.json"
PASSAT_RANGES = {
    "Passat B1": (1973, 1980),
    "Passat B2": (1980, 1988),
    "Passat B3": (1988, 1993),
    "Passat B4": (1993, 1997),
    "Passat B5": (1996, 2005),
    "Passat B6": (2005, 2010),
    "Passat B7": (2010, 2015),
    "Passat B8": (2014, 2023),
    "Passat B9": (2024, None),
}
BMW_3_SERIES_SOURCE_URL = (
    "https://www.press.bmwgroup.com/canada/article/detail/T0454453EN/"
    "50-years-of-bmw-3-series-production-%20-an-international-success-story?language=en"
)
BMW_3_SERIES_RANGES_AND_SOURCES = {
    "1st generation": (1975, 1983, BMW_3_SERIES_SOURCE_URL),
    "2nd generation": (1982, 1994, BMW_3_SERIES_SOURCE_URL),
    "3rd generation": (1990, 2000, BMW_3_SERIES_SOURCE_URL),
    "4th generation": (1997, 2006, BMW_3_SERIES_SOURCE_URL),
    "5th generation": (2004, 2013, BMW_3_SERIES_SOURCE_URL),
    "6th generation": (2011, 2021, BMW_3_SERIES_SOURCE_URL),
    "7th generation": (2018, None, BMW_3_SERIES_SOURCE_URL),
}
BMW_3_SERIES_BODY_VARIANTS = {
    "1st generation": ("Sedan",),
    "2nd generation": ("Sedan", "Convertible", "Touring", "Coupé"),
    "3rd generation": ("Sedan", "Coupé", "Convertible", "Touring", "Compact"),
    "4th generation": ("Sedan", "Coupé", "Convertible", "Touring", "Compact"),
    "5th generation": ("Sedan", "Coupé", "Convertible", "Touring"),
    "6th generation": ("Sedan", "Touring", "Gran Turismo"),
    "7th generation": ("Sedan", "Touring"),
}
PASSAT_RANGES_AND_SOURCES = {
    "Passat B1": (1973, 1980, "https://www.volkswagen-newsroom.com/en/passat-b1-19731980-19534"),
    "Passat B2": (1980, 1988, "https://www.volkswagen-newsroom.com/de/passat-b2-19801988-19537"),
    "Passat B3": (1988, 1993, "https://www.volkswagen-newsroom.com/en/passat-b3-19881993-19540"),
    "Passat B4": (1993, 1997, "https://www.volkswagen-newsroom.com/de/passat-b4-19931997-19543"),
    "Passat B5": (1996, 2005, "https://www.volkswagen-newsroom.com/de/passat-b5-19962005-19546"),
    "Passat B6": (2005, 2010, "https://www.volkswagen-newsroom.com/de/passat-b6-20052010-19549"),
    "Passat B7": (2010, 2015, "https://www.volkswagen-newsroom.com/en/passat-b7-20102014-20036"),
    "Passat B8": (2014, 2023, "https://www.volkswagen.de/de/besitzer-und-service/ueber-ihr-auto/vorgaengermodelle/mittelklasse/passat-b8.html"),
    "Passat B9": (2024, None, "https://www.volkswagen-newsroom.com/en/press-releases/configurator-open-pre-sales-of-the-all-new-passat-have-now-started-17924"),
}


def load_passat_family() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    volkswagen = next(make for make in catalog["makes"] if make["slug"] == "volkswagen")
    return copy.deepcopy(next(
        model for model in volkswagen["models"]
        if model["slug"] == "volkswagen-passat-family"
    ))


def test_checked_in_catalog_coverage_counts_match_seed():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    coverage = json.loads(CATALOG_COVERAGE_PATH.read_text(encoding="utf-8"))
    counts = validate_document(catalog)

    catalog_counts = {make["name"]: len(make["models"]) for make in catalog["makes"]}
    reported_counts = {
        make["name"]: make["models_in_seed"] for make in coverage["makes"]
    }

    assert reported_counts == catalog_counts
    assert sum(reported_counts.values()) == coverage["counts"]["models_in_seed"]
    assert coverage["counts"]["models_in_seed"] == counts["models"]


def test_generation_coverage_keeps_unknown_ends_unverified():
    coverage = json.loads(CATALOG_COVERAGE_PATH.read_text(encoding="utf-8"))
    controls = {item["requested"]: item for item in coverage["control_models"]}

    assert coverage["counts"]["generations"] == 16
    assert coverage["plan_acceptance"]["generation_rows_present"] == 16
    assert coverage["plan_acceptance"]["generation_depth_verified"] is False
    assert controls["BMW 3 Series"]["generation_count"] == 7
    assert controls["BMW 3 Series"]["generation_depth_verified"] is False
    assert controls["Volkswagen Passat"]["generation_count"] == 9
    assert controls["Volkswagen Passat"]["generation_depth_verified"] is False


def test_body_type_and_bmw_variant_coverage_matches_the_checked_in_catalog():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    coverage = json.loads(CATALOG_COVERAGE_PATH.read_text(encoding="utf-8"))
    counts = validate_document(catalog)
    bmw = next(make for make in catalog["makes"] if make["slug"] == "bmw")
    family = next(model for model in bmw["models"] if model["slug"] == "bmw-3-series-family")

    actual_variants = {
        generation["name"]: tuple(
            variant["name"] for variant in generation.get("body_variants", [])
        )
        for generation in family["generations"]
    }
    body_types = {item["qid"]: item for item in catalog["body_types"]}

    assert set(body_types) == {"Q190578", "Q188886", "Q216762", "Q213853", "Q55989", "Q192152", "Q223189", "Q1580019"}
    assert all(item["source"]["name"] == "Wikidata" for item in body_types.values())
    assert all(item["source"]["qid"] == item["qid"] for item in body_types.values())
    assert all(item["source"]["retrieved_at"].endswith("Z") for item in body_types.values())
    assert actual_variants == BMW_3_SERIES_BODY_VARIANTS
    assert all(
        variant["source"]["name"] == "BMW Group PressClub"
        and variant["source"]["url"] == BMW_3_SERIES_SOURCE_URL
        and variant["source"]["retrieved_at"].endswith("Z")
        for generation in family["generations"]
        for variant in generation["body_variants"]
    )
    assert counts["body_types"] == coverage["counts"]["body_types"] == 8
    assert counts["body_variants"] == coverage["counts"]["body_variants"] == 24
    assert coverage["plan_acceptance"]["status"] == "unverified"
    assert coverage["plan_acceptance"]["generation_depth_verified"] is False
    evidence = {item["requested"]: item["generation_evidence"] for item in coverage["control_models"] if "generation_evidence" in item}
    assert set(evidence) == {"Belgee X50", "Belgee X70", "Geely Coolray", "BYD Atto 3", "Zeekr 001"}
    assert all(item["status"] == "insufficient" for item in evidence.values())


def test_bmw_search_aliases_survive_catalog_import_and_match_search_queries():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    bmw = next(make for make in catalog["makes"] if make["slug"] == "bmw")
    family = next(model for model in bmw["models"] if model["slug"] == "bmw-3-series-family")

    assert validate_document(catalog)["models"] == 253
    assert "БМВ" in _aliases(bmw)
    assert {"3 серия", "3er"}.issubset(_aliases(family))

    class EmptyRows:
        def all(self):
            return []

    class CapturingSession:
        def scalars(self, query):
            self.query = query
            return EmptyRows()

    make_db = CapturingSession()
    model_db = CapturingSession()
    assert search_makes(make_db, q="БМВ") == {"items": []}
    assert search_models(model_db, make_id=None, q="3 серия") == {"items": []}
    make_sql = str(make_db.query.compile(compile_kwargs={"literal_binds": True}))
    model_sql = str(model_db.query.compile(compile_kwargs={"literal_binds": True}))
    assert "aliases" in make_sql and "БМВ" in make_sql
    assert "aliases" in model_sql and "3 серия" in model_sql


def test_checked_in_bmw_3_series_ranges_match_exact_sources():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    bmw = next(make for make in catalog["makes"] if make["slug"] == "bmw")
    family = next(
        model for model in bmw["models"]
        if model["slug"] == "bmw-3-series-family"
    )

    assert len(family["generations"]) == len(BMW_3_SERIES_RANGES_AND_SOURCES)
    actual = {
        item["name"]: (
            item["year_from"],
            item["year_to"],
            item["source"]["url"],
        )
        for item in family["generations"]
    }
    assert actual == BMW_3_SERIES_RANGES_AND_SOURCES
    assert all(item["source"]["name"] == "BMW Group PressClub" for item in family["generations"])


def test_checked_in_passat_ranges_are_valid_import_input():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    counts = validate_document(catalog)

    assert counts["models"] == 253
    assert counts["generations"] == 16
    family = load_passat_family()
    assert len(family["generations"]) == len(PASSAT_RANGES_AND_SOURCES)
    actual = {
        item["name"]: (
            item["year_from"],
            item["year_to"],
            item["source"]["url"],
        )
        for item in family["generations"]
    }
    assert actual == PASSAT_RANGES_AND_SOURCES
    assert {
        name: (year_from, year_to)
        for name, (year_from, year_to, _url) in actual.items()
    } == PASSAT_RANGES


def test_import_persists_passat_family_generation_ranges(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    source_name = f"Passat import test {suffix}"
    make_slug = f"passat-import-test-{suffix}"
    document = {
        "schema_version": 1,
        "source": {"name": source_name, "license": "Test fixture"},
        "makes": [{
            "name": "Volkswagen test fixture",
            "slug": make_slug,
            "aliases": [],
            "models": [load_passat_family()],
        }],
        "body_types": [],
        "regions": [],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with integration["SessionLocal"]() as db:
        result = import_catalog(db, path)
        make = db.scalar(select(CatalogMake).where(CatalogMake.slug == make_slug))
        assert result["status"] == "imported"
        assert result["counts"]["generations"] == 9
        assert make is not None
        model = db.scalar(select(CatalogModel).where(
            CatalogModel.make_id == make.id,
            CatalogModel.slug == "volkswagen-passat-family",
        ))
        assert model is not None
        generations = db.scalars(select(CatalogGeneration).where(
            CatalogGeneration.model_id == model.id,
        )).all()
        assert {item.name: (item.year_from, item.year_to) for item in generations} == PASSAT_RANGES
        expected_sources = {
            item["name"]: item["source"]
            for item in load_passat_family()["generations"]
        }
        assert all(item.source_name == expected_sources[item.name]["name"] for item in generations)
        assert all(item.source_metadata == expected_sources[item.name] for item in generations)


def test_reimport_updates_source_metadata_and_preserves_manual_variant_override(integration, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    generation_slug = f"generation-{suffix}"
    variant_slug = f"sedan-{suffix}"
    body_type_slug = f"sedan-{suffix}"
    generation_source = {
        "name": "BMW Group PressClub",
        "url": BMW_3_SERIES_SOURCE_URL,
        "retrieved_at": "2026-09-27T10:07:32Z",
    }
    body_type_source = {
        "name": "Wikidata",
        "qid": f"QBODY{suffix}",
        "url": f"https://www.wikidata.org/wiki/QBODY{suffix}",
        "retrieved_at": "2026-09-27T10:07:32Z",
    }
    document = {
        "schema_version": 1,
        "source": {"name": f"Catalog fixture {suffix}", "license": "Test fixture"},
        "makes": [{
            "name": "BMW fixture",
            "slug": f"bmw-fixture-{suffix}",
            "source": {"name": "manual"},
            "models": [{
                "name": "3 Series fixture",
                "slug": f"3-series-fixture-{suffix}",
                "source": {"name": "manual"},
                "generations": [{
                    "name": "7th generation",
                    "slug": generation_slug,
                    "year_from": 2018,
                    "year_to": None,
                    "source": generation_source,
                    "body_variants": [{
                        "name": "Sedan",
                        "slug": variant_slug,
                        "source": generation_source,
                    }],
                }],
            }],
        }],
        "body_types": [{
            "qid": f"QBODY{suffix}",
            "name": "Sedan",
            "slug": body_type_slug,
            "source": body_type_source,
        }],
        "regions": [],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    with integration["SessionLocal"]() as db:
        first = import_catalog(db, path)
        assert first["status"] == "imported"
        repeated = import_catalog(db, path)
        assert repeated["status"] == "unchanged"
        make = db.scalar(select(CatalogMake).where(CatalogMake.slug == f"bmw-fixture-{suffix}"))
        model = db.scalar(select(CatalogModel).where(
            CatalogModel.make_id == make.id,
            CatalogModel.slug == f"3-series-fixture-{suffix}",
        ))
        generation = db.scalar(select(CatalogGeneration).where(
            CatalogGeneration.model_id == model.id,
            CatalogGeneration.slug == generation_slug,
        ))
        variant = db.scalar(select(CatalogBodyVariant).where(
            CatalogBodyVariant.generation_id == generation.id,
            CatalogBodyVariant.slug == variant_slug,
        ))
        body_type = db.scalar(select(CatalogBodyType).where(CatalogBodyType.slug == body_type_slug))
        assert variant.source_name == "BMW Group PressClub"
        assert variant.source_metadata == generation_source
        assert body_type.source_name == "Wikidata"
        assert body_type.source_metadata == body_type_source

        manual_source = {"name": "manual", "reviewed_by": "fixture"}
        variant.manual_override = True
        variant.name = "Manually corrected sedan"
        variant.source_name = "manual"
        variant.source_metadata = manual_source
        db.commit()

        updated = copy.deepcopy(document)
        updated["source"]["retrieved_at"] = "2026-09-28T00:00:00Z"
        updated["makes"][0]["models"][0]["generations"][0]["body_variants"][0].update({
            "name": "Refreshed sedan",
            "source": {
                "name": "BMW Group PressClub",
                "url": BMW_3_SERIES_SOURCE_URL,
                "retrieved_at": "2026-09-28T00:00:00Z",
            },
        })
        updated["body_types"][0].update({
            "name": "Updated sedan",
            "source": {**body_type_source, "retrieved_at": "2026-09-28T00:00:00Z"},
        })
        path.write_text(json.dumps(updated, ensure_ascii=False), encoding="utf-8")
        refreshed = import_catalog(db, path)
        assert refreshed["status"] == "imported"
        db.expire_all()

        variant = db.scalar(select(CatalogBodyVariant).where(
            CatalogBodyVariant.generation_id == generation.id,
            CatalogBodyVariant.slug == variant_slug,
        ))
        body_type = db.scalar(select(CatalogBodyType).where(CatalogBodyType.slug == body_type_slug))
        assert variant.name == "Manually corrected sedan"
        assert variant.source_name == "manual"
        assert variant.source_metadata == manual_source
        assert body_type.name == "Updated sedan"
        assert body_type.source_metadata["retrieved_at"] == "2026-09-28T00:00:00Z"
