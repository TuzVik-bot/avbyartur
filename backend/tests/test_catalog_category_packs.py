"""Category scoping of the catalog makes/models endpoints for imported packs."""

import uuid

import pytest

from app.api.catalog import CATEGORY_PACK_SOURCE_NAMES
from app.models import CatalogMake, CatalogModel


def _seed(factory) -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    ids: dict[str, str] = {}
    specs = {
        "car": (None, None),
        "pack01_truck": ("NHTSA vPIC catalog pack 01", ["trucks"]),
        "pack02_moto": ("Autorinok catalog pack 02", ["motorcycles"]),
        "pack03_boat": ("Autorinok catalog pack 03", ["watercraft"]),
        "pack04_agro": ("Autorinok catalog pack 04", ["agricultural_equipment"]),
        "pack05_special": ("Autorinok catalog pack 05", ["special_equipment"]),
        "other_source": ("Wikidata", None),
        "pack_no_codes": ("Autorinok catalog pack 02", None),
    }
    with factory() as db:
        for label, (source, codes) in specs.items():
            metadata = {"category_codes": codes} if codes else None
            make = CatalogMake(
                slug=f"{label}-{suffix}", name=f"{label} Make {suffix}", aliases=[],
                source_name=source, source_metadata=metadata,
            )
            db.add(make)
            db.flush()
            model = CatalogModel(
                make_id=make.id, slug=f"{label}-{suffix}", name=f"{label} Model {suffix}",
                aliases=[], source_name=source, source_metadata=metadata,
            )
            db.add(model)
            db.flush()
            ids[f"make:{label}"] = str(make.id)
            ids[f"model:{label}"] = str(model.id)
        db.commit()
    return ids


def _ids(response) -> set[str]:
    assert response.status_code == 200
    return {item["id"] for item in response.json()["items"]}


def test_pack_source_names_cover_packs_01_to_05():
    assert len(CATEGORY_PACK_SOURCE_NAMES) == 5


@pytest.mark.parametrize("kind", ["makes", "models"])
def test_cars_catalog_hides_pack_rows_and_is_the_default(integration, kind):
    ids = _seed(integration["SessionLocal"])
    client = integration["client"]
    default = _ids(client.get(f"/api/v1/catalog/{kind}"))
    explicit = _ids(client.get(f"/api/v1/catalog/{kind}", params={"category_code": "cars"}))
    prefix = kind[:-1]
    visible = {ids[f"{prefix}:car"], ids[f"{prefix}:other_source"]}
    hidden = {ids[key] for key in ids if key.startswith(f"{prefix}:") and key.split(":")[1] not in {"car", "other_source"}}
    assert default == explicit
    assert visible <= default
    assert not hidden & default


@pytest.mark.parametrize(
    ("category", "label"),
    [
        ("trucks", "pack01_truck"),
        ("motorcycles", "pack02_moto"),
        ("watercraft", "pack03_boat"),
        ("agricultural_equipment", "pack04_agro"),
        ("special_equipment", "pack05_special"),
    ],
)
def test_category_catalog_returns_only_rows_tagged_with_that_category(integration, category, label):
    ids = _seed(integration["SessionLocal"])
    client = integration["client"]
    params = {"category_code": category}
    makes = _ids(client.get("/api/v1/catalog/makes", params=params))
    models = _ids(client.get("/api/v1/catalog/models", params=params))
    assert {ids[f"make:{label}"]} <= makes
    assert {ids[f"model:{label}"]} <= models
    for other in ("car", "other_source", "pack_no_codes"):
        assert ids[f"make:{other}"] not in makes
        assert ids[f"model:{other}"] not in models


def test_category_models_respect_make_filter_and_empty_categories(integration):
    ids = _seed(integration["SessionLocal"])
    client = integration["client"]
    scoped = client.get("/api/v1/catalog/models", params={"category_code": "trucks", "make_id": ids["make:pack01_truck"]})
    assert _ids(scoped) == {ids["model:pack01_truck"]}
    wrong_category = client.get("/api/v1/catalog/models", params={"category_code": "buses", "make_id": ids["make:pack01_truck"]})
    assert _ids(wrong_category) == set()
    assert client.get("/api/v1/catalog/makes", params={"category_code": "bogus"}).status_code == 422
