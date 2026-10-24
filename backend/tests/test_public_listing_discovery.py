import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.models import CatalogMake, CatalogModel, Company, ExchangeRate, Listing, ListingViewEvent, User


def _add_user(factory, *, status: str = "active") -> User:
    user = User(
        email=f"discovery-{uuid.uuid4().hex[:12]}@example.com",
        display_name="Discovery seller",
        role="user",
        status=status,
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _add_company(factory, owner_id: uuid.UUID, *, status: str) -> Company:
    company = Company(
        owner_id=owner_id,
        name="Discovery company",
        slug=f"discovery-{uuid.uuid4().hex[:12]}",
        unp="123456789",
        address="Минск",
        phone="+375291234567",
        status=status,
    )
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        db.expunge(company)
    return company


def _add_listing(
    factory,
    owner_id: uuid.UUID,
    *,
    status: str = "active",
    category_code: str = "cars",
    make_id: uuid.UUID | None = None,
    model_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    make_name_snapshot: str = "Mazda",
    model_name_snapshot: str = "3",
    price_amount: str | None = "32000",
    currency: str | None = "BYN",
    created_at: datetime | None = None,
) -> Listing:
    listing = Listing(
        owner_id=owner_id,
        company_id=company_id,
        slug=f"discovery-{uuid.uuid4().hex}",
        status=status,
        category_code=category_code,
        revision=1,
        title="Mazda listing",
        description="Public listing for discovery tests.",
        contact_phone="+375291234567",
        vin="JM1BL1SF8A1234567",
        make_id=make_id,
        model_id=model_id,
        make_name_snapshot=make_name_snapshot,
        model_name_snapshot=model_name_snapshot,
        year=2020,
        mileage_km=50000,
        price_amount=Decimal(price_amount) if price_amount is not None else None,
        currency=currency,
        damaged=False,
        parts_only=False,
        created_at=created_at,
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _add_catalog(factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    make = CatalogMake(slug=f"mazda-{uuid.uuid4().hex[:8]}", name="Mazda", aliases=[])
    with factory() as db:
        db.add(make)
        db.flush()
        model3 = CatalogModel(make_id=make.id, slug="3", name="3", aliases=[])
        model6 = CatalogModel(make_id=make.id, slug="6", name="6", aliases=[])
        db.add_all([model3, model6])
        db.commit()
        return make.id, model3.id, model6.id


def test_related_listings_rank_same_model_and_budget_and_keep_only_public_category(integration):
    factory = integration["SessionLocal"]
    make_id, model3_id, model6_id = _add_catalog(factory)
    unrelated_make = CatalogMake(slug=f"unrelated-{uuid.uuid4().hex[:8]}", name="Other", aliases=[])
    with factory() as db:
        db.add(unrelated_make)
        db.flush()
        unrelated_model = CatalogModel(make_id=unrelated_make.id, slug="3", name="3", aliases=[])
        db.add(unrelated_model)
        db.commit()
        unrelated_make_id = unrelated_make.id
        unrelated_model_id = unrelated_model.id
    target_owner = _add_user(factory)
    target = _add_listing(factory, target_owner.id, make_id=make_id, model_id=model3_id)

    # At 3.2 BYN/USD, the older USD listing is the closest in a common currency.
    usd_exact_budget = _add_listing(
        factory,
        _add_user(factory).id,
        make_id=make_id,
        model_id=model3_id,
        price_amount="10000",
        currency="USD",
        created_at=datetime.now(UTC) - timedelta(days=5),
    )
    byn_near_budget = _add_listing(
        factory,
        _add_user(factory).id,
        make_id=make_id,
        model_id=model3_id,
        price_amount="31000",
        currency="BYN",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    same_make = _add_listing(
        factory,
        _add_user(factory).id,
        make_id=make_id,
        model_id=model6_id,
        model_name_snapshot="6",
        price_amount="32000",
        created_at=datetime.now(UTC),
    )
    same_model_name_other_make = _add_listing(
        factory,
        _add_user(factory).id,
        make_id=unrelated_make_id,
        model_id=unrelated_model_id,
        make_name_snapshot="Other",
    )
    wrong_category = _add_listing(
        factory,
        _add_user(factory).id,
        make_id=make_id,
        model_id=model3_id,
        category_code="parts",
    )
    inactive_owner = _add_user(factory, status="disabled")
    hidden_seller = _add_listing(factory, inactive_owner.id, make_id=make_id, model_id=model3_id)
    pending_owner = _add_user(factory)
    pending_company = _add_company(factory, pending_owner.id, status="pending")
    hidden_company = _add_listing(
        factory,
        pending_owner.id,
        make_id=make_id,
        model_id=model3_id,
        company_id=pending_company.id,
    )
    _add_listing(factory, _add_user(factory).id, status="draft", make_id=make_id, model_id=model3_id)
    with factory() as db:
        db.add(ExchangeRate(
            currency="USD",
            rate_date=datetime.now(UTC).date().isoformat(),
            official_rate=Decimal("3.2"),
            scale=1,
            source="isolated discovery fixture",
            fetched_at=datetime.now(UTC),
        ))
        db.commit()

    response = integration["client"].get(f"/api/v1/listings/{target.id}/related")

    assert response.status_code == 200, response.text
    rows = response.json()["items"]
    ids = [row["id"] for row in rows]
    assert ids[:3] == [str(usd_exact_budget.id), str(byn_near_budget.id), str(same_make.id)]
    assert str(wrong_category.id) not in ids
    assert str(same_model_name_other_make.id) not in ids
    assert str(hidden_seller.id) not in ids
    assert str(hidden_company.id) not in ids
    assert len(rows) <= 8
    assert all(row["status"] == "active" for row in rows)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ListingViewEvent)) == 0


def test_related_listings_return_at_most_eight_candidates(integration):
    factory = integration["SessionLocal"]
    make_id, model_id, _ = _add_catalog(factory)
    target = _add_listing(factory, _add_user(factory).id, make_id=make_id, model_id=model_id)
    for _ in range(10):
        _add_listing(factory, _add_user(factory).id, make_id=make_id, model_id=model_id)

    response = integration["client"].get(f"/api/v1/listings/{target.id}/related")

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 8


def test_recent_batch_preserves_order_and_returns_only_public_active_listings_without_views(integration):
    factory = integration["SessionLocal"]
    make_id, model_id, _ = _add_catalog(factory)
    active_a = _add_listing(factory, _add_user(factory).id, make_id=make_id, model_id=model_id)
    active_b = _add_listing(factory, _add_user(factory).id, make_id=make_id, model_id=model_id)
    draft = _add_listing(factory, _add_user(factory).id, status="draft", make_id=make_id, model_id=model_id)
    sold = _add_listing(factory, _add_user(factory).id, status="sold", make_id=make_id, model_id=model_id)
    inactive_owner = _add_user(factory, status="disabled")
    hidden = _add_listing(factory, inactive_owner.id, make_id=make_id, model_id=model_id)
    pending_owner = _add_user(factory)
    pending_company = _add_company(factory, pending_owner.id, status="pending")
    hidden_company = _add_listing(
        factory,
        pending_owner.id,
        make_id=make_id,
        model_id=model_id,
        company_id=pending_company.id,
    )
    ids = [active_b.id, draft.id, active_a.id, hidden.id, hidden_company.id, sold.id, active_b.id]

    response = integration["client"].get(
        "/api/v1/listings/recent",
        params=[("ids", str(listing_id)) for listing_id in ids],
    )

    assert response.status_code == 200, response.text
    rows = response.json()["items"]
    assert [row["id"] for row in rows] == [str(active_b.id), str(active_a.id)]
    assert "contact_phone" not in rows[0]
    assert "vin" not in rows[0]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ListingViewEvent)) == 0


def test_recent_batch_rejects_more_than_twelve_ids(integration):
    response = integration["client"].get(
        "/api/v1/listings/recent",
        params=[("ids", str(uuid.uuid4())) for _ in range(13)],
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_recent_size"
