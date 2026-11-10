import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.api import listings as listings_api
from app.models import Listing, ListingPriceEvent, User
from app.security import hash_password
from fastapi.testclient import TestClient

PASSWORD = "price-drop-summary-password-123"


def _add_user(factory, label: str) -> tuple[User, str]:
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
        db.expunge(user)
    return user, email


def _add_listing(
    factory,
    owner_id,
    *,
    title: str,
    amount: str,
    currency: str = "BYN",
    status: str = "active",
    published_at=None,
) -> Listing:
    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            slug=f"price-drop-{uuid.uuid4().hex}",
            status=status,
            revision=3,
            title=title,
            description="Price drop summary fixture.",
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
            make_name_snapshot="Mazda",
            model_name_snapshot="3",
            year=2018,
            price_amount=Decimal(amount),
            currency=currency,
            published_at=published_at,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def _add_event(
    factory,
    listing_id,
    *,
    revision: int,
    amount: str,
    currency: str,
    previous: str | None,
    previous_currency: str | None,
    age: timedelta,
) -> None:
    with factory() as db:
        db.add(
            ListingPriceEvent(
                listing_id=listing_id,
                revision=revision,
                event_type="changed" if previous is not None else "published",
                price_amount=Decimal(amount),
                currency=currency,
                previous_price_amount=Decimal(previous)
                if previous is not None
                else None,
                previous_currency=previous_currency,
                created_at=datetime.now(timezone.utc) - age,
            )
        )
        db.commit()


def _client(integration) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver")


def _items_by_id(response) -> dict[str, dict]:
    assert response.status_code == 200, response.text
    return {item["id"]: item for item in response.json()["items"]}


def _seed_price_scenarios(factory):
    owner, _email = _add_user(factory, "price-drop-owner")
    now = datetime.now(timezone.utc)
    dropped = _add_listing(
        factory,
        owner.id,
        title="Dropped",
        amount="9000.00",
        published_at=now - timedelta(days=40),
    )
    _add_event(
        factory,
        dropped.id,
        revision=1,
        amount="10000.00",
        currency="BYN",
        previous=None,
        previous_currency=None,
        age=timedelta(days=40),
    )
    _add_event(
        factory,
        dropped.id,
        revision=2,
        amount="9000.00",
        currency="BYN",
        previous="10000.00",
        previous_currency="BYN",
        age=timedelta(days=2),
    )

    raised = _add_listing(
        factory,
        owner.id,
        title="Raised",
        amount="11000.00",
        published_at=now - timedelta(days=1),
    )
    _add_event(
        factory,
        raised.id,
        revision=1,
        amount="10000.00",
        currency="BYN",
        previous="12000.00",
        previous_currency="BYN",
        age=timedelta(days=5),
    )
    _add_event(
        factory,
        raised.id,
        revision=2,
        amount="11000.00",
        currency="BYN",
        previous="10000.00",
        previous_currency="BYN",
        age=timedelta(days=1),
    )

    stale = _add_listing(
        factory,
        owner.id,
        title="Stale drop",
        amount="8000.00",
        published_at=now - timedelta(days=90),
    )
    _add_event(
        factory,
        stale.id,
        revision=1,
        amount="8000.00",
        currency="BYN",
        previous="9000.00",
        previous_currency="BYN",
        age=timedelta(days=45),
    )

    currency_switch = _add_listing(
        factory,
        owner.id,
        title="Currency switch",
        amount="3000.00",
        currency="USD",
        published_at=now - timedelta(days=3),
    )
    _add_event(
        factory,
        currency_switch.id,
        revision=1,
        amount="3000.00",
        currency="USD",
        previous="9000.00",
        previous_currency="BYN",
        age=timedelta(days=3),
    )

    fresh = _add_listing(
        factory,
        owner.id,
        title="Fresh without events",
        amount="7000.00",
        published_at=now,
    )
    return dropped, raised, stale, currency_switch, fresh


def test_search_summary_exposes_only_a_recent_same_currency_latest_drop(integration):
    dropped, raised, stale, currency_switch, fresh = _seed_price_scenarios(
        integration["SessionLocal"]
    )

    items = _items_by_id(
        _client(integration).get("/api/v1/listings", params={"page_size": 25})
    )

    drop = items[str(dropped.id)]["last_price_drop"]
    assert drop["amount"] == "9000.00"
    assert drop["previous_amount"] == "10000.00"
    assert drop["currency"] == "BYN"
    assert datetime.fromisoformat(drop["changed_at"]) > datetime.now(
        timezone.utc
    ) - timedelta(days=3)
    for listing in (raised, stale, currency_switch, fresh):
        assert items[str(listing.id)].get("last_price_drop") is None


def test_price_drop_sort_lists_recent_drops_first_then_newest_without_currency(
    integration,
):
    dropped, raised, stale, currency_switch, fresh = _seed_price_scenarios(
        integration["SessionLocal"]
    )

    response = _client(integration).get(
        "/api/v1/listings", params={"sort": "price_drop", "page_size": 25}
    )

    assert response.status_code == 200, response.text
    order = [item["id"] for item in response.json()["items"]]
    assert order[0] == str(dropped.id)
    assert order[1:] == [
        str(fresh.id),
        str(raised.id),
        str(currency_switch.id),
        str(stale.id),
    ]
    count = _client(integration).get(
        "/api/v1/listings/count", params={"sort": "price_drop"}
    )
    assert count.status_code == 200, count.text
    assert count.json()["total"] == 5


def test_owner_listings_carry_market_comparison_with_signed_percent_for_active_only(
    integration, monkeypatch
):
    factory = integration["SessionLocal"]
    owner, email = _add_user(factory, "market-owner")
    active = _add_listing(factory, owner.id, title="Active above", amount="12000.00")
    below = _add_listing(factory, owner.id, title="Active below", amount="8500.00")
    draft = _add_listing(
        factory, owner.id, title="Draft", amount="9000.00", status="draft"
    )
    compared: list[set[str]] = []

    in_market_flags: list[bool] = []

    def fake_comparisons(_db, listings, _rate_info, *, include_in_market=False):
        compared.append({str(listing.id) for listing in listings})
        in_market_flags.append(include_in_market)
        result = {listing.id: None for listing in listings}
        common = {
            "median_byn": "10000.00",
            "sample_size": 12,
            "seller_count": 6,
            "as_of": "2026-11-10T00:00:00+00:00",
            "rate_date": None,
        }
        result[active.id] = {"label": "above_market", **common}
        result[below.id] = {"label": "below_market", **common}
        return result

    monkeypatch.setattr(listings_api, "build_market_comparisons", fake_comparisons)
    client = _client(integration)
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert login.status_code == 200, login.text

    items = _items_by_id(client.get("/api/v1/me/listings"))

    assert compared == [{str(active.id), str(below.id)}]
    assert in_market_flags == [True]
    assert (
        items[str(active.id)]["price"]["market_comparison"]["difference_percent"] == 20
    )
    assert (
        items[str(below.id)]["price"]["market_comparison"]["difference_percent"] == -15
    )
    assert items[str(draft.id)]["price"].get("market_comparison") is None
