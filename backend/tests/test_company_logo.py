import uuid
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from app.models import Company, DealerTeamMember, User
from app.security import hash_password

PASSWORD = "company-logo-test-password-123"


def _add_user(factory) -> User:
    email = f"logo-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, display_name="logo", password_hash=hash_password(PASSWORD), role="user", status="active")
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _add_company(factory, owner: User, status: str = "approved") -> Company:
    company = Company(
        owner_id=owner.id,
        name="Logo Motors",
        slug=f"logo-{uuid.uuid4().hex[:10]}",
        unp=str(100000000 + uuid.uuid4().int % 899999999),
        address="",
        phone="",
        status=status,
    )
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        db.expunge(company)
    return company


def _client(integration, user: User) -> tuple[TestClient, dict]:
    client = TestClient(integration["client"].app)
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def _png(size=(8, 8)) -> bytes:
    data = BytesIO()
    Image.new("RGB", size, color=(20, 50, 90)).save(data, format="PNG")
    return data.getvalue()


def _upload(client, headers, company_id, revision=1, payload=None, content_type="image/png"):
    return client.put(
        f"/api/v1/companies/{company_id}/logo",
        data={"expected_revision": str(revision)},
        files={"file": ("brand.png", payload if payload is not None else _png(), content_type)},
        headers=headers,
    )


def test_logo_upload_reencodes_bumps_revision_and_is_served_publicly(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    company = _add_company(factory, owner)
    client, headers = _client(integration, owner)
    response = _upload(client, headers, company.id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 2
    assert body["logo_url"].startswith("/api/v1/company-logos/") and body["logo_url"].endswith(".webp")
    assert client.get("/api/v1/me/company").json()["company"]["logo_url"] == body["logo_url"]
    public = integration["client"].get(f"/api/v1/dealers/{company.slug}").json()
    assert public["company"]["logo_url"] == body["logo_url"]
    served = TestClient(integration["client"].app).get(body["logo_url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.headers["x-content-type-options"] == "nosniff"
    with Image.open(BytesIO(served.content)) as decoded:
        assert decoded.format == "WEBP" and decoded.size == (8, 8)

    replaced = _upload(client, headers, company.id, revision=2)
    assert replaced.status_code == 200, replaced.text
    assert integration["client"].get(body["logo_url"]).status_code == 404
    assert integration["client"].get(replaced.json()["logo_url"]).status_code == 200
    stored = list((integration["media_root"] / "company-logos").iterdir())
    assert replaced.json()["logo_url"].rsplit("/", 1)[1] in {path.name for path in stored}
    assert body["logo_url"].rsplit("/", 1)[1] not in {path.name for path in stored}


def test_logo_upload_rejects_stale_revision_bad_data_and_missing_csrf(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    company = _add_company(factory, owner)
    client, headers = _client(integration, owner)
    assert _upload(client, {}, company.id).status_code == 403
    assert _upload(client, headers, company.id, revision=5).status_code == 409
    assert _upload(client, headers, company.id, payload=b"not an image").status_code == 415
    assert _upload(client, headers, company.id, content_type="image/jpeg").status_code == 415
    gif = BytesIO()
    Image.new("RGB", (4, 4)).save(gif, format="GIF")
    assert _upload(client, headers, company.id, payload=gif.getvalue(), content_type="image/gif").status_code == 415
    with factory() as db:
        assert db.get(Company, company.id).logo_storage_name is None


def test_logo_upload_idor_requires_company_manager(integration):
    factory = integration["SessionLocal"]
    owner, stranger, seller = _add_user(factory), _add_user(factory), _add_user(factory)
    company = _add_company(factory, owner)
    with factory() as db:
        db.add(DealerTeamMember(company_id=company.id, user_id=seller.id, role="seller", status="active", granted_by=owner.id))
        db.commit()
    anonymous = TestClient(integration["client"].app)
    assert (
        anonymous.put(
            f"/api/v1/companies/{company.id}/logo",
            data={"expected_revision": "1"},
            files={"file": ("brand.png", _png(), "image/png")},
        ).status_code
        == 401
    )
    stranger_client, stranger_headers = _client(integration, stranger)
    assert _upload(stranger_client, stranger_headers, company.id).status_code == 404
    seller_client, seller_headers = _client(integration, seller)
    assert _upload(seller_client, seller_headers, company.id).status_code == 403
    with factory() as db:
        assert db.get(Company, company.id).logo_storage_name is None


def test_logo_serving_rejects_unknown_names_and_blocked_companies(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    company = _add_company(factory, owner)
    client, headers = _client(integration, owner)
    logo_url = _upload(client, headers, company.id).json()["logo_url"]
    public = TestClient(integration["client"].app)
    for name in ("../secret.webp", "a" * 32 + ".png", uuid.uuid4().hex + ".webp"):
        assert public.get(f"/api/v1/company-logos/{name}").status_code == 404
    with factory() as db:
        db.get(Company, company.id).status = "blocked"
        db.commit()
    assert public.get(logo_url).status_code == 404


def test_logo_upload_route_is_covered_by_upload_body_limit():
    from app.main import UploadBodyLimitMiddleware

    company_id = uuid.uuid4()
    logo = {"type": "http", "method": "PUT", "path": f"/api/v1/companies/{company_id}/logo"}
    assert UploadBodyLimitMiddleware._is_photo_upload(logo)
    assert not UploadBodyLimitMiddleware._is_photo_upload({**logo, "method": "POST"})
    assert UploadBodyLimitMiddleware._is_photo_upload(
        {"type": "http", "method": "POST", "path": f"/api/v1/listings/{company_id}/photos"}
    )
    assert not UploadBodyLimitMiddleware._is_photo_upload(
        {"type": "http", "method": "PATCH", "path": f"/api/v1/companies/{company_id}"}
    )
