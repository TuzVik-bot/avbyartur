from pathlib import Path
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import import_catalog_packs_07 as importer


def test_new_pack_categories_accept_their_source_category_sets():
    assert {"07.23", "07.24", "07.27"}.issubset(importer.PACKS)
    assert set(importer.PACKS["07.23"]["source_categories"]) == {"atv_utv", "motorcycle"}
    assert set(importer.PACKS["07.24"]["source_categories"]) == {"boat_motorboat"}
    assert set(importer.PACKS["07.27"]["source_categories"]) == {
        "atv_utility", "atv_youth", "atv_electric", "atv_sport", "atv_utv"
    }


def test_only_the_three_unconfirmed_denago_models_are_withheld_from_public_names():
    hold = getattr(importer, "model_publication_hold", None)
    assert callable(hold)

    expected_models = {
        "atv_utility|DENAGO|FREELANDER200FI": "Freelander 200FI",
        "atv_utility|DENAGO|FREELANDER350FI4X4": "Freelander 350FI 4x4",
        "atv_utility|DENAGO|FREELANDER500FI4X4": "Freelander 500FI 4x4",
    }
    for model_key, model in expected_models.items():
        decision = hold("07.27", {"brand": "Denago", "model": model, "model_key": model_key})
        assert decision["status"] == "private_review_only"
        assert decision["source_url"] == "https://denagopowersports.com/pages/faq-denago-powersports"

    assert hold("07.23", {"brand": "Denago", "model_key": "atv_utility|DENAGO|FREELANDER200FI"}) is None
    assert hold("07.27", {"brand": "Denago", "model_key": "atv_utility|DENAGO|MUDHAWK200FI"}) is None
    with pytest.raises(ValueError, match="reserved publication hold"):
        hold("07.27", {
            "brand": "Apollo Motors",
            "model": "Freelander 200FI",
            "model_key": "atv_utility|DENAGO|FREELANDER200FI",
        })
