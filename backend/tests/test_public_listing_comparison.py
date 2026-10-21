import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Listing, ListingViewEvent, User
from app.security import hash_password


PASSWORD = "public-comparison-test-password-123"


def _add_owner(factory) -> tuple[uuid.UUID, str]:
    email = f"comparison-owner-{uuid.uuid4().hex[:12]}@example.com"
    user = User(
        email=email,
        display_name="Comparison owner",
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, email


def _add_listing(factory, owner_id: uuid.UUID, *, status: str, title: str) -> uuid.UUID:
    listing = Listing(
        owner_id=owner_id,
        slug=f"comparison-{uuid.uuid4().hex}",
        status=status,
        revision=1,
        title=title,
        description="Comparison endpoint test listing.",
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        make_name_snapshot="Mazda",
        model_name_snapshot="3",
        year=2018,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        return listing.id


def test_public_comparison_is_batch_public_only_and_does_not_record_views(integration):
    factory = integration["SessionLocal"]
    owner_id, email = _add_owner(factory)
    active_id = _add_listing(factory, owner_id, status="active", title="Public Mazda")
    draft_id = _add_listing(factory, owner_id, status="draft", title="Private draft Mazda")

    # The endpoint works anonymously and keeps public-only semantics with the
    # owner's session cookie, too.
    client: TestClient = integration["client"]
    query = [("ids", str(active_id)), ("ids", str(draft_id))]
    anonymous_response = client.get("/api/v1/listings/compare", params=query)
    assert anonymous_response.status_code == 200, anonymous_response.text

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text

    response = client.get("/api/v1/listings/compare", params=query)

    assert response.status_code == 200, response.text
    assert response.json() == anonymous_response.json()
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(active_id)]
    assert items[0]["title"] == "Public Mazda"
    assert "contact_phone" not in items[0]
    assert "vin" not in items[0]
    assert "Private draft Mazda" not in response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ListingViewEvent)) == 0


def test_public_comparison_rejects_more_than_four_ids(integration):
    response = integration["client"].get(
        "/api/v1/listings/compare",
        params=[("ids", str(uuid.uuid4())) for _ in range(5)],
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_comparison_size"
