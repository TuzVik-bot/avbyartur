import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.exc import DBAPIError

from app.listing_change_audit import (
    build_listing_photo_edit_event,
    project_listing_change_event,
)
from app.models import AuditEvent, Company, DealerTeamMember, Listing, ListingStatusEvent, User
from app.security import hash_password

PASSWORD = "listing-audit-test-password-123"


def _add_user(factory, label: str, *, role: str = "user") -> tuple[User, str]:
    email = f"{label}-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name=label,
            password_hash=hash_password(PASSWORD),
            role=role,
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user, email


def _add_listing(
    factory,
    owner_id,
    *,
    status: str = "active",
    company_id=None,
    **overrides,
) -> Listing:
    values = {
        "owner_id": owner_id,
        "company_id": company_id,
        "slug": f"listing-audit-{uuid.uuid4().hex}",
        "status": status,
        "revision": 1,
        "title": "Mazda 3, 2018",
        "description": "Initial listing description",
        "make_name_snapshot": "Mazda",
        "model_name_snapshot": "3",
        "year": 2018,
        "vin": "1HGCM82633A004352",
        "price_amount": 10000,
        "currency": "BYN",
        "manual_city": "Минск",
        "contact_phone": "+375291234567",
        "damaged": False,
        "parts_only": False,
    }
    values.update(overrides)
    with factory() as db:
        listing = Listing(**values)
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _login(integration, email: str) -> tuple[TestClient, str]:
    client = TestClient(integration["client"].app, base_url="http://testserver")
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def _headers(csrf: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf}


def test_edit_records_sanitized_field_snapshots_and_rechecks_active_revision(integration):
    factory = integration["SessionLocal"]
    owner, email = _add_user(factory, "listing-audit-owner")
    listing = _add_listing(
        factory,
        owner.id,
        description="Call +375291234567 or write seller@example.by for details.",
    )
    client, csrf = _login(integration, email)

    response = client.patch(
        f"/api/v1/listings/{listing.id}",
        json={
            "expected_revision": 1,
            "title": "Updated Mazda 3",
            "description": "Call +375299876543 or write new-seller@example.by.",
            "vin": "2HGCM82633A004352",
            "price": {"amount": "8500.00", "currency": "BYN"},
            "manual_city": "Гомель",
            "contact_phone": "+375299876543",
        },
        headers=_headers(csrf),
    )

    assert response.status_code == 200, response.text
    assert response.json()["listing"]["status"] == "draft"
    assert response.json()["listing"]["revision"] == 2
    with factory() as db:
        event = db.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_type == "listing",
                AuditEvent.entity_id == listing.id,
                AuditEvent.action == "listing_edited",
            )
        )
        assert event is not None
        assert event.actor_id == owner.id
        assert event.details["revision"] == 2
        assert event.details["reason"] == "seller_edit"
        assert event.details["from_status"] == "active"
        assert event.details["to_status"] == "draft"
        changes = {change["field"]: change for change in event.details["changes"]}
        assert set(changes) >= {"title", "description", "vin", "price", "manual_city", "contact_phone"}
        assert changes["price"]["before"] == {"amount": "10000.00", "currency": "BYN"}
        assert changes["price"]["after"] == {"amount": "8500.00", "currency": "BYN"}
        assert changes["manual_city"]["before"] == "Минск"
        assert changes["manual_city"]["after"] == "Гомель"
        assert changes["description"]["before"]["length"] > 0
        assert changes["description"]["after"]["length"] > 0
        assert changes["contact_phone"]["before"] != "+375291234567"
        assert changes["contact_phone"]["after"] != "+375299876543"
        assert changes["vin"]["before"] != "1HGCM82633A004352"
        assert changes["vin"]["after"] != "2HGCM82633A004352"
        serialized = json.dumps(event.details, ensure_ascii=False)
        for private_value in (
            "+375291234567",
            "+375299876543",
            "1HGCM82633A004352",
            "2HGCM82633A004352",
            "seller@example.by",
            "new-seller@example.by",
        ):
            assert private_value not in serialized
        transition = db.scalar(
            select(ListingStatusEvent).where(
                ListingStatusEvent.listing_id == listing.id,
                ListingStatusEvent.revision == 2,
            )
        )
        assert transition is not None
        assert transition.to_status == "draft"


def test_stale_and_invalid_edits_do_not_create_audit_events(integration):
    factory = integration["SessionLocal"]
    owner, email = _add_user(factory, "listing-audit-stale")
    listing = _add_listing(factory, owner.id, status="draft")
    client, csrf = _login(integration, email)

    stale = client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": 2, "title": "Stale title"},
        headers=_headers(csrf),
    )
    invalid = client.patch(
        f"/api/v1/listings/{listing.id}",
        json={"expected_revision": 1, "description": "<script>not plain text</script>"},
        headers=_headers(csrf),
    )

    assert stale.status_code == 409, stale.text
    assert invalid.status_code == 422, invalid.text
    with factory() as db:
        assert db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == "listing",
                AuditEvent.entity_id == listing.id,
                AuditEvent.action == "listing_edited",
            )
        ) is None


def test_foreign_public_patch_is_forbidden_but_private_draft_stays_hidden(integration):
    factory = integration["SessionLocal"]
    owner, _ = _add_user(factory, "listing-audit-owner")
    stranger, stranger_email = _add_user(factory, "listing-audit-stranger")
    active_public = _add_listing(factory, owner.id, status="active")
    private_draft = _add_listing(factory, owner.id, status="draft")
    client, csrf = _login(integration, stranger_email)
    payload = {"expected_revision": 1, "title": "Unauthorized edit"}

    public_result = client.patch(
        f"/api/v1/listings/{active_public.id}", json=payload, headers=_headers(csrf)
    )
    draft_result = client.patch(
        f"/api/v1/listings/{private_draft.id}", json=payload, headers=_headers(csrf)
    )

    assert stranger.id != owner.id
    assert public_result.status_code == 403, public_result.text
    assert draft_result.status_code == 404, draft_result.text
    with factory() as db:
        assert db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == "listing",
                AuditEvent.entity_id.in_([active_public.id, private_draft.id]),
                AuditEvent.action == "listing_edited",
            )
        ) is None


def test_company_seller_can_edit_own_company_listing_but_not_another_company(integration):
    factory = integration["SessionLocal"]
    owner_a, _ = _add_user(factory, "listing-audit-company-a-owner")
    owner_b, _ = _add_user(factory, "listing-audit-company-b-owner")
    seller, seller_email = _add_user(factory, "listing-audit-company-a-seller")
    with factory() as db:
        company_a = Company(
            owner_id=owner_a.id,
            name="Audit Dealer A",
            slug=f"audit-dealer-a-{uuid.uuid4().hex}",
            unp=f"{uuid.uuid4().int % 900_000_000 + 100_000_000}",
            address="Minsk",
            phone="+375291234567",
            status="approved",
        )
        company_b = Company(
            owner_id=owner_b.id,
            name="Audit Dealer B",
            slug=f"audit-dealer-b-{uuid.uuid4().hex}",
            unp=f"{uuid.uuid4().int % 900_000_000 + 100_000_000}",
            address="Gomel",
            phone="+375291234568",
            status="approved",
        )
        db.add_all([company_a, company_b])
        db.flush()
        db.add(
            DealerTeamMember(
                company_id=company_a.id,
                user_id=seller.id,
                role="seller",
                status="active",
                granted_by=owner_a.id,
            )
        )
        listing_a = Listing(
            owner_id=owner_a.id,
            company_id=company_a.id,
            slug=f"listing-audit-company-a-{uuid.uuid4().hex}",
            status="active",
            revision=1,
            title="Company A car",
            description="Company listing A",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
        )
        listing_b = Listing(
            owner_id=owner_b.id,
            company_id=company_b.id,
            slug=f"listing-audit-company-b-{uuid.uuid4().hex}",
            status="active",
            revision=1,
            title="Company B car",
            description="Company listing B",
            contact_phone="+375291234568",
            damaged=False,
            parts_only=False,
        )
        db.add_all([listing_a, listing_b])
        db.commit()
        db.refresh(listing_a)
        db.refresh(listing_b)
        listing_a_id = listing_a.id
        listing_b_id = listing_b.id

    client, csrf = _login(integration, seller_email)
    own = client.patch(
        f"/api/v1/listings/{listing_a_id}",
        json={"expected_revision": 1, "title": "Company A revised car"},
        headers=_headers(csrf),
    )
    foreign = client.patch(
        f"/api/v1/listings/{listing_b_id}",
        json={"expected_revision": 1, "title": "Company B altered car"},
        headers=_headers(csrf),
    )

    assert own.status_code == 200, own.text
    assert own.json()["listing"]["status"] == "draft"
    assert foreign.status_code == 403, foreign.text
    with factory() as db:
        assert db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == "listing",
                AuditEvent.entity_id == listing_a_id,
                AuditEvent.action == "listing_edited",
            )
        ) is not None
        assert db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.entity_type == "listing",
                AuditEvent.entity_id == listing_b_id,
                AuditEvent.action == "listing_edited",
            )
        ) is None


def test_moderation_projection_masks_sensitive_snapshots_and_rejects_other_events():
    from datetime import UTC, datetime

    event = AuditEvent(
        actor_id=uuid.uuid4(),
        entity_type="listing",
        entity_id=uuid.uuid4(),
        action="listing_edited",
        created_at=datetime.now(UTC),
        details={
            "revision": 2,
            "reason": "seller_edit",
            "from_status": "active",
            "to_status": "draft",
            "changed_field_keys": ["vin", "contact_phone", "description", "unknown_secret"],
            "changes": [
                {"field": "vin", "before": "1HGCM82633A004352", "after": "2HGCM82633A004352"},
                {"field": "contact_phone", "before": "+375291234567", "after": "+375299876543"},
                {"field": "description", "before": "private description text", "after": "changed private description"},
                {"field": "unknown_secret", "before": "must not escape", "after": "must not escape"},
            ],
        },
    )

    projected = project_listing_change_event(event)
    assert projected is not None
    assert projected.changed_field_keys == ["vin", "contact_phone", "description"]
    serialized = projected.model_dump_json()
    for private_value in (
        "1HGCM82633A004352",
        "2HGCM82633A004352",
        "+375291234567",
        "+375299876543",
        "private description text",
        "changed private description",
        "must not escape",
    ):
        assert private_value not in serialized

    event.action = "listing_blocked"
    assert project_listing_change_event(event) is None


def test_photo_change_event_contains_only_sanitized_photo_metadata():
    actor_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    before = [
        {
            "id": uuid.uuid4(),
            "position": 0,
            "is_cover": True,
            "status": "ready",
            "storage_name": "private-storage-secret",
            "original_name": "private-original-secret.jpg",
            "perceptual_hash": "aabbccddeeff0011",
        }
    ]
    after = [
        {
            **before[0],
            "position": 1,
            "is_cover": False,
        },
        {
            "id": uuid.uuid4(),
            "position": 0,
            "is_cover": True,
            "status": "ready",
            "storage_name": "second-private-storage-secret",
            "original_name": "second-private-original-secret.jpg",
            "perceptual_hash": "1122334455667788",
        },
    ]

    event = build_listing_photo_edit_event(
        actor_id=actor_id,
        listing_id=listing_id,
        revision=3,
        from_status="draft",
        to_status="draft",
        before=before,
        after=after,
    )

    assert event is not None
    assert event.actor_id == actor_id
    assert event.entity_id == listing_id
    assert event.action == "listing_edited"
    assert event.details["revision"] == 3
    assert event.details["reason"] == "seller_photo_edit"
    assert event.details["changed_field_keys"] == ["photos"]
    serialized = json.dumps(event.details)
    for private_value in (
        "private-storage-secret",
        "private-original-secret.jpg",
        "aabbccddeeff0011",
        "second-private-storage-secret",
        "second-private-original-secret.jpg",
        "1122334455667788",
    ):
        assert private_value not in serialized


def test_listing_edit_locks_actor_before_phone_reveal_reaches_company(integration, monkeypatch):
    import app.api.listings as listings_api

    factory = integration["SessionLocal"]
    owner, owner_email = _add_user(factory, "listing-audit-race-owner")
    with factory() as db:
        company = Company(
            owner_id=owner.id,
            name="Audit lock-order dealer",
            slug=f"audit-lock-order-{uuid.uuid4().hex}",
            unp=f"{uuid.uuid4().int % 900_000_000 + 100_000_000}",
            address="Minsk",
            phone="+375291234567",
            status="approved",
        )
        db.add(company)
        db.flush()
        listing = Listing(
            owner_id=owner.id,
            company_id=company.id,
            slug=f"listing-audit-lock-order-{uuid.uuid4().hex}",
            status="active",
            revision=1,
            title="Lock order test car",
            description="A company listing for a bounded lock-order regression.",
            contact_phone="+375299876543",
            damaged=False,
            parts_only=False,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        listing_id = listing.id

    owner_client, owner_csrf = _login(integration, owner_email)
    edit_has_company_lock = Event()
    release_edit_after_company_lock = Event()
    reveal_is_attempting_actor_lock = Event()
    engine = integration["engine"]
    require_owned_listing = listings_api.require_owned_listing
    lock_public_active_listing = listings_api._lock_public_active_listing

    def mark_edit_connection(db, *args, **kwargs):
        db.connection().info["listing_lock_probe"] = "edit"
        return require_owned_listing(db, *args, **kwargs)

    def mark_reveal_connection(db, *args, **kwargs):
        db.connection().info["listing_lock_probe"] = "reveal"
        return lock_public_active_listing(db, *args, **kwargs)

    monkeypatch.setattr(listings_api, "require_owned_listing", mark_edit_connection)
    monkeypatch.setattr(listings_api, "_lock_public_active_listing", mark_reveal_connection)

    def bound_lock_wait(_connection):
        raw_connection = _connection.connection.driver_connection
        with raw_connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '3000ms'")

    def observe_edit_company_lock(connection, _cursor, statement, _parameters, _context, _many):
        normalized = statement.casefold()
        if (
            connection.info.get("listing_lock_probe") == "edit"
            and "for update" in normalized
            and "companies" in normalized
        ):
            edit_has_company_lock.set()
            if not release_edit_after_company_lock.wait(5):
                raise AssertionError("test did not release the edit after its company lock")

    def observe_reveal_actor_lock(_connection, _cursor, statement, _parameters, _context, _many):
        normalized = statement.casefold()
        if (
            _connection.info.get("listing_lock_probe") == "reveal"
            and "for update" in normalized
            and "users" in normalized
        ):
            reveal_is_attempting_actor_lock.set()

    event.listen(engine, "begin", bound_lock_wait)
    event.listen(engine, "after_cursor_execute", observe_edit_company_lock)
    event.listen(engine, "before_cursor_execute", observe_reveal_actor_lock)
    try:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="listing-edit-lock-race") as executor:
            edit_future = executor.submit(
                owner_client.patch,
                f"/api/v1/listings/{listing_id}",
                json={"expected_revision": 1, "title": "Revised lock order test car"},
                headers=_headers(owner_csrf),
            )
            try:
                assert edit_has_company_lock.wait(5), "company edit did not acquire the company lock"
                # The PATCH must already hold its actor row when it reaches the
                # Company lock. A separate NOWAIT transaction checks that
                # ordering without reading or mutating application data.
                with factory() as probe_db:
                    try:
                        probe_db.scalar(
                            select(User.id)
                            .where(User.id == owner.id)
                            .with_for_update(nowait=True)
                        )
                    except DBAPIError as exc:
                        sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
                        assert sqlstate == "55P03", "actor row probe failed for an unexpected database error"
                        actor_row_is_locked = True
                        probe_db.rollback()
                    else:
                        actor_row_is_locked = False
                        probe_db.rollback()
                assert actor_row_is_locked, "PATCH reached the company lock without first locking its actor"

                reveal_future = executor.submit(
                    owner_client.post,
                    f"/api/v1/listings/{listing_id}/phone-reveal",
                    headers=_headers(owner_csrf),
                )
                assert reveal_is_attempting_actor_lock.wait(5), "phone reveal did not attempt the shared actor lock"
                release_edit_after_company_lock.set()
                edit_response = edit_future.result(timeout=8)
                reveal_response = reveal_future.result(timeout=8)
            finally:
                release_edit_after_company_lock.set()
    finally:
        event.remove(engine, "begin", bound_lock_wait)
        event.remove(engine, "after_cursor_execute", observe_edit_company_lock)
        event.remove(engine, "before_cursor_execute", observe_reveal_actor_lock)

    assert edit_response.status_code == 200
    assert reveal_response.status_code in {200, 404}
