import uuid

import pytest

from app import models


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/catalog/makes",
        "/api/v1/catalog/models",
        "/api/v1/catalog/body-types",
        "/api/v1/locations/regions",
        f"/api/v1/locations/cities?region_id={uuid.UUID(int=7)}",
    ],
)
def test_reference_endpoints_are_publicly_cacheable(integration, path):
    response = integration["client"].get(path)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=300"


def test_reference_validation_errors_are_not_cached(integration):
    response = integration["client"].get("/api/v1/locations/cities", params={"region_id": "bad"})

    assert response.status_code == 422
    assert "max-age" not in response.headers.get("cache-control", "")


def test_catalog_text_filter_treats_wildcards_literally(integration):
    suffix = uuid.uuid4().hex[:8]
    with integration["SessionLocal"]() as db:
        db.add_all([
            models.CatalogMake(slug=f"plain-{suffix}", name=f"Plain {suffix}"),
            models.CatalogMake(slug=f"percent-{suffix}", name=f"Make 100%{suffix}"),
        ])
        db.commit()

    response = integration["client"].get("/api/v1/catalog/makes", params={"q": f"%{suffix}"})

    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()["items"]] == [f"Make 100%{suffix}"]
