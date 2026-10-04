"""Catalog edits must retain provenance, version history and stable URLs."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent, CatalogMake, CatalogModel, User
from app.security import hash_password

PASSWORD = "catalog-admin-test-password-123"


def setup(integration, role="admin"):
    factory = integration["SessionLocal"]
    user = User(email=f"catalog-admin-{uuid.uuid4().hex}@example.com", display_name="Редактор", password_hash=hash_password(PASSWORD), role=role, status="active")
    make = CatalogMake(slug="verified-make", name="Исходная марка", aliases=["Исходный вариант"], source_name="licensed", source_metadata={"source_url": "https://source.example/catalog/make", "permission_ref": "owner-license"})
    with factory() as db:
        db.add_all([user, make]); db.commit(); db.refresh(user); db.refresh(make)
        model = CatalogModel(make_id=make.id, slug="verified-model", name="Модель", aliases=[], source_name="licensed")
        db.add(model); db.commit(); db.refresh(model)
        db.expunge(user); db.expunge(make); db.expunge(model)
    client = TestClient(integration["client"].app)
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}, make, model


def payload(**changes):
    return {"name": "Уточнённая марка", "aliases": ["Локальное название"], "expected_revision": 0,
            "reason": "Сверено с подтверждённым источником", "current_password": PASSWORD,
            "confirmation": "UPDATE_CATALOG", **changes}


def test_catalog_editor_requires_admin_and_reauthentication(integration):
    client, headers, make, _ = setup(integration, role="moderator")
    assert client.get("/api/v1/admin/catalog/makes").status_code == 403
    assert client.patch(f"/api/v1/admin/catalog/makes/{make.id}", json=payload(), headers=headers).status_code == 403


def test_catalog_change_retains_slug_provenance_and_records_immutable_versions(integration):
    client, headers, make, _ = setup(integration)
    listing = client.get("/api/v1/admin/catalog/makes", params={"q": "Исходная"})
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["revision"] == 0
    endpoint = f"/api/v1/admin/catalog/makes/{make.id}"
    assert client.patch(endpoint, json=payload()).status_code == 403
    assert client.patch(endpoint, json=payload(current_password="wrong"), headers=headers).status_code == 401
    response = client.patch(endpoint, json=payload(), headers=headers)
    assert response.status_code == 200, response.text
    item = response.json()["item"]
    assert item["name"] == "Уточнённая марка" and item["revision"] == 1
    assert item["slug"] == "verified-make" and item["manual_override"] is True
    versions = client.get(endpoint + "/versions")
    assert versions.status_code == 200, versions.text
    revision = versions.json()["items"][0]
    assert revision["revision"] == 1
    assert revision["before"]["name"] == "Исходная марка"
    assert revision["after"]["name"] == "Уточнённая марка"
    assert revision["reason"] == "Сверено с подтверждённым источником"
    stale = client.patch(endpoint, json=payload(name="Устаревшее изменение"), headers=headers)
    assert stale.status_code == 409 and stale.json()["code"] == "revision_conflict"
    with integration["SessionLocal"]() as db:
        saved = db.get(CatalogMake, make.id)
        assert saved.source_metadata["permission_ref"] == "owner-license"
        assert saved.source_metadata["source_url"] == "https://source.example/catalog/make"
        assert saved.name == "Уточнённая марка" and saved.slug == "verified-make"
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.entity_id == make.id, AuditEvent.action == "catalog_updated")).all()) == 1
    assert PASSWORD not in versions.text


def test_catalog_pagination_parent_filter_and_validation_do_not_change_identity(integration):
    client, headers, make, model = setup(integration)
    response = client.get("/api/v1/admin/catalog/models", params={"parent_id": str(make.id), "page_size": 1})
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(model.id)
    assert client.get("/api/v1/admin/catalog/models", params={"parent_id": str(uuid.uuid4())}).json()["total"] == 0
    endpoint = f"/api/v1/admin/catalog/makes/{make.id}"
    assert client.patch(endpoint, json=payload(name="  "), headers=headers).status_code == 422
    assert client.patch(endpoint, json=payload(slug="replace-permanent-url"), headers=headers).status_code == 422
    assert client.patch(endpoint, json=payload(year_from=2020, year_to=2019), headers=headers).status_code == 422
    assert client.get("/api/v1/admin/catalog/unknown").status_code == 422


def test_noop_catalog_edit_has_no_new_revision(integration):
    client, headers, make, _ = setup(integration)
    response = client.patch(f"/api/v1/admin/catalog/makes/{make.id}",
                            json=payload(name=make.name, aliases=make.aliases), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["changed"] is False and response.json()["item"]["revision"] == 0
    assert client.get(f"/api/v1/admin/catalog/makes/{make.id}/versions").json()["items"] == []


def test_catalog_versions_sanitize_legacy_snapshots_and_mark_malformed_entries(integration):
    client, _headers, make, _ = setup(integration)
    with integration["SessionLocal"]() as db:
        admin_id = db.scalar(select(User.id).where(User.role == "admin"))
        db.add(AuditEvent(actor_id=admin_id, entity_type="catalog:makes", entity_id=make.id, action="catalog_updated", details={
            "revision": 3, "reason": "Историческая запись", "before": {"name": "Марка", "password": "never-return-snapshot-secret"},
            "after": {"name": "Новая марка", "source": {"source_name": "Источник", "token": "never-return-source-token"}},
        }))
        db.add(AuditEvent(actor_id=admin_id, entity_type="catalog:makes", entity_id=make.id, action="catalog_updated", details={
            "revision": "corrupted", "reason": {"password": "never-return-reason-secret"}, "before": [],
        }))
        db.commit()
    response = client.get(f"/api/v1/admin/catalog/makes/{make.id}/versions")
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 2
    assert sum(item["valid"] for item in response.json()["items"]) == 1
    for forbidden in ["never-return-snapshot-secret", "never-return-source-token", "never-return-reason-secret", "password", "token"]:
        assert forbidden not in response.text


def test_catalog_source_contract_retains_provenance_and_removes_url_credentials(integration):
    client, headers, make, _ = setup(integration)
    with integration["SessionLocal"]() as db:
        row = db.get(CatalogMake, make.id)
        row.source_metadata = {**row.source_metadata, "source_url": "https://user:hidden-password@source.example/make?api_key=hidden-key&access_token=hidden-access&client_secret=hidden-client&X-Amz-Credential=hidden-aws&market=by",
                               "token": "hidden-metadata-token", "retrieved_at": "2026-10-01"}
        db.commit()
    read = client.get("/api/v1/admin/catalog/makes").json()["items"][0]
    assert read["source"]["canonical_url"] == "https://source.example/make?market=by"
    assert read["source"]["permission_reference"] == "owner-license"
    assert read["source"]["retrieved_at"] == "2026-10-01"
    response = client.patch(f"/api/v1/admin/catalog/makes/{make.id}", json=payload(), headers=headers)
    assert response.status_code == 200, response.text
    versions = client.get(f"/api/v1/admin/catalog/makes/{make.id}/versions")
    assert versions.status_code == 200, versions.text
    assert versions.json()["items"][0]["source"]["permission_reference"] == "owner-license"
    for secret in ["hidden-password", "hidden-key", "hidden-metadata-token", "hidden-access", "hidden-client", "hidden-aws"]:
        assert secret not in versions.text
