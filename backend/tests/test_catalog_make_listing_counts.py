import uuid

from app.models import CatalogMake, Company, Listing, User
from tests.test_pilot_api import add_user


def _listing(owner_id, make_id, status="active", company_id=None, category_code="cars") -> Listing:
    return Listing(
        owner_id=owner_id,
        company_id=company_id,
        make_id=make_id,
        category_code=category_code,
        slug=f"make-count-{uuid.uuid4().hex}",
        status=status,
        revision=1,
        submitted_revision=1,
        title="Make count listing",
        year=2019,
        mileage_km=90000,
        contact_phone="+375291234567",
        damaged=False,
        parts_only=False,
        description="Listing used to verify public make counters.",
    )


def _count(client, make_id) -> int | None:
    response = client.get("/api/v1/catalog/makes", params={"limit": 200})
    assert response.status_code == 200, response.text
    return next(item["listing_count"] for item in response.json()["items"] if item["id"] == str(make_id))


def test_make_listing_count_includes_only_publicly_visible_cars(integration):
    factory = integration["SessionLocal"]
    client = integration["client"]
    suffix = uuid.uuid4().hex[:8]
    owner = add_user(factory, f"make-count-owner-{suffix}@example.com")
    blocked_owner = add_user(factory, f"make-count-blocked-{suffix}@example.com")
    pending_owner = add_user(factory, f"make-count-pending-{suffix}@example.com")
    with factory() as db:
        make = CatalogMake(slug=f"make-count-{suffix}", name=f"Make Count {suffix}", aliases=[])
        db.add(make)
        db.get(User, blocked_owner.id).status = "blocked"
        approved = Company(owner_id=owner.id, name=f"Approved {suffix}", slug=f"approved-{suffix}", unp=f"{uuid.uuid4().int % 10**9:09d}", address="Minsk", phone="+375291111111", status="approved")
        pending = Company(owner_id=pending_owner.id, name=f"Pending {suffix}", slug=f"pending-{suffix}", unp=f"{uuid.uuid4().int % 10**9:09d}", address="Minsk", phone="+375291111112", status="pending")
        db.add_all([approved, pending])
        db.flush()
        make_id = make.id
        assert make_id is not None
        db.add_all([
            _listing(owner.id, make_id),
            _listing(owner.id, make_id, company_id=approved.id),
            *[_listing(owner.id, make_id, status=status) for status in ("draft", "pending_review", "blocked", "archived", "sold")],
            _listing(pending_owner.id, make_id, company_id=pending.id),
            _listing(blocked_owner.id, make_id),
            _listing(owner.id, make_id, category_code="trucks"),
        ])
        db.commit()

    assert _count(client, make_id) == 2
    search = client.get("/api/v1/listings", params={"make_id": str(make_id)})
    assert search.status_code == 200, search.text
    assert len(search.json()["items"]) == _count(client, make_id)


def test_make_listing_count_is_zero_without_listings(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        make = CatalogMake(slug=f"empty-make-{uuid.uuid4().hex[:8]}", name="Empty Make", aliases=[])
        db.add(make)
        db.commit()
        make_id = make.id
    assert _count(integration["client"], make_id) == 0
