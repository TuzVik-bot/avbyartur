"""Integration tests for the onliner.by mirror ingestion pipeline."""

import json
import uuid
from decimal import Decimal
from io import BytesIO

import httpx
import pytest
from app.ingest_onliner import (
    OnlinerClient,
    OnlinerFetchError,
    collect_snapshot,
    discover_new,
    import_record,
    import_snapshot,
    parse_advert,
    sync_existing,
)
from app.models import (
    AuditEvent,
    CatalogMake,
    CatalogModel,
    Listing,
    ListingPhoto,
    ListingPriceEvent,
    ListingStatusEvent,
    LocationCity,
    LocationRegion,
    User,
)
from app.security import hash_password
from PIL import Image
from sqlalchemy import select

PASSWORD = "onliner-ingest-test-password-123"


def _add_owner(factory) -> User:
    email = f"onliner-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name="Onliner Mirror",
            password_hash=hash_password(PASSWORD),
            role="user",
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _add_catalog(factory) -> None:
    with factory() as db:
        make = CatalogMake(slug="ford", name="Ford")
        db.add(make)
        db.flush()
        db.add(CatalogModel(make_id=make.id, slug="escape", name="Escape"))
        db.commit()


def _add_geo(factory) -> None:
    with factory() as db:
        region = LocationRegion(slug="minsk-region", name="Минская обл.")
        db.add(region)
        db.flush()
        db.add(LocationCity(region_id=region.id, slug="minsk", name="Минск"))
        db.commit()


def _jpeg_bytes(color=(200, 30, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (96, 64), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _detail(**overrides) -> dict:
    detail = {
        "id": 5071635,
        "title": "Ford Escape (IV)",
        "manufacturer": {"id": 19, "name": "Ford", "slug": "ford"},
        "model": {"id": 572, "name": "Escape", "slug": "escape"},
        "generation": {"id": 6548, "name": "(IV)", "slug": "4-pokolenie"},
        "specs": {
            "transmission": "automatic",
            "color": "black",
            "odometer": {"unit": "km", "value": 64000},
            "year": 2022,
            "engine": {
                "hybrid": False,
                "gas": False,
                "type": "gasoline",
                "capacity": 1.5,
                "power": {"value": 180, "unit": "horse"},
            },
            "body_type": "suv",
            "state": "owned",
            "drivetrain": "all",
            "has_vin": True,
        },
        "equipment": [
            {
                "id": "multimedia",
                "name": "Мультимедиа",
                "items": [{"id": "carplay", "name": "CarPlay", "value": True}],
            }
        ],
        "seller": {
            "call": {"from": "09:00+03:00", "to": "21:00+03:00"},
            "name": "Александр",
            "phones": ["+37544*******"],
            "type": "individual",
        },
        "price": {
            "amount": "18700.00",
            "currency": "USD",
            "converted": {"BYN": {"amount": "55245.41", "currency": "BYN"}},
        },
        "deal_terms": {
            "include_vat": False,
            "exchange": False,
            "customs_clearance": True,
        },
        "location": {
            "country": {"name": "Беларусь", "id": 248},
            "city": {"name": "Минск", "id": 269},
            "region": {"name": "Минская обл.", "id": 349},
        },
        "images": [
            {"original": "https://content.onliner.by/automarket/1/original/a.jpg"},
            {"original": "https://content.onliner.by/automarket/1/original/b.jpg"},
        ],
        "description": "Вся в родной краске!",
        "created_at": "2026-08-15T00:03:44+03:00",
        "updated_at": "2026-09-23T20:23:34+03:00",
        "closed_at": None,
        "url": "https://ab.api.onliner.by/adverts/5071635",
        "html_url": "https://ab.onliner.by/ford/escape/5071635",
    }
    detail.update(overrides)
    return detail


class _FakeImageClient:
    """Only download_image, for photo pipeline tests."""

    def __init__(self, payloads: dict[str, bytes]) -> None:
        self._payloads = payloads

    def download_image(self, url: str, *, max_bytes: int) -> bytes:
        payload = self._payloads.get(url)
        if payload is None:
            raise OnlinerFetchError(f"missing image {url}")
        return payload


class _FakeSourceClient:
    """dictionaries/search/advert/phones for sync and discovery tests."""

    def __init__(
        self, *, dictionaries=None, search=None, adverts=None, phones=None
    ) -> None:
        self._dictionaries = dictionaries or {}
        self._search = {int(key): value for key, value in (search or {}).items()}
        self._adverts = adverts or {}
        self._phones = phones or {}

    def dictionaries(self) -> dict:
        return self._dictionaries

    def search_used(self, manufacturer_id, *, limit, page=1) -> dict:
        return self._search.get(int(manufacturer_id), {"adverts": [], "total": 0})

    def get_advert(self, advert_id):
        return self._adverts.get(str(advert_id))

    def get_phones(self, advert_id) -> list:
        return self._phones.get(str(advert_id), ["+375447976309"])

    def download_image(self, url: str, *, max_bytes: int) -> bytes:
        return _jpeg_bytes()


def _mock_client(handler) -> OnlinerClient:
    return OnlinerClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda seconds: None,
    )


# --- parsing ---------------------------------------------------------------


def test_parse_advert_maps_fields():
    record = parse_advert(_detail(), ["+375447976309"])
    assert record.source_id == "5071635"
    assert record.slug == "onliner-5071635"
    assert record.manufacturer_slug == "ford"
    assert record.model_slug == "escape"
    assert record.generation_name == "(IV)"
    assert record.year == 2022
    assert record.mileage_km == 64000
    assert record.fuel == "petrol"
    assert record.transmission == "automatic"
    assert record.drive == "all"
    assert record.condition == "used"
    assert record.damaged is False
    assert record.color == "black"
    assert record.engine_volume_l == Decimal("1.5")
    assert record.power_hp == 180
    assert record.price_amount == Decimal("18700.00")
    assert record.currency == "USD"
    assert record.exchange is False
    assert record.customs_status == "cleared_rb"
    assert record.seller_name == "Александр"
    assert record.contact_phone == "+375447976309"
    assert record.call_hours == "09:00–21:00"
    assert record.city_name == "Минск"
    assert record.region_name == "Минская обл."
    assert record.equipment_ids == ("carplay",)
    assert len(record.image_urls) == 2
    assert record.title == "Ford Escape 2022"


def test_parse_advert_maps_emergency_state_to_damaged():
    specs = dict(_detail()["specs"], state="emergency")
    record = parse_advert(_detail(specs=specs), [])
    assert record.condition == "used"
    assert record.damaged is True


def test_parse_advert_eur_price_falls_back_to_usd():
    detail = _detail(
        price={
            "amount": "10000.00",
            "currency": "EUR",
            "converted": {"USD": {"amount": "11000.00", "currency": "USD"}},
        }
    )
    record = parse_advert(detail, [])
    assert record.currency == "USD"
    assert record.price_amount == Decimal("11000.00")


def test_parse_advert_requires_usable_price():
    with pytest.raises(ValueError):
        parse_advert(_detail(price={"amount": "0", "currency": "USD"}), [])
    with pytest.raises(ValueError):
        parse_advert(_detail(id=None), [])


# --- HTTP client -----------------------------------------------------------


def test_client_maps_404_to_none():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(("/adverts/42", "/vehicles/42/phones"))
        return httpx.Response(404, json={"message": "not found"})

    with _mock_client(handler) as client:
        assert client.get_advert(42) is None
        assert client.get_phones(42) == []


def test_client_search_sends_source_filter_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"adverts": [], "total": 0, "page": {}})

    with _mock_client(handler) as client:
        client.search_used(19, limit=10)
    assert "state%5B%5D=owned" in captured["url"]
    assert "car%5B0%5D%5Bmanufacturer%5D=19" in captured["url"]
    assert "limit=10" in captured["url"]


def test_client_retries_transient_errors():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=[])

    with _mock_client(handler) as client:
        assert client.get_phones(7) == []
    assert attempts["count"] == 3


def test_client_raises_on_permanent_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={})

    with _mock_client(handler) as client:
        with pytest.raises(OnlinerFetchError):
            client.get_advert(1)


# --- import -----------------------------------------------------------------


def test_import_record_publishes_active_listing(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    with factory() as db:
        owner_db = db.get(User, owner.id)
        assert import_record(db, record, owner_db) == "imported"
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        assert listing is not None
        assert listing.status == "active"
        assert listing.category_code == "cars"
        assert listing.make_id is not None
        assert listing.model_id is not None
        assert listing.make_name_snapshot == "Ford"
        assert listing.model_name_snapshot == "Escape"
        assert listing.city_id is not None
        assert listing.region_id is not None
        assert listing.manual_city is None
        assert listing.contact_phone == "+375447976309"
        assert listing.call_hours == "09:00–21:00"
        assert listing.price_amount == Decimal("18700.00")
        assert listing.currency == "USD"
        assert "Onlíner" in listing.description
        assert "ab.onliner.by" in listing.description
        price_events = db.scalars(
            select(ListingPriceEvent).where(ListingPriceEvent.listing_id == listing.id)
        ).all()
        assert [event.event_type for event in price_events] == ["published"]
        status_events = db.scalars(
            select(ListingStatusEvent).where(
                ListingStatusEvent.listing_id == listing.id
            )
        ).all()
        assert [
            (event.from_status, event.to_status, event.actor_kind)
            for event in status_events
        ] == [("draft", "active", "import")]
        audit = db.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_id == listing.id,
                AuditEvent.action == "imported_onliner_listing",
            )
        ).all()
        assert len(audit) == 1


def test_import_record_is_idempotent(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    with factory() as db:
        owner_db = db.get(User, owner.id)
        assert import_record(db, record, owner_db) == "imported"
        assert import_record(db, record, owner_db) == "existing"
        listings = db.scalars(
            select(Listing).where(Listing.slug == "onliner-5071635")
        ).all()
        assert len(listings) == 1
        price_events = db.scalars(
            select(ListingPriceEvent).where(
                ListingPriceEvent.listing_id == listings[0].id
            )
        ).all()
        assert len(price_events) == 1


def test_import_record_purges_unfinished_draft(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    with factory() as db:
        owner_db = db.get(User, owner.id)
        assert import_record(db, record, owner_db) == "imported"
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        listing.status = "draft"
        db.commit()
    with factory() as db:
        owner_db = db.get(User, owner.id)
        assert import_record(db, record, owner_db) == "imported"
        listings = db.scalars(
            select(Listing).where(Listing.slug == "onliner-5071635")
        ).all()
        assert len(listings) == 1
        assert listings[0].status == "active"


def test_import_record_processes_photos(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    fake_client = _FakeImageClient(
        {
            "https://content.onliner.by/automarket/1/original/a.jpg": _jpeg_bytes(
                (200, 30, 30)
            ),
            "https://content.onliner.by/automarket/1/original/b.jpg": _jpeg_bytes(
                (30, 30, 200)
            ),
        }
    )
    media_root = integration["media_root"]
    with factory() as db:
        owner_db = db.get(User, owner.id)
        assert import_record(db, record, owner_db, client=fake_client) == "imported"
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        photos = db.scalars(
            select(ListingPhoto)
            .where(ListingPhoto.listing_id == listing.id)
            .order_by(ListingPhoto.position)
        ).all()
        assert [photo.status for photo in photos] == ["ready", "ready"]
        assert photos[0].is_cover is True
        assert photos[1].is_cover is False
        for photo in photos:
            for edge in (320, 768, 1600):
                assert (media_root / photo.storage_name / f"{edge}.webp").is_file()


def test_import_record_skips_broken_photos(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    fake_client = _FakeImageClient(
        {
            "https://content.onliner.by/automarket/1/original/a.jpg": b"not-an-image",
            "https://content.onliner.by/automarket/1/original/b.jpg": _jpeg_bytes(),
        }
    )
    with factory() as db:
        owner_db = db.get(User, owner.id)
        assert import_record(db, record, owner_db, client=fake_client) == "imported"
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        photos = db.scalars(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing.id)
        ).all()
        assert len(photos) == 1
        assert photos[0].status == "ready"


def test_import_snapshot_dry_run_and_limit(integration, tmp_path):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    snapshot = tmp_path / "snapshot.jsonl"
    rows = []
    for index in range(3):
        detail = _detail(id=5071600 + index)
        rows.append(json.dumps({"detail": detail, "phones": ["+375447976309"]}))
    snapshot.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with factory() as db:
        owner_db = db.get(User, owner.id)
        dry = import_snapshot(db, snapshot, owner_db, dry_run=True)
        assert dry["requested"] == 3
        assert dry["imported"] == 3
        assert dry["existing"] == 0
        limited = import_snapshot(db, snapshot, owner_db, client=None, limit=2)
        assert limited["imported"] == 2
        assert limited["without_photos"] == 2
        listings = db.scalars(
            select(Listing).where(Listing.slug.like("onliner-%"))
        ).all()
        assert len(listings) == 2


# --- sync -------------------------------------------------------------------


def test_sync_existing_updates_price(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    with factory() as db:
        owner_db = db.get(User, owner.id)
        import_record(db, record, owner_db)
    cheaper = _detail(price={"amount": "18000.00", "currency": "USD"})
    client = _FakeSourceClient(adverts={"5071635": cheaper})
    with factory() as db:
        stats = sync_existing(db, client)
        assert stats["checked"] == 1
        assert stats["price_updates"] == 1
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        assert listing.price_amount == Decimal("18000.00")
        events = db.scalars(
            select(ListingPriceEvent)
            .where(ListingPriceEvent.listing_id == listing.id)
            .order_by(ListingPriceEvent.revision)
        ).all()
        assert [event.event_type for event in events] == ["published", "changed"]
        assert events[1].previous_price_amount == Decimal("18700.00")


def test_sync_existing_pauses_closed_and_reopens(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    with factory() as db:
        owner_db = db.get(User, owner.id)
        import_record(db, record, owner_db)
    closed = _detail(closed_at="2026-10-24T00:00:00+03:00")
    with factory() as db:
        stats = sync_existing(db, _FakeSourceClient(adverts={"5071635": closed}))
        assert stats["closed"] == 1
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        assert listing.status == "paused"
        event = db.scalar(
            select(ListingStatusEvent).where(
                ListingStatusEvent.listing_id == listing.id,
                ListingStatusEvent.to_status == "paused",
            )
        )
        assert event.reason == "closed_on_source"
    with factory() as db:
        stats = sync_existing(db, _FakeSourceClient(adverts={"5071635": None}))
        assert stats["closed"] == 0
        assert stats["unchanged"] == 1
    with factory() as db:
        stats = sync_existing(db, _FakeSourceClient(adverts={"5071635": _detail()}))
        assert stats["reopened"] == 1
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        assert listing.status == "active"


def test_sync_existing_reports_fetch_errors(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    record = parse_advert(_detail(), ["+375447976309"])
    with factory() as db:
        owner_db = db.get(User, owner.id)
        import_record(db, record, owner_db)

    class _BrokenClient:
        def get_advert(self, advert_id):
            raise OnlinerFetchError("network down")

    with factory() as db:
        stats = sync_existing(db, _BrokenClient())
        assert stats["errors"] == 1
        listing = db.scalar(select(Listing).where(Listing.slug == "onliner-5071635"))
        assert listing.status == "active"


# --- discovery and collection ----------------------------------------------


def test_discover_new_imports_and_skips_existing(integration):
    factory = integration["SessionLocal"]
    owner = _add_owner(factory)
    _add_catalog(factory)
    _add_geo(factory)
    client = _FakeSourceClient(
        dictionaries={"manufacturer": [{"id": 19, "name": "Ford", "slug": "ford"}]},
        search={19: {"adverts": [{"id": 5071635}], "total": 1}},
        adverts={"5071635": _detail()},
        phones={"5071635": ["+375447976309"]},
    )
    with factory() as db:
        owner_db = db.get(User, owner.id)
        first = discover_new(db, client, owner_db)
        assert first["imported"] == 1
        second = discover_new(db, client, owner_db)
        assert second["existing"] == 1
        assert second["imported"] == 0
        listings = db.scalars(
            select(Listing).where(Listing.slug.like("onliner-%"))
        ).all()
        assert len(listings) == 1


def test_collect_snapshot_writes_jsonl(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/dictionaries"):
            return httpx.Response(
                200,
                json={"manufacturer": [{"id": 19, "name": "Ford", "slug": "ford"}]},
            )
        if path.endswith("/search/vehicles"):
            return httpx.Response(
                200, json={"adverts": [{"id": 5071635}], "total": 1, "page": {}}
            )
        if path.endswith("/adverts/5071635"):
            return httpx.Response(200, json=_detail())
        if path.endswith("/phones"):
            return httpx.Response(200, json=["+375447976309"])
        return httpx.Response(404, json={"message": "unknown"})

    output = tmp_path / "snapshot.jsonl"
    with _mock_client(handler) as client:
        stats = collect_snapshot(client, output, per_make_limit=10)
    assert stats["makes"] == 1
    assert stats["written"] == 1
    rows = [
        json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["detail"]["id"] == 5071635
    assert rows[0]["phones"] == ["+375447976309"]
