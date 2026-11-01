import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.onliner_catalog_plan import reconcile


def source(name="Jaguar", slug="jaguar", models=None):
    return {"format": "onliner-catalog-v1", "makes": [{"id": 30, "name": name, "slug": slug, "models": models if models is not None else [{"id": 7, "name": "XF", "slug": "xf"}]}]}


class CatalogPlanTests(unittest.TestCase):
    def test_add_missing_make_and_model(self):
        plan = reconcile(source(), {"makes": []})
        self.assertEqual([m["name"] for m in plan["makes"]], ["Jaguar"])
        self.assertEqual(plan["models"][0]["make_slug"], "jaguar")
        self.assertEqual(plan["coverage"][0]["models"][0]["target_slug"], "xf")

    def test_existing_unicode_alias_and_make_prefix_preserved(self):
        before = {"makes": [{"id": "m1", "slug": "skoda", "name": "Škoda", "aliases": [], "models": [{"id": "o1", "slug": "skoda-octavia", "name": "Škoda Octavia", "aliases": []}]}]}
        plan = reconcile(source("Skoda", "skoda", [{"id": 7, "name": "Octavia", "slug": "octavia"}]), before)
        self.assertEqual(plan["makes"], [])
        self.assertEqual(plan["models"], [])
        self.assertEqual(plan["coverage"][0]["models"][0]["target_slug"], "skoda-octavia")

    def test_vaz_matches_lada_and_replay_is_empty(self):
        before = {"makes": [{"id": "m1", "slug": "lada", "name": "Lada", "aliases": [], "models": [{"id": "o1", "slug": "vesta", "name": "Vesta", "aliases": []}]}]}
        plan = reconcile(source("ВАЗ", "vaz", [{"id": 7, "name": "Vesta", "slug": "vesta"}]), before)
        self.assertEqual(plan["makes"], [])
        self.assertEqual(plan["models"], [])
        self.assertEqual(plan["aliases"], [{"make_slug": "lada", "alias": "ВАЗ"}])

    def test_name_equivalent_existing_rows_do_not_create_third_duplicate(self):
        before = {"makes": [{"id": "m1", "slug": "jaguar", "name": "Jaguar", "models": [{"id": "o1", "slug": "xf-1", "name": "XF"}, {"id": "o2", "slug": "xf-2", "name": "Jaguar XF"}]}]}
        plan = reconcile(source(), before)
        self.assertEqual(plan["models"], [])
        self.assertEqual(len(plan["equivalent_models"]), 1)

    def test_slug_collision_with_different_name_is_rejected(self):
        before = {"makes": [{"id": "m1", "slug": "jaguar", "name": "Jaguar", "models": [{"id": "o1", "slug": "xf", "name": "XJ"}]}]}
        with self.assertRaisesRegex(ValueError, "conflict"):
            reconcile(source(), before)

    def test_invalid_and_duplicate_source_identity_rejected(self):
        for models in ([{"id": 7, "name": "", "slug": "xf"}], [{"id": 7, "name": "XF", "slug": "xf"}] * 2):
            with self.assertRaises(ValueError):
                reconcile(source(models=models), {"makes": []})

    def test_ambiguous_make_is_rejected(self):
        before = {"makes": [{"id": "m1", "slug": "jaguar", "name": "Jaguar", "models": []}, {"id": "m2", "slug": "other", "name": "Other", "aliases": ["Jaguar"], "models": []}]}
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            reconcile(source(), before)

    def test_reviewed_source_display_variants_preserve_existing_identity(self):
        before = {"makes": [{"id": "m1", "slug": "chery", "name": "Chery", "models": [{"id": "o1", "slug": "amulet", "name": "Chery Amulet A15"}]}]}
        plan = reconcile(source("Chery", "chery", [{"id": 7, "name": "Amulet", "slug": "amulet"}]), before)
        self.assertEqual(plan["models"], [])

    def test_reconcile_does_not_mutate_baseline_and_second_run_is_empty(self):
        import copy
        before = {"makes": []}
        original = copy.deepcopy(before)
        plan = reconcile(source(), before)
        self.assertEqual(before, original)
        after = {"makes": [{**m, "models": [o for o in plan["models"] if o["make_slug"] == m["slug"]]} for m in plan["makes"]]}
        replay = reconcile(source(), after)
        self.assertEqual(replay["makes"], [])
        self.assertEqual(replay["models"], [])

    def test_plus_suffix_is_a_distinct_model(self):
        before = {"makes": [{"slug": "toyota", "name": "Toyota", "models": [{"slug": "c-hr_plus", "name": "C-HR+"}]}]}
        plan = reconcile(source("Toyota", "toyota", [{"id": 7, "name": "C-HR", "slug": "c-hr"}]), before)
        self.assertEqual(len(plan["models"]), 1)

    def test_two_source_make_aliases_share_pending_models(self):
        document = source("Lada", "lada", [{"id": 7, "name": "Niva", "slug": "niva"}])
        document["makes"].append({"id": 65, "name": "ВАЗ", "slug": "vaz", "models": [{"id": 8, "name": "Niva", "slug": "niva"}]})
        plan = reconcile(document, {"makes": []})
        self.assertEqual(len(plan["makes"]), 1)
        self.assertEqual(len(plan["models"]), 1)

    def test_existing_source_model_gets_missing_cars_category(self):
        before = {"makes": [{"slug": "jaguar", "name": "Jaguar", "models": [{"slug": "xf", "name": "XF", "source_metadata": {"category_codes": ["trucks"], "original": "preserve"}}]}]}
        plan = reconcile(source(), before)
        self.assertEqual(plan["categories"], [{"make_slug": "jaguar", "model_slug": "xf"}])
        self.assertEqual(before["makes"][0]["models"][0]["source_metadata"]["category_codes"], ["trucks"])
        before["makes"][0]["models"][0]["source_metadata"]["category_codes"].append("cars")
        self.assertEqual(reconcile(source(), before)["categories"], [])


if __name__ == "__main__":
    unittest.main()
