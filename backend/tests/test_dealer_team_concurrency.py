"""PostgreSQL regressions for dealer team and administrator lock ordering."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient

from app.models import Company, User
from app.security import hash_password


PASSWORD = "dealer-team-lock-test-password-123"


def _add_user(factory, *, label: str, role: str = "user", user_id: uuid.UUID | None = None):
    user = User(
        id=user_id,
        email=f"dealer-team-lock-{label}-{uuid.uuid4().hex}@example.com",
        display_name=f"Synthetic {label}",
        password_hash=hash_password(PASSWORD),
        role=role,
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _company(factory, owner_id: uuid.UUID) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:16]
    with factory() as db:
        company = Company(
            owner_id=owner_id,
            name=f"Synthetic team lock {suffix}",
            slug=f"team-lock-{suffix}",
            unp=f"{uuid.uuid4().int % 900_000_000 + 100_000_000}",
            address="Minsk",
            phone="+375291234567",
            status="approved",
            revision=1,
        )
        db.add(company)
        db.commit()
        return company.id


def _login(integration, email: str) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(integration["client"].app)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def _admin_change_body(target: User) -> dict:
    return {
        "role": "moderator",
        "status": "active",
        "expected_role": target.role,
        "expected_status": target.status,
        "reason": "Synthetic team lock-order regression",
        "confirmation": "UPDATE_USER",
        "current_password": PASSWORD,
    }


def _assert_team_mutation_waits_for_admin_guard(integration, monkeypatch, *, mutation: str) -> None:
    from app.api import admin as admin_api
    from app.api import dealer as dealer_api
    from app.admin_service import lock_active_administrators as real_lock_active_administrators

    factory = integration["SessionLocal"]
    # Fixed UUID order makes the old PATCH actor->target acquisition collide
    # with admin's active-admin-target acquisition in the same direction as POST.
    owner = _add_user(factory, label=f"owner-{mutation}", user_id=uuid.UUID(int=1))
    admin = _add_user(factory, label=f"admin-{mutation}", role="admin", user_id=uuid.UUID(int=2))
    _company(factory, owner.id)
    owner_client, owner_headers = _login(integration, owner.email)
    admin_client, admin_headers = _login(integration, admin.email)

    member_id = None
    if mutation == "patch":
        added = owner_client.post(
            "/api/v1/dealer/team",
            json={"user_id": str(admin.id), "role": "admin"},
            headers=owner_headers,
        )
        assert added.status_code == 200, added.text
        member_id = added.json()["member"]["id"]

    admin_guard_locked = Event()
    team_guard_started = Event()
    release_admin = Event()

    def hold_admin_guard(db):
        locked = real_lock_active_administrators(db)
        admin_guard_locked.set()
        if not release_admin.wait(timeout=8):
            raise AssertionError("test did not release the administrator guard")
        return locked

    def observe_team_guard(db):
        team_guard_started.set()
        return real_lock_active_administrators(db)

    monkeypatch.setattr(admin_api, "lock_active_administrators", hold_admin_guard)
    monkeypatch.setattr(dealer_api, "lock_active_administrators", observe_team_guard, raising=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        admin_future = pool.submit(
            admin_client.patch,
            f"/api/v1/admin/users/{owner.id}",
            json=_admin_change_body(owner),
            headers=admin_headers,
        )
        assert admin_guard_locked.wait(timeout=5), "admin PATCH did not acquire its guard"

        if mutation == "post":
            team_future = pool.submit(
                owner_client.post,
                "/api/v1/dealer/team",
                json={"user_id": str(admin.id), "role": "admin"},
                headers=owner_headers,
            )
        else:
            team_future = pool.submit(
                owner_client.patch,
                f"/api/v1/dealer/team/{member_id}",
                json={"status": "revoked", "expected_revision": 1},
                headers=owner_headers,
            )

        try:
            entered_guard = team_guard_started.wait(timeout=2)
            if entered_guard:
                assert not admin_future.done(), "admin PATCH should still own the guard while the team mutation waits"
                assert not team_future.done(), "team mutation should wait before taking user and company locks"
        finally:
            # Releasing the first transaction is mandatory even on RED so the
            # database can resolve the old-order deadlock and the test can exit.
            release_admin.set()

        admin_response = admin_future.result(timeout=10)
        team_response = team_future.result(timeout=10)

    assert admin_response.status_code in {200, 403, 409}, admin_response.text
    assert team_response.status_code in {200, 403, 409}, team_response.text
    assert entered_guard, "team mutation must enter the active-admin guard before user locks"


def test_adding_active_admin_waits_for_admin_set_before_locking_users(integration, monkeypatch):
    _assert_team_mutation_waits_for_admin_guard(integration, monkeypatch, mutation="post")


def test_updating_team_member_waits_for_admin_set_before_locking_users(integration, monkeypatch):
    _assert_team_mutation_waits_for_admin_guard(integration, monkeypatch, mutation="patch")
