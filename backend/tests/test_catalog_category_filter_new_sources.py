"""Unknown non-car pack names must not leak into the passenger catalog."""

import uuid

import pytest

from app.models import CatalogMake, CatalogModel


@pytest.mark.parametrize("kind,entity_key", [("makes", "make"), ("models", "model")])
def test_new_source_category_is_hidden_from_cars_and_visible_in_its_category(integration, kind, entity_key):
    suffix = uuid.uuid4().hex[:10]
    source_name = "Autorinok catalog pack 07.25"
    with integration["SessionLocal"]() as db:
        make = CatalogMake(
            slug=f"regression-brand-{suffix}",
            name=f"Regression Brand {suffix}",
            aliases=[],
            source_name=source_name,
            source_metadata={"category_codes": ["motorcycles"]},
        )
        db.add(make)
        db.flush()
        model = CatalogModel(
            make_id=make.id,
            slug=f"regression-model-{suffix}",
            name=f"Regression Model {suffix}",
            aliases=[],
            source_name=source_name,
            source_metadata={"category_codes": ["motorcycles"]},
        )
        db.add(model)
        db.commit()
        entity_id = str(make.id if entity_key == "make" else model.id)

    client = integration["client"]
    cars = client.get(f"/api/v1/catalog/{kind}", params={"q": suffix, "category_code": "cars"})
    motorcycles = client.get(f"/api/v1/catalog/{kind}", params={"q": suffix, "category_code": "motorcycles"})
    assert cars.status_code == 200
    assert motorcycles.status_code == 200
    assert entity_id not in {item["id"] for item in cars.json()["items"]}
    assert entity_id in {item["id"] for item in motorcycles.json()["items"]}
