from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main
from app.api import listings as listings_api
from app.api.dependencies import get_current_user, require_csrf
from app.db import get_db


def test_market_estimate_api_requires_write_dependencies_and_returns_aggregate(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    rate_limits = []
    captured = {}
    monkeypatch.setattr(listings_api, "consume_rate_limit", lambda db, namespace, subject, limit, period: rate_limits.append((namespace, subject, limit)))
    monkeypatch.setattr(listings_api, "seller_company", lambda db, current_user, requested_type: None)
    monkeypatch.setattr(listings_api, "latest_listing_exchange_rate", lambda db: (None, False))

    def estimate(db, target, rate_info):
        captured["target"] = target
        return {"median_byn": "20000.00", "sample_size": 12, "seller_count": 7, "as_of": "2026-10-15T00:00:00Z", "rate_date": None}

    monkeypatch.setattr(listings_api, "build_market_estimate", estimate)
    app = main.app
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_csrf] = lambda: object()
    app.dependency_overrides[get_db] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/listings/market-price-estimate", json={
                "seller_type": "private", "make_id": str(uuid4()), "model_id": str(uuid4()),
                "body_type_id": str(uuid4()), "year": 2020, "mileage_km": 50000,
                "condition": "used", "fuel": "petrol", "transmission": "manual",
                "damaged": False, "parts_only": False,
            })
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "available": True, "median_byn": "20000.00", "sample_size": 12,
        "seller_count": 7, "as_of": "2026-10-15T00:00:00Z", "rate_date": None,
    }
    assert {item[0] for item in rate_limits} == {"market-price-estimate-user", "market-price-estimate-ip"}
    assert captured["target"].owner_id == user.id
    assert not hasattr(captured["target"], "vin")
