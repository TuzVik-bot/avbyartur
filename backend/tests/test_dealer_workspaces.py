import uuid

from fastapi.testclient import TestClient

from app.models import Company, ContactReveal, Conversation, Listing, User
from app.security import hash_password


PASSWORD = "dealer-workspace-test-password-123"


def _add_user(factory, *, label: str) -> tuple[uuid.UUID, str]:
    email = f"{label}-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name=label,
            password_hash=hash_password(PASSWORD),
            role="user",
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email


def _add_company(factory, owner_id: uuid.UUID) -> uuid.UUID:
    suffix = uuid.uuid4().int % 900_000_000 + 100_000_000
    with factory() as db:
        company = Company(
            owner_id=owner_id,
            name=f"Dealer {suffix}",
            slug=f"dealer-{suffix}",
            unp=str(suffix),
            address="Minsk",
            phone="+375291234567",
            status="approved",
            revision=1,
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        return company.id


def _login(integration, email: str) -> tuple[TestClient, str]:
    client = TestClient(integration["client"].app, base_url="http://testserver")
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _csrf(token: str) -> dict[str, str]:
    return {"X-CSRF-Token": token}


def test_dealer_team_scopes_roles_and_existing_active_users(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="owner")
    seller_id, seller_email = _add_user(factory, label="seller")
    outsider_id, outsider_email = _add_user(factory, label="outsider")
    company_id = _add_company(factory, owner_id)
    outsider_company_id = _add_company(factory, outsider_id)
    owner, owner_csrf = _login(integration, owner_email)
    seller, seller_csrf = _login(integration, seller_email)
    outsider, outsider_csrf = _login(integration, outsider_email)
    with factory() as db:
        foreign_listing = Listing(
            owner_id=owner_id,
            company_id=company_id,
            slug=f"company-scope-{uuid.uuid4().hex}",
            title="Company scoped draft",
            description="Private company draft",
            contact_phone="+375291234567",
            status="draft",
            revision=1,
        )
        db.add(foreign_listing)
        db.commit()
        foreign_listing_id = foreign_listing.id

    initial = owner.get("/api/v1/dealer/team")
    assert initial.status_code == 200, initial.text
    assert [(row["role"], row["user_id"]) for row in initial.json()["items"]] == [
        ("owner", str(owner_id)),
    ]

    added = owner.post(
        "/api/v1/dealer/team",
        json={"user_id": str(seller_id), "role": "seller"},
        headers=_csrf(owner_csrf),
    )
    assert added.status_code == 200, added.text
    member = added.json()["member"]
    assert member["role"] == "seller"
    assert member["user_id"] == str(seller_id)
    revoked = owner.patch(
        f"/api/v1/dealer/team/{member['id']}",
        json={"status": "revoked", "expected_revision": member["revision"]},
        headers=_csrf(owner_csrf),
    )
    assert revoked.status_code == 200, revoked.text
    reactivated = owner.post(
        "/api/v1/dealer/team",
        json={"user_id": str(seller_id), "role": "seller"},
        headers=_csrf(owner_csrf),
    )
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["member"]["status"] == "active"
    assert reactivated.json()["member"]["revision"] == revoked.json()["member"]["revision"] + 1
    assert seller.get("/api/v1/dealer/team").status_code == 200

    forbidden = seller.post(
        "/api/v1/dealer/team",
        json={"user_id": str(outsider_id), "role": "viewer"},
        headers=_csrf(seller_csrf),
    )
    assert forbidden.status_code == 403

    cross_company = outsider.patch(
        f"/api/v1/dealer/team/{member['id']}",
        json={"role": "viewer", "expected_revision": member["revision"]},
        headers=_csrf(outsider_csrf),
    )
    assert outsider_company_id != company_id
    assert cross_company.status_code == 404
    assert outsider.get(f"/api/v1/listings/{foreign_listing_id}").status_code == 404


def test_company_listing_permissions_allow_seller_and_admin_but_keep_viewer_read_only(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="permission-owner")
    admin_id, admin_email = _add_user(factory, label="permission-admin")
    seller_id, seller_email = _add_user(factory, label="permission-seller")
    viewer_id, viewer_email = _add_user(factory, label="permission-viewer")
    company_id = _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    admin, admin_csrf = _login(integration, admin_email)
    seller, seller_csrf = _login(integration, seller_email)
    viewer, viewer_csrf = _login(integration, viewer_email)

    for user_id, role in ((admin_id, "admin"), (seller_id, "seller"), (viewer_id, "viewer")):
        added = owner.post(
            "/api/v1/dealer/team",
            json={"user_id": str(user_id), "role": role},
            headers=_csrf(owner_csrf),
        )
        assert added.status_code == 200, added.text

    draft = seller.post(
        "/api/v1/listings/drafts",
        json={"seller_type": "company"},
        headers={**_csrf(seller_csrf), "Idempotency-Key": "seller-company-draft"},
    )
    assert draft.status_code == 200, draft.text
    listing = draft.json()["listing"]
    assert listing["seller"]["id"] == str(company_id)
    listing_id = uuid.UUID(listing["id"])
    with factory() as db:
        assert db.get(Listing, listing_id).owner_id == seller_id

    visible = viewer.get("/api/v1/me/listings")
    assert visible.status_code == 200, visible.text
    assert [item["id"] for item in visible.json()["items"]] == [listing["id"]]
    detail = viewer.get(f"/api/v1/listings/{listing['id']}")
    assert detail.status_code == 200, detail.text

    edited = admin.patch(
        f"/api/v1/listings/{listing['id']}",
        json={"expected_revision": listing["revision"], "title": "Updated by company admin"},
        headers=_csrf(admin_csrf),
    )
    assert edited.status_code == 200, edited.text
    with factory() as db:
        assert db.get(Listing, listing_id).owner_id == seller_id

    denied = viewer.patch(
        f"/api/v1/listings/{listing['id']}",
        json={"expected_revision": edited.json()["listing"]["revision"], "title": "Viewer edit"},
        headers=_csrf(viewer_csrf),
    )
    assert denied.status_code == 403


def test_dealer_feed_rejects_xml_entities_and_keeps_import_history(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="feed-owner")
    _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)

    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Inventory XML", "format": "xml"},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]

    malicious = b'<!DOCTYPE listings [<!ENTITY x "expanded">]><listings><listing><title>&x;</title></listing></listings>'
    imported = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports",
        files={"file": ("inventory.xml", malicious, "application/xml")},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "xml-unsafe-import"},
    )
    assert imported.status_code == 200, imported.text
    run_id = imported.json()["run"]["id"]
    assert imported.json()["run"]["dry_run"] is True
    assert imported.json()["run"]["status"] == "failed"

    history = owner.get(f"/api/v1/dealer/feed-imports/{run_id}")
    assert history.status_code == 200, history.text
    assert history.json()["run"]["status"] == "failed"
    rows = owner.get(f"/api/v1/dealer/feed-imports/{run_id}/rows")
    assert rows.status_code == 200, rows.text
    assert rows.json()["items"][0]["error_code"] == "unsafe_xml"


def test_csv_feed_preview_apply_update_and_replay_are_idempotent(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="csv-feed-owner")
    company_id = _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={
            "name": "Inventory CSV",
            "format": "csv",
            "field_mapping": {
                "dealer_external_id": "stock_number",
                "manual_make": "brand",
                "price_amount": "cost",
                "currency": "currency",
            },
        },
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]
    content = b"stock_number,brand,cost,currency\nA-100,Toyota,12000.50,BYN\n"

    preview = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports",
        files={"file": ("inventory.csv", content, "text/csv")},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "csv-preview"},
    )
    assert preview.status_code == 200, preview.text
    preview_run = preview.json()["run"]
    assert preview_run["dry_run"] is True
    assert preview_run["status"] == "preview"
    preview_rows = owner.get(f"/api/v1/dealer/feed-imports/{preview_run['id']}/rows")
    assert preview_rows.json()["items"][0]["action"] == "create"
    assert preview_rows.json()["items"][0]["listing_id"] is None
    with factory() as db:
        assert db.query(Listing).filter(Listing.company_id == company_id).count() == 0

    applied = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports?dry_run=false",
        files={"file": ("inventory.csv", content, "text/csv")},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "csv-apply"},
    )
    assert applied.status_code == 200, applied.text
    applied_run = applied.json()["run"]
    assert applied_run["status"] == "succeeded"
    assert applied_run["applied_rows"] == 1
    applied_rows = owner.get(f"/api/v1/dealer/feed-imports/{applied_run['id']}/rows")
    row = applied_rows.json()["items"][0]
    assert row["action"] == "created"
    assert row["status"] == "draft"
    assert row["listing_id"]
    with factory() as db:
        listing = db.get(Listing, uuid.UUID(row["listing_id"]))
        assert listing.owner_id == owner_id
        assert listing.company_id == company_id
        assert listing.status == "draft"

    replayed = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports?dry_run=false",
        files={"file": ("inventory.csv", content, "text/csv")},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "csv-apply"},
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["run"]["id"] == applied_run["id"]
    changed = b"stock_number,brand,cost,currency\nA-100,Lada,13000.00,BYN\n"
    updated = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/imports?dry_run=false",
        files={"file": ("inventory.csv", changed, "text/csv")},
        headers={**_csrf(owner_csrf), "Idempotency-Key": "csv-update"},
    )
    assert updated.status_code == 200, updated.text
    updated_row = owner.get(f"/api/v1/dealer/feed-imports/{updated.json()['run']['id']}/rows").json()["items"][0]
    assert updated_row["action"] == "updated"
    with factory() as db:
        listing = db.get(Listing, uuid.UUID(row["listing_id"]))
        assert listing.manual_make == "Lada"
        assert listing.status == "draft"
        assert db.query(Listing).filter(Listing.company_id == company_id).count() == 1


def test_api_feed_uses_one_time_token_and_keeps_bad_rows_in_import_history(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="api-feed-owner")
    _add_company(factory, owner_id)
    owner, owner_csrf = _login(integration, owner_email)
    created = owner.post(
        "/api/v1/dealer/feeds",
        json={"name": "Inventory API", "format": "api"},
        headers=_csrf(owner_csrf),
    )
    assert created.status_code == 200, created.text
    token = created.json()["api_token"]
    feed_id = created.json()["feed"]["id"]
    assert token
    listed = owner.get("/api/v1/dealer/feeds")
    assert listed.status_code == 200
    assert token not in listed.text

    payload = {
        "dry_run": False,
        "items": [
            {"dealer_external_id": "api-1", "manual_make": "Toyota"},
            {"dealer_external_id": "api-2", "year": "not-a-year"},
        ],
    }
    imported = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/api-imports",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "api-import"},
    )
    assert imported.status_code == 200, imported.text
    run = imported.json()["run"]
    assert run["status"] == "partial"
    assert run["applied_rows"] == 1
    assert run["rejected_rows"] == 1
    rows = owner.get(f"/api/v1/dealer/feed-imports/{run['id']}/rows").json()["items"]
    assert [item["status"] for item in rows] == ["draft", "rejected"]
    assert rows[1]["field_errors"]["year"]

    rotated = owner.post(f"/api/v1/dealer/feeds/{feed_id}/rotate-token", headers=_csrf(owner_csrf))
    assert rotated.status_code == 200, rotated.text
    rejected_old = owner.post(
        f"/api/v1/dealer/feeds/{feed_id}/api-imports",
        json={"items": [{"dealer_external_id": "api-3", "manual_make": "Honda"}]},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "old-api-token"},
    )
    assert rejected_old.status_code == 401


def test_dealer_analytics_counts_company_views_contacts_and_chats(integration):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="analytics-owner")
    buyer_id, _ = _add_user(factory, label="analytics-buyer")
    outsider_id, outsider_email = _add_user(factory, label="analytics-outsider")
    company_id = _add_company(factory, owner_id)
    _add_company(factory, outsider_id)
    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            company_id=company_id,
            slug=f"analytics-{uuid.uuid4().hex}",
            title="Analytics car",
            description="A test listing",
            contact_phone="+375291234567",
            status="active",
        )
        db.add(listing)
        db.flush()
        db.add(ContactReveal(listing_id=listing.id, user_id=buyer_id))
        db.add(Conversation(listing_id=listing.id, buyer_id=buyer_id, seller_id=owner_id))
        db.commit()
        listing_id = listing.id
    owner, _ = _login(integration, owner_email)
    outsider, _ = _login(integration, outsider_email)
    public = TestClient(integration["client"].app, base_url="http://testserver")
    viewed = public.get(f"/api/v1/listings/{listing_id}")
    assert viewed.status_code == 200, viewed.text
    # Owner views are excluded from public listing analytics.
    owner_view = owner.get(f"/api/v1/listings/{listing_id}")
    assert owner_view.status_code == 200, owner_view.text

    response = owner.get("/api/v1/dealer/analytics")
    assert response.status_code == 200, response.text
    assert response.json()["totals"] == {
        "listings": 1,
        "active_listings": 1,
        "contact_reveals": 1,
        "chats": 1,
        "views": 1,
    }
    assert response.json()["items"][0]["views"] == 1

    isolated = outsider.get("/api/v1/dealer/analytics")
    assert isolated.status_code == 200, isolated.text
    assert isolated.json()["totals"]["listings"] == 0
    assert all(item["listing_id"] != str(listing_id) for item in isolated.json()["items"])
