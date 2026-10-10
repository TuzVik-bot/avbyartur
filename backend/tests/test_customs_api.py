from datetime import date

from fastapi.testclient import TestClient

from app.api import customs_calculator as customs_api
from app.main import app


client = TestClient(app)
META_PATH = "/api/v1/customs-calculator/meta"
CALCULATE_PATH = "/api/v1/customs-calculator/calculate"
RATES_PATH = "/api/v1/customs-calculator/rates"


def _request_body(**overrides):
    return {
        "price_amount": "8500",
        "currency": "EUR",
        "manufacture_date": "2023-10-04",
        "engine_type": "petrol",
        "engine_volume_cc": 1600,
        "personal_use": True,
        "origin_outside_eaeu": True,
        **overrides,
    }


def test_meta_has_the_exact_public_contract_and_does_not_fetch_rates(monkeypatch) -> None:
    monkeypatch.setattr(
        customs_api,
        "get_nbrb_rates",
        lambda *_: (_ for _ in ()).throw(AssertionError("meta must not fetch rates")),
    )
    response = client.get(META_PATH)

    assert response.status_code == 200
    meta = response.json()
    assert set(meta) == {
        "scenario",
        "supported_currencies",
        "supported_engines",
        "calculation_available",
        "unavailable_reason",
        "rules_version",
        "verified_on",
        "sources",
        "scope_notes",
    }
    assert meta["supported_currencies"] == ["EUR", "USD", "BYN", "RUB", "CNY"]
    assert meta["supported_engines"] == ["petrol", "diesel"]
    assert meta["calculation_available"] is True
    assert meta["unavailable_reason"] is None
    assert isinstance(meta["sources"], list)
    assert any(source.startswith("https://api.nbrb.by/exrates/rates?") for source in meta["sources"])
    assert isinstance(meta["scope_notes"], list)


def test_closed_publication_gate_returns_api_error_envelope_without_rates(monkeypatch) -> None:
    rules = object()
    monkeypatch.setattr(customs_api, "get_rules_for_date", lambda _: rules)
    monkeypatch.setattr(customs_api, "is_publicly_available", lambda _: False)
    monkeypatch.setattr(
        customs_api,
        "get_nbrb_rates",
        lambda *_: (_ for _ in ()).throw(AssertionError("closed gate must not fetch rates")),
    )
    monkeypatch.setattr(customs_api, "minsk_today", lambda: date(2026, 10, 4))

    response = client.post(CALCULATE_PATH, json=_request_body())

    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"code", "message", "field_errors", "request_id"}
    assert body["code"] == "customs_rules_unverified"
    assert isinstance(body["request_id"], str)


def test_rate_failure_returns_api_error_envelope(monkeypatch) -> None:
    monkeypatch.setattr(customs_api, "get_rules_for_date", lambda _: object())
    monkeypatch.setattr(customs_api, "is_publicly_available", lambda _: True)
    monkeypatch.setattr(
        customs_api,
        "get_nbrb_rates",
        lambda *_: (_ for _ in ()).throw(customs_api.RatesUnavailable("upstream unavailable")),
    )
    monkeypatch.setattr(customs_api, "minsk_today", lambda: date(2026, 10, 4))

    response = client.post(CALCULATE_PATH, json=_request_body())

    assert response.status_code == 503
    assert response.json()["code"] == "customs_rates_unavailable"
    assert set(response.json()) == {"code", "message", "field_errors", "request_id"}


def test_public_post_returns_specified_fields_and_decimal_strings(monkeypatch) -> None:
    monkeypatch.setattr(customs_api, "get_rules_for_date", lambda _: object())
    monkeypatch.setattr(customs_api, "is_publicly_available", lambda _: True)
    monkeypatch.setattr(customs_api, "get_nbrb_rates", lambda _: object())
    monkeypatch.setattr(customs_api, "minsk_today", lambda: date(2026, 10, 4))
    monkeypatch.setattr(
        customs_api,
        "calculate_customs",
        lambda request, *, calculation_date, rates, rules: {
            "calculation_date": calculation_date,
            "rules_version": "test-rules-v1",
            "age_band": "up_to_3_years",
            "customs_value_eur": "8500.00",
            "duty_eur": "4590.00",
            "duty_byn": "13770.00",
            "recycling_fee_byn": "5.25",
            "customs_fee_byn": "1.20",
            "total_byn": "13776.45",
            "rate_date": calculation_date,
            "rates_used": [
                {
                    "currency": "EUR",
                    "official_rate": "3",
                    "scale": 1,
                    "byn_per_unit": "3",
                }
            ],
            "sources": ["https://example.org/test-only-rules"],
            "warnings": [],
        },
    )

    response = client.post(CALCULATE_PATH, json=_request_body())

    assert response.status_code == 200
    result = response.json()
    assert set(result) == {
        "calculation_date",
        "rules_version",
        "age_band",
        "customs_value_eur",
        "duty_eur",
        "duty_byn",
        "recycling_fee_byn",
        "customs_fee_byn",
        "total_byn",
        "rate_date",
        "rates_used",
        "sources",
        "warnings",
    }
    assert result["duty_eur"] == "4590.00"
    assert result["total_byn"] == "13776.45"
    assert result["rates_used"][0]["scale"] == 1


def test_rates_endpoint_returns_all_official_currencies_for_one_date(monkeypatch) -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    snapshot_date = date(2026, 10, 4)
    snapshot = SimpleNamespace(
        rate_date=snapshot_date,
        rates={
            "EUR": SimpleNamespace(official_rate=Decimal("3.50"), scale=1, byn_per_unit=Decimal("3.50")),
            "USD": SimpleNamespace(official_rate=Decimal("3.21"), scale=1, byn_per_unit=Decimal("3.21")),
            "BYN": SimpleNamespace(official_rate=Decimal("1"), scale=1, byn_per_unit=Decimal("1")),
            "RUB": SimpleNamespace(official_rate=Decimal("3.50"), scale=100, byn_per_unit=Decimal("0.035")),
            "CNY": SimpleNamespace(official_rate=Decimal("4.50"), scale=10, byn_per_unit=Decimal("0.45")),
        },
    )
    monkeypatch.setattr(customs_api, "get_nbrb_rates", lambda _: snapshot)
    monkeypatch.setattr(customs_api, "minsk_today", lambda: snapshot_date)

    response = client.get(RATES_PATH)

    assert response.status_code == 200
    assert response.json() == {
        "rate_date": "2026-10-04",
        "rates": [
            {"currency": "EUR", "official_rate": "3.50", "scale": 1, "byn_per_unit": "3.50"},
            {"currency": "USD", "official_rate": "3.21", "scale": 1, "byn_per_unit": "3.21"},
            {"currency": "BYN", "official_rate": "1", "scale": 1, "byn_per_unit": "1"},
            {"currency": "RUB", "official_rate": "3.50", "scale": 100, "byn_per_unit": "0.035"},
            {"currency": "CNY", "official_rate": "4.50", "scale": 10, "byn_per_unit": "0.45"},
        ],
    }


def test_invalid_request_is_returned_in_api_error_contract() -> None:
    response = client.post(CALCULATE_PATH, json=_request_body(personal_use=False))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert set(response.json()) == {"code", "message", "field_errors", "request_id"}


def test_openapi_documents_decimal_string_input_and_customs_endpoints() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    assert META_PATH in paths
    assert CALCULATE_PATH in paths
    assert RATES_PATH in paths
    request_schema = paths[CALCULATE_PATH]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("CustomsCalculationRequest")
    properties = schema["components"]["schemas"]["CustomsCalculationRequest"]["properties"]
    assert properties["price_amount"]["type"] == "string"
    assert paths[CALCULATE_PATH]["post"]["responses"]["503"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorOut"
    }
