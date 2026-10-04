import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import refresh_wikidata_catalog as catalog


def entity_uri(qid: str) -> str:
    return f"http://www.wikidata.org/entity/{qid}"


def row(make_qid: str, make_name: str, *, model_qid: str | None = None,
        model_name: str | None = None, brand_qid: str | None = None) -> dict:
    result = {
        "make": {"value": entity_uri(make_qid)},
        "makeLabel": {"xml:lang": "en", "value": make_name},
    }
    if make_qid != "Q17324842":
        result["makeBrand"] = {"value": entity_uri(make_qid)}
    if model_qid and model_name:
        result.update(
            {
                "model": {"value": entity_uri(model_qid)},
                "modelLabel": {"xml:lang": "en", "value": model_name},
                "brand": {"value": entity_uri(brand_qid or make_qid)},
            }
        )
    return result


class WikidataCatalogTests(unittest.TestCase):
    def test_query_requires_brand_entity_and_direct_brand_relation(self):
        query = catalog.make_query()
        self.assertIn("wd:Q431289", query)
        self.assertIn("wdt:P1716 ?brand", query)
        self.assertIn("FILTER (?brand = ?make)", query)
        self.assertNotIn("wdt:P176", query)

    def test_parent_manufacturer_matches_do_not_become_make_models(self):
        rows = [row(qid, name) for qid, name in catalog.MAKES]
        rows.extend(
            [
                row("Q53268", "Toyota", model_qid="QTEST1", model_name="Toyota Corolla"),
                row("Q53268", "Toyota", model_qid="QTEST2", model_name="Toyota Cavalier", brand_qid="Q29570"),
                row("Q53268", "Toyota", model_qid="QTEST3", model_name="Daihatsu Terios", brand_qid="Q27511"),
                row("Q6742", "Peugeot", model_qid="QTEST4", model_name="Citroën C3", brand_qid="Q6746"),
            ]
        )

        records, _ = catalog.collect(rows)
        models_by_make = {item["qid"]: item["models"] for item in records}
        self.assertEqual(set(models_by_make["Q53268"]), {"QTEST1"})
        self.assertEqual(models_by_make["Q6742"], {})

    def test_control_model_presence_does_not_claim_generation_depth(self):
        rows = [row(qid, name) for qid, name in catalog.MAKES]
        make_qids = {name: qid for qid, name in catalog.MAKES}
        rows.append(row(make_qids["BMW"], "BMW", model_qid="QBMW3", model_name="BMW 3 Series"))
        rows.append(row(make_qids["Volkswagen"], "Volkswagen", model_qid="QPASSAT", model_name="Volkswagen Passat B7"))
        records, _ = catalog.collect(rows)

        _, coverage = catalog.build_catalog(records, "2026-09-27T00:00:00Z", 12)
        controls = {item["requested"]: item for item in coverage["control_models"]}
        self.assertTrue(controls["BMW 3 Series"]["model_present_in_seed"])
        self.assertTrue(controls["Volkswagen Passat"]["model_present_in_seed"])
        self.assertEqual(controls["BMW 3 Series"]["generation_count"], 0)
        self.assertFalse(controls["BMW 3 Series"]["generation_depth_verified"])
        self.assertEqual(coverage["plan_acceptance"]["status"], "unverified")
        self.assertFalse(coverage["row_count_threshold_met"])

    def test_bmw_uses_brand_entity_and_accepts_language_neutral_label(self):
        bmw_qid = dict((name, qid) for qid, name in catalog.MAKES)["BMW"]
        self.assertEqual(bmw_qid, "Q796364")
        self.assertIn('FILTER (LANG(?makeLabel) IN ("ru", "en", "mul"))', catalog.make_query())

    def test_refresh_builds_the_bmw_make_search_alias(self):
        records, _ = catalog.collect([row(qid, name) for qid, name in catalog.MAKES])

        generated, _ = catalog.build_catalog(records, "2026-09-27T00:00:00Z", 12)

        bmw = next(make for make in generated["makes"] if make["slug"] == "bmw")
        self.assertIn("БМВ", bmw["aliases"])

    def test_refresh_preserves_geography_source_and_regions(self):
        geography_source = {
            "name": "Wikidata",
            "license": "CC0 1.0",
            "query_sha256": "geography-query-hash",
        }
        regions = [{"qid": "Q173822", "name": "Брестская область", "cities": []}]
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata", "retrieved_at": "old"},
            "geography_source": geography_source,
            "makes": [],
            "body_types": [],
            "regions": regions,
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata", "retrieved_at": "new"},
            "makes": [],
            "body_types": [],
            "regions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            merged = catalog.merge_existing_catalog(path, generated)

        self.assertEqual(merged["regions"], regions)
        self.assertEqual(merged["geography_source"], geography_source)
        self.assertEqual(merged["source"]["retrieved_at"], "new")

    def test_refresh_preserves_generation_rows_and_manual_overrides(self):
        previous_generations = [
            {
                "qid": "QGEN1",
                "name": "Generation omitted by refresh",
                "slug": "generation-1",
                "source": {"name": "Wikidata", "qid": "QGEN1"},
            },
            {
                "qid": "QGEN2",
                "name": "Manual generation name",
                "slug": "manual-generation",
                "source": {"name": "manual"},
            },
            {
                "qid": "QGEN3",
                "name": "Old sourced name",
                "slug": "generation-3-old",
                "source": {"name": "Wikidata", "qid": "QGEN3"},
            },
        ]
        previous_model = {
            "qid": "QMODEL",
            "name": "Model",
            "slug": "model",
            "source": {
                "name": "Wikidata",
                "qid": "QMODEL",
                "brand_property": "P1716",
                "brand_qid": "QMAKE",
            },
            "generations": previous_generations,
        }
        generated_model = {
            **previous_model,
            "generations": [
                {
                    "qid": "QGEN2",
                    "name": "Generated name that must not replace manual data",
                    "slug": "generated-generation-2",
                    "source": {"name": "Wikidata", "qid": "QGEN2"},
                },
                {
                    "qid": "QGEN3",
                    "name": "Refreshed sourced name",
                    "slug": "generation-3-new",
                    "source": {"name": "Wikidata", "qid": "QGEN3"},
                },
            ],
        }
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [previous_model],
            }],
            "body_types": [],
            "regions": [],
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [generated_model],
            }],
            "body_types": [],
            "regions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            merged = catalog.merge_existing_catalog(path, generated)

        generations = merged["makes"][0]["models"][0]["generations"]
        by_qid = {generation["qid"]: generation for generation in generations}
        self.assertEqual(by_qid["QGEN1"], previous_generations[0])
        self.assertEqual(by_qid["QGEN2"], previous_generations[1])
        self.assertEqual(by_qid["QGEN3"]["name"], "Refreshed sourced name")

    def test_refresh_preserves_manual_model_override(self):
        manual_model = {
            "qid": "QMODEL",
            "name": "Manual model name",
            "slug": "manual-model",
            "source": {"name": "manual"},
            "generations": [],
        }
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [manual_model],
            }],
            "body_types": [],
            "regions": [],
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [{
                    **manual_model,
                    "name": "Generated model name",
                    "source": {
                        "name": "Wikidata",
                        "brand_property": "P1716",
                        "brand_qid": "QMAKE",
                    },
                }],
            }],
            "body_types": [],
            "regions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            merged = catalog.merge_existing_catalog(path, generated)

        self.assertEqual(merged["makes"][0]["models"][0], manual_model)

    def test_refresh_keeps_omitted_model_that_contains_generations(self):
        sourced_model = {
            "qid": "QMODEL",
            "name": "Model outside refreshed cap",
            "slug": "model-outside-cap",
            "source": {
                "name": "Wikidata",
                "qid": "QMODEL",
                "brand_property": "P1716",
                "brand_qid": "QMAKE",
            },
            "generations": [{
                "qid": "QGEN1",
                "name": "Saved generation",
                "slug": "saved-generation",
                "source": {"name": "Wikidata", "qid": "QGEN1"},
            }],
        }
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [sourced_model],
            }],
            "body_types": [],
            "regions": [],
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [],
            }],
            "body_types": [],
            "regions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            merged = catalog.merge_existing_catalog(path, generated)

        self.assertEqual(merged["makes"][0]["models"], [sourced_model])

    def test_control_generation_counts_reflect_merged_catalog(self):
        coverage = {
            "control_models": [{
                "matching_model_qid": "QMODEL",
                "generation_count": 0,
                "generation_depth_verified": False,
            }]
        }
        catalog_document = {
            "makes": [{
                "models": [{
                    "qid": "QMODEL",
                    "generations": [{"qid": "QGEN1"}, {"qid": "QGEN2"}],
                }]
            }]
        }

        catalog.update_control_generation_counts(coverage, catalog_document)

        self.assertEqual(coverage["control_models"][0]["generation_count"], 2)
        self.assertFalse(coverage["control_models"][0]["generation_depth_verified"])

    def test_refresh_counts_manual_control_model_by_slug_without_qid(self):
        manual_model = {
            "name": "BMW 3 Series family",
            "slug": "bmw-3-series-family",
            "source": {"name": "manual"},
            "generations": [
                {"slug": "generation-one"},
                {"slug": "generation-two"},
            ],
        }
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [manual_model],
            }],
            "body_types": [],
            "regions": [],
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [],
            }],
            "body_types": [],
            "regions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            merged = catalog.merge_existing_catalog(path, generated)

        previous_coverage = {
            "control_models": [{
                "matching_model_qid": None,
                "matching_model_slug": "bmw-3-series-family",
                "requested": "BMW 3 Series",
                "model_present_in_seed": True,
                "generation_count": 0,
                "generation_depth_verified": False,
            }]
        }
        coverage = {
            "control_models": [{
                "matching_model_qid": "QREFRESHED",
                "matching_model_slug": "bmw-3-series",
                "requested": "BMW 3 Series",
                "model_present_in_seed": True,
                "generation_count": 0,
                "generation_depth_verified": False,
            }]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "coverage.json"
            path.write_text(json.dumps(previous_coverage), encoding="utf-8")
            catalog.preserve_existing_control_slugs(path, coverage, merged)
        catalog.update_control_generation_counts(coverage, merged)

        self.assertEqual(merged["makes"][0]["models"], [manual_model])
        self.assertEqual(len(merged["makes"][0]["models"]), 1)
        self.assertIsNone(coverage["control_models"][0]["matching_model_qid"])
        self.assertEqual(coverage["control_models"][0]["matching_model_slug"], "bmw-3-series-family")
        self.assertEqual(coverage["control_models"][0]["generation_count"], 2)
        self.assertFalse(coverage["control_models"][0]["generation_depth_verified"])

    def test_refresh_preserves_passat_family_control_slug_and_generations(self):
        root = Path(__file__).resolve().parents[1]
        checked_in = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
        volkswagen = next(make for make in checked_in["makes"] if make["slug"] == "volkswagen")
        family = next(model for model in volkswagen["models"] if model["slug"] == "volkswagen-passat-family")
        generated_passat = {
            "qid": "Q1543320",
            "name": "Volkswagen Passat (B1)",
            "slug": "volkswagen-passat-b1",
            "source": {
                "name": "Wikidata",
                "qid": "Q1543320",
                "brand_property": "P1716",
                "brand_qid": "Q246",
            },
            "generations": [],
        }
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{"qid": "Q246", "name": "Volkswagen", "slug": "volkswagen", "source": {"name": "Wikidata"}, "models": [family]}],
            "body_types": [],
            "regions": [],
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{"qid": "Q246", "name": "Volkswagen", "slug": "volkswagen", "source": {"name": "Wikidata"}, "models": [generated_passat]}],
            "body_types": [],
            "regions": [],
        }
        previous_coverage = {
            "control_models": [{
                "requested": "Volkswagen Passat",
                "matching_model_qid": None,
                "matching_model_slug": "volkswagen-passat-family",
                "model_present_in_seed": True,
                "generation_count": 9,
                "generation_depth_verified": False,
            }]
        }
        coverage = {
            "control_models": [{
                "requested": "Volkswagen Passat",
                "matching_model_qid": "Q1543320",
                "matching_model_slug": "volkswagen-passat-b1",
                "model_present_in_seed": True,
                "generation_count": 0,
                "generation_depth_verified": False,
            }]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            catalog_path = temp / "catalog.json"
            coverage_path = temp / "coverage.json"
            catalog_path.write_text(json.dumps(previous), encoding="utf-8")
            coverage_path.write_text(json.dumps(previous_coverage), encoding="utf-8")
            merged = catalog.merge_existing_catalog(catalog_path, generated)
            catalog.preserve_existing_control_slugs(coverage_path, coverage, merged)
        catalog.update_control_generation_counts(coverage, merged)

        family_after_refresh = next(
            model for model in merged["makes"][0]["models"]
            if model.get("slug") == "volkswagen-passat-family"
        )
        self.assertEqual(family_after_refresh, family)
        self.assertIsNone(coverage["control_models"][0]["matching_model_qid"])
        self.assertEqual(coverage["control_models"][0]["matching_model_slug"], "volkswagen-passat-family")
        self.assertEqual(coverage["control_models"][0]["generation_count"], 9)
        self.assertFalse(coverage["control_models"][0]["generation_depth_verified"])

    def test_refresh_updates_sourced_body_types_and_keeps_manual_records(self):
        manual_type = {
            "qid": "QMANUAL",
            "name": "Manual body type",
            "slug": "manual-body-type",
            "source": {"name": "manual"},
        }
        manual_variant = {
            "name": "Manual Touring name",
            "slug": "manual-touring",
            "source": {"name": "BMW Group PressClub", "url": "https://example.test/bmw"},
        }
        previous = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [{
                    "qid": "QMODEL",
                    "name": "Model",
                    "slug": "model",
                    "source": {"name": "Wikidata", "brand_property": "P1716", "brand_qid": "QMAKE"},
                    "generations": [{
                        "qid": "QGEN",
                        "name": "Generation",
                        "slug": "generation",
                        "source": {"name": "Wikidata", "qid": "QGEN"},
                        "body_variants": [manual_variant, {
                            "qid": "QVARIANT",
                            "name": "Old sourced label",
                            "slug": "sourced-variant",
                            "source": {"name": "Wikidata", "qid": "QVARIANT"},
                        }],
                    }],
                }],
            }],
            "body_types": [{
                "qid": "Q190578",
                "name": "Old sourced label",
                "slug": "sedan",
                "source": {"name": "Wikidata", "qid": "Q190578"},
            }, manual_type],
            "regions": [],
        }
        generated = {
            "schema_version": 1,
            "source": {"name": "Wikidata"},
            "makes": [{
                "qid": "QMAKE",
                "name": "Make",
                "slug": "make",
                "source": {"name": "Wikidata"},
                "models": [{
                    "qid": "QMODEL",
                    "name": "Model",
                    "slug": "model",
                    "source": {"name": "Wikidata", "brand_property": "P1716", "brand_qid": "QMAKE"},
                    "generations": [{
                        "qid": "QGEN",
                        "name": "Generation",
                        "slug": "generation",
                        "source": {"name": "Wikidata", "qid": "QGEN"},
                        "body_variants": [{
                            "qid": "QVARIANT",
                            "name": "Refreshed sourced label",
                            "slug": "sourced-variant",
                            "source": {"name": "Wikidata", "qid": "QVARIANT"},
                        }, {
                            "qid": "QVARIANT2",
                            "name": "New sourced variant",
                            "slug": "new-variant",
                            "source": {"name": "Wikidata", "qid": "QVARIANT2"},
                        }],
                    }],
                }],
            }],
            "body_types": [{
                "qid": "Q190578",
                "name": "Refreshed sedan",
                "slug": "sedan",
                "source": {"name": "Wikidata", "qid": "Q190578"},
            }, {
                "qid": "Q188886",
                "name": "Station wagon",
                "slug": "station-wagon",
                "source": {"name": "Wikidata", "qid": "Q188886"},
            }],
            "regions": [],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps(previous), encoding="utf-8")
            merged = catalog.merge_existing_catalog(path, generated)

        body_types = {row["qid"]: row for row in merged["body_types"]}
        self.assertEqual(body_types["Q190578"]["name"], "Refreshed sedan")
        self.assertIn("Q188886", body_types)
        self.assertEqual(body_types["QMANUAL"], manual_type)
        variants = merged["makes"][0]["models"][0]["generations"][0]["body_variants"]
        variants_by_key = {catalog.record_key(row): row for row in variants}
        self.assertEqual(variants_by_key["manual-touring"], manual_variant)
        self.assertEqual(variants_by_key["QVARIANT"]["name"], "Refreshed sourced label")
        self.assertIn("QVARIANT2", variants_by_key)


if __name__ == "__main__":
    unittest.main()
