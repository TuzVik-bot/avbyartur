from dataclasses import replace
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.customs_calculator import (
    CustomsRulesUnavailable,
    CustomsPriceBand,
    CustomsRuleVersion,
    CustomsVolumeBand,
    DEFAULT_RULES_PATH,
    REQUIRED_GTK_CASE_IDS,
    calculate_customs,
    determine_age_band,
    get_rules_for_date,
    is_publicly_available,
    load_rules_versions,
    _canonical_sha256,
)
from app.customs_rates import CurrencyRate, RateSnapshot
from app.customs_schemas import CustomsCalculationRequest


def _rules(
    *,
    price_bands: tuple[CustomsPriceBand, ...] | None = None,
    middle_bands: tuple[CustomsVolumeBand, ...] | None = None,
    old_bands: tuple[CustomsVolumeBand, ...] | None = None,
    recycling_under_3: Decimal = Decimal("5.25"),
    recycling_over_3: Decimal = Decimal("8.02"),
    customs_fee: Decimal = Decimal("1.20"),
    effective_from: date = date(2020, 1, 1),
    effective_to: date | None = None,
) -> CustomsRuleVersion:
    source = "https://example.org/test-only-rules"
    return CustomsRuleVersion(
        rules_version="test-rules-v1",
        effective_from=effective_from,
        effective_to=effective_to,
        verified_on=date(2026, 10, 4),
        sources=(source,),
        up_to_3_years=price_bands or (
            CustomsPriceBand(Decimal("8500"), Decimal("0.54"), Decimal("2.5"), source),
            CustomsPriceBand(Decimal("16700"), Decimal("0.48"), Decimal("3.5"), source),
            CustomsPriceBand(Decimal("42300"), Decimal("0.48"), Decimal("5.5"), source),
            CustomsPriceBand(Decimal("84500"), Decimal("0.48"), Decimal("7.5"), source),
            CustomsPriceBand(Decimal("169000"), Decimal("0.48"), Decimal("15"), source),
            CustomsPriceBand(None, Decimal("0.48"), Decimal("20"), source),
        ),
        over_3_to_5_years=middle_bands or (
            CustomsVolumeBand(1000, Decimal("1.5"), source),
            CustomsVolumeBand(1500, Decimal("1.7"), source),
            CustomsVolumeBand(1800, Decimal("2.5"), source),
            CustomsVolumeBand(2300, Decimal("2.7"), source),
            CustomsVolumeBand(3000, Decimal("3.0"), source),
            CustomsVolumeBand(None, Decimal("3.6"), source),
        ),
        over_5_years=old_bands or (
            CustomsVolumeBand(1000, Decimal("3.0"), source),
            CustomsVolumeBand(1500, Decimal("3.2"), source),
            CustomsVolumeBand(1800, Decimal("3.5"), source),
            CustomsVolumeBand(2300, Decimal("4.8"), source),
            CustomsVolumeBand(3000, Decimal("5.0"), source),
            CustomsVolumeBand(None, Decimal("5.7"), source),
        ),
        recycling_fee_up_to_3_byn=recycling_under_3,
        recycling_fee_over_3_byn=recycling_over_3,
        customs_fee_byn=customs_fee,
    )


def _rates(
    *,
    rate_date: date = date(2026, 10, 4),
    eur_byn: Decimal = Decimal("3"),
    input_currency: str = "EUR",
    input_byn: Decimal | None = None,
) -> RateSnapshot:
    per_unit = input_byn if input_byn is not None else eur_byn
    currencies = {
        "EUR": CurrencyRate("EUR", eur_byn, 1, eur_byn),
        "USD": CurrencyRate("USD", Decimal("3.2"), 1, Decimal("3.2")),
        "RUB": CurrencyRate("RUB", Decimal("3.6"), 100, Decimal("0.036")),
        "CNY": CurrencyRate("CNY", Decimal("4.5"), 10, Decimal("0.45")),
        "BYN": CurrencyRate("BYN", Decimal("1"), 1, Decimal("1")),
    }
    if input_currency != "EUR" and input_byn is not None:
        currencies[input_currency] = replace(
            currencies[input_currency], byn_per_unit=per_unit
        )
    return RateSnapshot(rate_date=rate_date, rates=currencies)


def _request(
    *,
    price: str = "8500",
    currency: str = "EUR",
    manufacture_date: date = date(2023, 10, 4),
    volume_cc: int = 1000,
    **overrides,
) -> CustomsCalculationRequest:
    payload = {
        "price_amount": price,
        "currency": currency,
        "manufacture_date": manufacture_date,
        "engine_type": "petrol",
        "engine_volume_cc": volume_cc,
        "personal_use": True,
        "origin_outside_eaeu": True,
    }
    payload.update(overrides)
    return CustomsCalculationRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("manufactured", "as_of", "expected"),
    [
        (date(2023, 10, 4), date(2026, 10, 4), "up_to_3_years"),
        (date(2023, 10, 4), date(2026, 10, 5), "over_3_to_5_years"),
        (date(2021, 10, 4), date(2026, 10, 4), "over_3_to_5_years"),
        (date(2021, 10, 4), date(2026, 10, 5), "over_5_years"),
    ],
)
def test_age_bands_change_on_calendar_anniversaries(manufactured, as_of, expected) -> None:
    assert determine_age_band(manufactured, as_of) == expected


def test_february_29_uses_last_calendar_day_of_february_for_anniversary() -> None:
    assert determine_age_band(date(2020, 2, 29), date(2023, 2, 28)) == "up_to_3_years"
    assert determine_age_band(date(2020, 2, 29), date(2023, 3, 1)) == "over_3_to_5_years"


@pytest.mark.parametrize(
    ("price", "expected_duty"),
    [
        ("8500", "4590.00"),
        ("8501", "4080.48"),
        ("16701", "8016.48"),
        ("42301", "20304.48"),
        ("84501", "40560.48"),
        ("169001", "81120.48"),
    ],
)
def test_every_young_vehicle_customs_value_band_uses_percentage_and_minimum(
    price, expected_duty
) -> None:
    result = calculate_customs(
        _request(price=price),
        calculation_date=date(2026, 10, 4),
        rates=_rates(),
        rules=_rules(),
    )

    assert result.age_band == "up_to_3_years"
    assert result.duty_eur == expected_duty


@pytest.mark.parametrize(
    ("volume", "expected_duty"),
    [
        (1000, "1500.00"),
        (1001, "1701.70"),
        (1501, "3752.50"),
        (1801, "4862.70"),
        (2301, "6903.00"),
        (3001, "10803.60"),
    ],
)
def test_every_middle_age_engine_volume_band(volume, expected_duty) -> None:
    result = calculate_customs(
        _request(price="5000", manufacture_date=date(2022, 10, 4), volume_cc=volume),
        calculation_date=date(2026, 10, 4),
        rates=_rates(),
        rules=_rules(),
    )

    assert result.age_band == "over_3_to_5_years"
    assert result.duty_eur == expected_duty


@pytest.mark.parametrize(
    ("volume", "expected_duty"),
    [
        (1000, "3000.00"),
        (1001, "3203.20"),
        (1501, "5253.50"),
        (1801, "8644.80"),
        (2301, "11505.00"),
        (3001, "17105.70"),
    ],
)
def test_every_old_vehicle_engine_volume_band(volume, expected_duty) -> None:
    result = calculate_customs(
        _request(price="5000", manufacture_date=date(2020, 10, 4), volume_cc=volume),
        calculation_date=date(2026, 10, 4),
        rates=_rates(),
        rules=_rules(),
    )

    assert result.age_band == "over_5_years"
    assert result.duty_eur == expected_duty


def test_young_band_uses_the_maximum_of_percentage_and_minimum() -> None:
    by_minimum = calculate_customs(
        _request(price="5000", volume_cc=1600),
        calculation_date=date(2026, 10, 4),
        rates=_rates(),
        rules=_rules(),
    )
    by_percentage = calculate_customs(
        _request(price="8500", volume_cc=1600),
        calculation_date=date(2026, 10, 4),
        rates=_rates(),
        rules=_rules(),
    )

    assert by_minimum.duty_eur == "4000.00"
    assert by_percentage.duty_eur == "4590.00"


@pytest.mark.parametrize(
    ("price", "volume", "expected_duty"),
    [
        ("8500", 1840, "4600.00"),
        ("8501", 1200, "4200.00"),
        ("16701", 1500, "8250.00"),
        ("42301", 3000, "22500.00"),
        ("84501", 3000, "45000.00"),
        ("169001", 5000, "100000.00"),
    ],
)
def test_minimum_wins_for_each_young_customs_value_band(price, volume, expected_duty) -> None:
    result = calculate_customs(
        _request(price=price, volume_cc=volume),
        calculation_date=date(2026, 10, 4),
        rates=_rates(),
        rules=_rules(),
    )

    assert result.duty_eur == expected_duty


def test_price_threshold_after_scaled_currency_conversion_is_compared_before_rounding() -> None:
    exactly_on_threshold = calculate_customs(
        _request(price="25500", currency="BYN"),
        calculation_date=date(2026, 10, 4),
        rates=_rates(eur_byn=Decimal("3")),
        rules=_rules(),
    )
    just_over_threshold = calculate_customs(
        _request(price="25500.00000003", currency="BYN"),
        calculation_date=date(2026, 10, 4),
        rates=_rates(eur_byn=Decimal("3")),
        rules=_rules(),
    )

    assert exactly_on_threshold.customs_value_eur == "8500.00"
    assert exactly_on_threshold.duty_eur == "4590.00"
    assert just_over_threshold.customs_value_eur == "8500.00"
    assert just_over_threshold.duty_eur == "4080.00"


def test_customs_value_converts_using_scaled_nbrb_rates() -> None:
    result = calculate_customs(
        _request(price="100", currency="RUB"),
        calculation_date=date(2026, 10, 4),
        rates=_rates(eur_byn=Decimal("3")),
        rules=_rules(),
    )

    assert result.customs_value_eur == "1.20"
    assert {rate.currency for rate in result.rates_used} == {"EUR", "RUB"}
    rub_rate = next(rate for rate in result.rates_used if rate.currency == "RUB")
    assert rub_rate.scale == 100


def test_money_rounding_uses_half_up_and_total_sums_displayed_lines() -> None:
    exact_duty_rules = _rules(
        middle_bands=(CustomsVolumeBand(None, Decimal("1.005"), "https://example.org/test-only-rules"),),
        old_bands=(CustomsVolumeBand(None, Decimal("1.005"), "https://example.org/test-only-rules"),),
        recycling_over_3=Decimal("0.005"),
        customs_fee=Decimal("0.005"),
    )
    result = calculate_customs(
        _request(price="50", manufacture_date=date(2022, 10, 4), volume_cc=1),
        calculation_date=date(2026, 10, 4),
        rates=_rates(eur_byn=Decimal("3.333")),
        rules=exact_duty_rules,
    )

    assert result.duty_eur == "1.01"
    assert result.duty_byn == "3.35"
    assert result.recycling_fee_byn == "0.01"
    assert result.customs_fee_byn == "0.01"
    assert result.total_byn == "3.37"


def test_duty_byn_uses_unrounded_eur_duty_not_displayed_eur_value() -> None:
    rules = _rules(
        middle_bands=(CustomsVolumeBand(None, Decimal("1.005"), "https://example.org/test-only-rules"),),
        old_bands=(CustomsVolumeBand(None, Decimal("1.005"), "https://example.org/test-only-rules"),),
        recycling_over_3=Decimal("0"),
        customs_fee=Decimal("0"),
    )
    result = calculate_customs(
        _request(price="50", manufacture_date=date(2022, 10, 4), volume_cc=1),
        calculation_date=date(2026, 10, 4),
        rates=_rates(eur_byn=Decimal("3.333")),
        rules=rules,
    )

    assert result.duty_eur == "1.01"
    assert result.duty_byn == "3.35"


@pytest.mark.parametrize(
    "payload",
    [
        {"price_amount": "0"},
        {"price_amount": "-1"},
        {"price_amount": "NaN"},
        {"price_amount": "1e3"},
        {"currency": "GBP"},
        {"engine_type": "hybrid"},
        {"engine_volume_cc": 0},
        {"engine_volume_cc": 100001},
        {"personal_use": False},
        {"origin_outside_eaeu": False},
    ],
)
def test_request_rejects_unsupported_scenario_or_invalid_values(payload) -> None:
    with pytest.raises(ValidationError):
        _request(**payload)


def test_future_manufacture_date_is_rejected_by_pure_calculator() -> None:
    with pytest.raises(ValueError, match="future"):
        calculate_customs(
            _request(manufacture_date=date(2026, 10, 5)),
            calculation_date=date(2026, 10, 4),
            rates=_rates(),
            rules=_rules(),
        )


def test_rule_set_and_rate_snapshot_must_be_effective_for_the_same_date() -> None:
    with pytest.raises(CustomsRulesUnavailable, match="effective"):
        calculate_customs(
            _request(),
            calculation_date=date(2026, 10, 4),
            rates=_rates(),
            rules=_rules(effective_from=date(2026, 10, 5)),
        )


def test_rate_snapshot_must_match_calculation_date() -> None:
    with pytest.raises(ValueError, match="rate date"):
        calculate_customs(
            _request(),
            calculation_date=date(2026, 10, 4),
            rates=_rates(rate_date=date(2026, 10, 3)),
            rules=_rules(),
        )


def _raw_rule_version(
    *,
    rules_version: str = "test-rules-v1",
    effective_from: str = "2026-04-29",
    effective_to: str | None = None,
    source_url: str = "https://eec.eaeunion.org/test-source",
) -> dict:
    source = {
        "id": "primary-source",
        "title": "Test source",
        "url": source_url,
        "effective_from": "2018-01-01",
        "effective_to": None,
        "verified_on": "2026-10-04",
    }
    return {
        "rules_version": rules_version,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "verified_on": "2026-10-04",
        "legal_sources": [source],
        "unified_duty": {
            "up_to_3_years": {
                "bands": [
                    {
                        "max_customs_value_eur": None,
                        "percent_rate": "0.5",
                        "minimum_eur_per_cc": "1.5",
                        "source_id": "primary-source",
                    }
                ]
            },
            "over_3_to_5_years": {
                "bands": [
                    {
                        "max_engine_volume_cc": None,
                        "eur_per_cc": "2.5",
                        "source_id": "primary-source",
                    }
                ]
            },
            "over_5_years": {
                "bands": [
                    {
                        "max_engine_volume_cc": None,
                        "eur_per_cc": "3.5",
                        "source_id": "primary-source",
                    }
                ]
            },
        },
        "recycling_fee_byn": {
            "up_to_3_years": {"amount_byn": "5.25", "source_id": "primary-source"},
            "over_3_years": {"amount_byn": "8.02", "source_id": "primary-source"},
        },
        "customs_operation_fee_byn": {
            "amount_byn": "1.20",
            "source_id": "primary-source",
        },
        "gtk_verification": {
            "status": "unverified",
            "rules_version": rules_version,
            "verified_on": None,
            "source_url": "https://customs.gov.by/calc/",
            "evidence_reference": "docs/customs/gtk-control-cases.json",
            "evidence_sha256": None,
            "tariff_fingerprint": None,
            "cases_sha256": None,
            "cases": [],
        },
    }


def _write_rule_document(tmp_path, *versions: dict) -> Path:
    path = tmp_path / "customs-rules.json"
    path.write_text(
        json.dumps({"schema_version": 1, "versions": list(versions)}),
        encoding="utf-8",
    )
    return path


def test_rule_versions_are_date_selected_with_exclusive_end_and_no_fallback(tmp_path) -> None:
    older = _raw_rule_version(
        rules_version="older",
        effective_from="2026-01-01",
        effective_to="2026-07-01",
    )
    newer = _raw_rule_version(
        rules_version="newer",
        effective_from="2027-01-01",
    )
    path = _write_rule_document(tmp_path, older, newer)

    assert get_rules_for_date(date(2026, 6, 30), path).rules_version == "older"
    with pytest.raises(CustomsRulesUnavailable, match="No verified customs rule version"):
        get_rules_for_date(date(2026, 7, 1), path)
    with pytest.raises(CustomsRulesUnavailable, match="No verified customs rule version"):
        get_rules_for_date(date(2026, 10, 4), path)


def test_rules_reject_untrusted_sources_and_overlapping_effective_intervals(tmp_path) -> None:
    untrusted = _raw_rule_version(source_url="https://example.org/fake-law")
    with pytest.raises(CustomsRulesUnavailable, match="legal source"):
        load_rules_versions(_write_rule_document(tmp_path, untrusted))

    first = _raw_rule_version(
        rules_version="first",
        effective_from="2026-01-01",
        effective_to="2026-08-01",
    )
    second = _raw_rule_version(
        rules_version="second",
        effective_from="2026-07-31",
    )
    with pytest.raises(CustomsRulesUnavailable, match="overlap"):
        load_rules_versions(_write_rule_document(tmp_path, first, second))


def test_packaged_rule_file_path_is_inside_backend_app_for_docker_copy() -> None:
    assert DEFAULT_RULES_PATH.parts[-3:] == ("app", "data", "customs-rules.json")


def _verified_cases() -> list[dict]:
    evidence_path = Path(__file__).resolve().parents[2] / "docs/customs/gtk-control-cases.json"
    return json.loads(evidence_path.read_text(encoding="utf-8"))["cases"]


def test_public_gate_requires_all_version_bound_real_gtk_cases() -> None:
    cases = _verified_cases()
    fingerprint = "a" * 64
    control = {
        "status": "verified",
        "rules_version": "test-rules-v1",
        "verified_on": "2026-10-04",
        "source_url": "https://customs.gov.by/calc/",
        "evidence_reference": "docs/customs/gtk-control-cases.json",
        "evidence_sha256": "b" * 64,
        "tariff_fingerprint": fingerprint,
        "cases_sha256": _canonical_sha256(cases),
        "cases": cases,
    }
    rules = replace(
        _rules(),
        tariff_fingerprint=fingerprint,
        gtk_verification=control,
    )

    assert is_publicly_available(rules)
    assert not is_publicly_available(
        replace(rules, tariff_fingerprint="c" * 64)
    )
    incomplete_cases = cases[:-1]
    assert not is_publicly_available(
        replace(
            rules,
            gtk_verification={
                **control,
                "cases": incomplete_cases,
                "cases_sha256": _canonical_sha256(incomplete_cases),
            },
        )
    )
    mismatched_case = [{**cases[0], "gtk_actual_duty_byn": "3.68"}, *cases[1:]]
    assert not is_publicly_available(
        replace(
            rules,
            gtk_verification={
                **control,
                "cases": mismatched_case,
                "cases_sha256": _canonical_sha256(mismatched_case),
            },
        )
    )
    tampered_input_cases = json.loads(json.dumps(cases))
    tampered_input_cases[0]["input"]["engine_volume_cc"] = 10000
    assert not is_publicly_available(
        replace(
            rules,
            gtk_verification={
                **control,
                "cases": tampered_input_cases,
                "cases_sha256": _canonical_sha256(tampered_input_cases),
            },
        )
    )


def test_public_gate_rejects_valid_cases_relabelled_to_fake_band_coverage() -> None:
    source_cases = {case["id"]: case for case in _verified_cases()}
    template_for_id = {}
    for case_id in REQUIRED_GTK_CASE_IDS:
        if case_id.startswith("up_to_3_price_"):
            mode = "percent" if case_id.endswith("_percent") else "minimum"
            template_for_id[case_id] = f"up_to_3_price_1_{mode}"
        elif case_id.startswith("over_3_to_5_volume_"):
            template_for_id[case_id] = "over_3_to_5_volume_1"
        else:
            template_for_id[case_id] = "over_5_volume_1"

    reused_cases = []
    for case_id, template_id in template_for_id.items():
        case = json.loads(json.dumps(source_cases[template_id]))
        case["id"] = case_id
        reused_cases.append(case)

    fingerprint = "a" * 64
    control = {
        "status": "verified",
        "rules_version": "test-rules-v1",
        "verified_on": "2026-10-04",
        "source_url": "https://customs.gov.by/calc/",
        "evidence_reference": "docs/customs/gtk-control-cases.json",
        "evidence_sha256": "b" * 64,
        "tariff_fingerprint": fingerprint,
        "cases_sha256": _canonical_sha256(reused_cases),
        "cases": reused_cases,
    }
    rules = replace(
        _rules(),
        tariff_fingerprint=fingerprint,
        gtk_verification=control,
    )

    assert len({case["id"] for case in reused_cases}) == len(REQUIRED_GTK_CASE_IDS)
    assert not is_publicly_available(rules)


def test_packaged_gtk_control_cases_match_runtime_decimal_engine() -> None:
    rules = get_rules_for_date(date(2026, 10, 4))
    assert is_publicly_available(rules)

    manufacture_dates = {
        "up_to_3_years": date(2023, 10, 4),
        "over_3_to_5_years": date(2021, 10, 4),
        "over_5_years": date(2020, 10, 4),
    }
    for case in _verified_cases():
        inputs = case["input"]
        rate = Decimal(inputs["exchange_rate_byn_per_eur"])
        volume = inputs["engine_volume_cc"]
        request = _request(
            price=inputs.get("vehicle_price_eur", "1"),
            currency="EUR",
            manufacture_date=manufacture_dates[inputs["age_band"]],
            volume_cc=volume,
        )
        snapshot = RateSnapshot(
            rate_date=date(2026, 10, 4),
            rates={"EUR": CurrencyRate("EUR", rate, 1, rate)},
        )
        result = calculate_customs(
            request,
            calculation_date=date(2026, 10, 4),
            rates=snapshot,
            rules=rules,
        )

        assert Decimal(result.duty_eur) == Decimal(case["local_expected_duty_eur"]), case["id"]
        assert Decimal(result.duty_byn) == Decimal(case["local_expected_duty_byn"]), case["id"]
        assert Decimal(result.duty_byn) == Decimal(case["gtk_actual_duty_byn"]).quantize(
            Decimal("0.01")
        ), case["id"]
