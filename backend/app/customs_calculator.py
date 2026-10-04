from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.customs_rates import CurrencyRate, NBRB_API_URL, RateSnapshot, SUPPORTED_CURRENCIES
from app.customs_schemas import (
    CustomsCalculationRequest,
    CustomsCalculationResponse,
    CustomsRateUsed,
)


DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "data" / "customs-rules.json"
MAX_RULES_FILE_BYTES = 1024 * 1024
CENT = Decimal("0.01")
REQUIRED_GTK_CASE_IDS = frozenset(
    {
        *(
            f"up_to_3_price_{index}_{mode}"
            for index in range(1, 7)
            for mode in ("percent", "minimum")
        ),
        *(f"over_3_to_5_volume_{index}" for index in range(1, 7)),
        *(f"over_5_volume_{index}" for index in range(1, 7)),
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_OFFICIAL_SOURCE_SUFFIXES = (
    ".eaeunion.org",
    ".nalog.gov.by",
    ".customs.gov.by",
    ".pravo.by",
    ".etalonline.by",
    ".president.gov.by",
)


class CustomsRulesUnavailable(RuntimeError):
    """Raised when no complete legal rate version applies to the calculation date."""


@dataclass(frozen=True)
class CustomsPriceBand:
    max_customs_value_eur: Decimal | None
    percent_rate: Decimal
    minimum_eur_per_cc: Decimal
    source_url: str


@dataclass(frozen=True)
class CustomsVolumeBand:
    max_engine_volume_cc: int | None
    eur_per_cc: Decimal
    source_url: str


@dataclass(frozen=True)
class CustomsRuleVersion:
    rules_version: str
    effective_from: date
    effective_to: date | None
    verified_on: date
    sources: tuple[str, ...]
    up_to_3_years: tuple[CustomsPriceBand, ...]
    over_3_to_5_years: tuple[CustomsVolumeBand, ...]
    over_5_years: tuple[CustomsVolumeBand, ...]
    recycling_fee_up_to_3_byn: Decimal
    recycling_fee_over_3_byn: Decimal
    customs_fee_byn: Decimal
    tariff_fingerprint: str | None = None
    gtk_verification: dict[str, Any] | None = None


def _parse_date(value: Any, field_name: str, *, optional: bool = False) -> date | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise CustomsRulesUnavailable(f"Rules data has an invalid {field_name}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise CustomsRulesUnavailable(f"Rules data has an invalid {field_name}") from None


def _parse_money(value: Any, field_name: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise CustomsRulesUnavailable(f"Rules data has an invalid {field_name}")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise CustomsRulesUnavailable(f"Rules data has an invalid {field_name}") from None
    if (
        not amount.is_finite()
        or amount < 0
        or amount >= Decimal("1e18")
        or len(amount.as_tuple().digits) > 48
        or amount.adjusted() > 18
        or amount.adjusted() < -48
        or (amount == 0 and not allow_zero)
    ):
        raise CustomsRulesUnavailable(f"Rules data has an invalid {field_name}")
    return amount


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_host_is_official(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        return False
    return any(hostname == suffix[1:] or hostname.endswith(suffix) for suffix in _OFFICIAL_SOURCE_SUFFIXES)


def _parse_sources(version: dict[str, Any], version_start: date, version_end: date | None) -> dict[str, str]:
    raw_sources = version.get("legal_sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise CustomsRulesUnavailable("Rules version must contain legal sources")
    sources: dict[str, str] = {}
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise CustomsRulesUnavailable("Rules data contains an invalid legal source")
        source_id = raw.get("id")
        title = raw.get("title")
        url = raw.get("url")
        if (
            not isinstance(source_id, str)
            or not source_id.strip()
            or source_id in sources
            or not isinstance(title, str)
            or not title.strip()
            or not _source_host_is_official(url)
        ):
            raise CustomsRulesUnavailable("Rules data contains an invalid legal source")
        source_start = _parse_date(raw.get("effective_from"), "source effective_from")
        source_end = _parse_date(raw.get("effective_to"), "source effective_to", optional=True)
        _parse_date(raw.get("verified_on"), "source verified_on")
        if source_start is None or source_start > version_start:
            raise CustomsRulesUnavailable("Legal source does not cover the rules effective_from date")
        if source_end is not None and (version_end is None or source_end < version_end):
            raise CustomsRulesUnavailable("Legal source expires before the rules version")
        if source_end is not None and source_end <= source_start:
            raise CustomsRulesUnavailable("Rules data has an invalid source validity interval")
        sources[source_id] = url
    return sources


def _source_url(raw: dict[str, Any], sources: dict[str, str]) -> str:
    source_id = raw.get("source_id")
    if not isinstance(source_id, str) or source_id not in sources:
        raise CustomsRulesUnavailable("A tariff has no valid legal source")
    return sources[source_id]


def _parse_price_bands(raw: Any, sources: dict[str, str]) -> tuple[CustomsPriceBand, ...]:
    if not isinstance(raw, list) or not raw:
        raise CustomsRulesUnavailable("Up-to-three-year duty bands are missing")
    bands: list[CustomsPriceBand] = []
    previous: Decimal | None = None
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CustomsRulesUnavailable("Rules data contains an invalid customs value band")
        maximum = item.get("max_customs_value_eur")
        maximum_value = None if maximum is None else _parse_money(maximum, "customs value threshold")
        if maximum_value is not None and (previous is not None and maximum_value <= previous):
            raise CustomsRulesUnavailable("Customs value thresholds must increase strictly")
        if maximum_value is None and index != len(raw) - 1:
            raise CustomsRulesUnavailable("Only the last customs value band may be unbounded")
        percent = _parse_money(item.get("percent_rate"), "unified duty percentage")
        if percent > 1:
            raise CustomsRulesUnavailable("Unified duty percentage must be a fraction")
        minimum = _parse_money(item.get("minimum_eur_per_cc"), "minimum duty per cc")
        bands.append(
            CustomsPriceBand(
                max_customs_value_eur=maximum_value,
                percent_rate=percent,
                minimum_eur_per_cc=minimum,
                source_url=_source_url(item, sources),
            )
        )
        if maximum_value is not None:
            previous = maximum_value
    if bands[-1].max_customs_value_eur is not None:
        raise CustomsRulesUnavailable("The final customs value band must be unbounded")
    return tuple(bands)


def _parse_volume_bands(raw: Any, sources: dict[str, str], *, group: str) -> tuple[CustomsVolumeBand, ...]:
    if not isinstance(raw, list) or not raw:
        raise CustomsRulesUnavailable(f"{group} engine volume bands are missing")
    bands: list[CustomsVolumeBand] = []
    previous: int | None = None
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CustomsRulesUnavailable(f"Rules data contains an invalid {group} volume band")
        maximum = item.get("max_engine_volume_cc")
        if maximum is not None and (
            isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0
        ):
            raise CustomsRulesUnavailable(f"Rules data contains an invalid {group} volume threshold")
        if maximum is not None and previous is not None and maximum <= previous:
            raise CustomsRulesUnavailable(f"{group} volume thresholds must increase strictly")
        if maximum is None and index != len(raw) - 1:
            raise CustomsRulesUnavailable(f"Only the last {group} volume band may be unbounded")
        amount = _parse_money(item.get("eur_per_cc"), f"{group} duty per cc")
        bands.append(
            CustomsVolumeBand(
                max_engine_volume_cc=maximum,
                eur_per_cc=amount,
                source_url=_source_url(item, sources),
            )
        )
        if maximum is not None:
            previous = maximum
    if bands[-1].max_engine_volume_cc is not None:
        raise CustomsRulesUnavailable(f"The final {group} volume band must be unbounded")
    return tuple(bands)


def _parse_rule_version(raw: Any) -> CustomsRuleVersion:
    if not isinstance(raw, dict):
        raise CustomsRulesUnavailable("Rules data contains an invalid version")
    version_id = raw.get("rules_version")
    if not isinstance(version_id, str) or not version_id.strip():
        raise CustomsRulesUnavailable("Rules data contains a version without an id")
    effective_from = _parse_date(raw.get("effective_from"), "effective_from")
    effective_to = _parse_date(raw.get("effective_to"), "effective_to", optional=True)
    verified_on = _parse_date(raw.get("verified_on"), "verified_on")
    if effective_from is None or verified_on is None:
        raise CustomsRulesUnavailable("Rules version is missing dates")
    if effective_to is not None and effective_to <= effective_from:
        raise CustomsRulesUnavailable("Rules version has an invalid effective interval")
    sources = _parse_sources(raw, effective_from, effective_to)

    duty = raw.get("unified_duty")
    if not isinstance(duty, dict):
        raise CustomsRulesUnavailable("Rules version is missing unified duty tables")
    up_to_3 = duty.get("up_to_3_years")
    over_3_to_5 = duty.get("over_3_to_5_years")
    over_5 = duty.get("over_5_years")
    if not isinstance(up_to_3, dict) or not isinstance(over_3_to_5, dict) or not isinstance(over_5, dict):
        raise CustomsRulesUnavailable("Rules version is missing an age group")

    recycling = raw.get("recycling_fee_byn")
    operations = raw.get("customs_operation_fee_byn")
    if not isinstance(recycling, dict) or not isinstance(operations, dict):
        raise CustomsRulesUnavailable("Rules version is missing mandatory fee tables")
    _source_url(recycling.get("up_to_3_years", {}), sources)
    _source_url(recycling.get("over_3_years", {}), sources)
    _source_url(operations, sources)

    version_without_control = {
        key: value for key, value in raw.items() if key != "gtk_verification"
    }
    tariff_fingerprint = _canonical_sha256(version_without_control)
    control = raw.get("gtk_verification")
    return CustomsRuleVersion(
        rules_version=version_id,
        effective_from=effective_from,
        effective_to=effective_to,
        verified_on=verified_on,
        sources=tuple(dict.fromkeys(sources.values())),
        up_to_3_years=_parse_price_bands(up_to_3.get("bands"), sources),
        over_3_to_5_years=_parse_volume_bands(
            over_3_to_5.get("bands"), sources, group="over_3_to_5_years"
        ),
        over_5_years=_parse_volume_bands(over_5.get("bands"), sources, group="over_5_years"),
        recycling_fee_up_to_3_byn=_parse_money(
            recycling.get("up_to_3_years", {}).get("amount_byn"),
            "up-to-three-year recycling fee",
        ),
        recycling_fee_over_3_byn=_parse_money(
            recycling.get("over_3_years", {}).get("amount_byn"),
            "over-three-year recycling fee",
        ),
        customs_fee_byn=_parse_money(operations.get("amount_byn"), "customs operation fee"),
        tariff_fingerprint=tariff_fingerprint,
        gtk_verification=control if isinstance(control, dict) else None,
    )


def load_rules_versions(path: Path = DEFAULT_RULES_PATH) -> tuple[CustomsRuleVersion, ...]:
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise CustomsRulesUnavailable("Customs rules are unavailable") from exc
    if len(body) > MAX_RULES_FILE_BYTES:
        raise CustomsRulesUnavailable("Customs rules data exceeds the size limit")
    try:
        document = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise CustomsRulesUnavailable("Customs rules data is invalid JSON") from None
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise CustomsRulesUnavailable("Customs rules data has an unsupported schema version")
    raw_versions = document.get("versions")
    if not isinstance(raw_versions, list) or not raw_versions:
        raise CustomsRulesUnavailable("Customs rules data contains no versions")
    versions = tuple(_parse_rule_version(raw) for raw in raw_versions)
    if len({version.rules_version for version in versions}) != len(versions):
        raise CustomsRulesUnavailable("Customs rules data has duplicate version ids")
    ordered = sorted(versions, key=lambda version: version.effective_from)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.effective_to is None or current.effective_from < previous.effective_to:
            raise CustomsRulesUnavailable("Customs rules effective intervals overlap")
    return tuple(ordered)


def get_rules_for_date(on_date: date, path: Path = DEFAULT_RULES_PATH) -> CustomsRuleVersion:
    if type(on_date) is not date:
        raise TypeError("on_date must be a date")
    for version in load_rules_versions(path):
        if version.effective_from <= on_date and (
            version.effective_to is None or on_date < version.effective_to
        ):
            return version
    raise CustomsRulesUnavailable("No verified customs rule version applies to this date")


def _valid_control_case(case: Any, expected_id: str, rules: CustomsRuleVersion) -> bool:
    if not isinstance(case, dict) or case.get("id") != expected_id or case.get("status") != "matched":
        return False
    local_eur_value = case.get("local_expected_duty_eur")
    gtk_eur_value = case.get("gtk_actual_duty_eur")
    local_byn_value = case.get("local_expected_duty_byn")
    gtk_byn_value = case.get("gtk_actual_duty_byn")
    checked_on = case.get("checked_on")
    evidence = case.get("evidence")
    input_values = case.get("input")
    if not all(
        isinstance(value, str)
        for value in (local_eur_value, gtk_eur_value, local_byn_value, gtk_byn_value)
    ):
        return False
    if not isinstance(input_values, dict):
        return False
    try:
        local_eur = Decimal(local_eur_value)
        gtk_eur = Decimal(gtk_eur_value)
        local_byn = Decimal(local_byn_value)
        gtk_byn = Decimal(gtk_byn_value)
        gtk_input_rate = Decimal(str(input_values["exchange_rate_byn_per_eur"]))
        date.fromisoformat(checked_on)
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False
    if not all(
        value.is_finite()
        and value > 0
        and len(value.as_tuple().digits) <= 48
        and value.adjusted() <= 18
        and value.adjusted() >= -48
        for value in (local_eur, gtk_eur, local_byn, gtk_byn, gtk_input_rate)
    ):
        return False
    if gtk_input_rate > Decimal("1000000"):
        return False
    if local_eur != gtk_eur or not isinstance(evidence, str) or not evidence.strip():
        return False

    age_band = input_values.get("age_band")
    expected_group = {
        "up_to_3_years": "<=3",
        "over_3_to_5_years": ">3<=5",
        "over_5_years": ">5",
    }.get(age_band)
    if expected_group is None or input_values.get("gtk_age_group_label") != expected_group:
        return False
    volume = input_values.get("engine_volume_cc")
    if isinstance(volume, bool) or not isinstance(volume, int) or not 1 <= volume <= 100_000:
        return False

    try:
        with localcontext() as context:
            context.prec = 96
            if age_band == "up_to_3_years":
                if input_values.get("price_currency") != "EUR":
                    return False
                price_value = input_values.get("vehicle_price_eur")
                if not isinstance(price_value, str):
                    return False
                price_eur = Decimal(price_value)
                if (
                    not price_eur.is_finite()
                    or price_eur <= 0
                    or len(price_eur.as_tuple().digits) > 40
                    or price_eur.adjusted() > 18
                    or price_eur.adjusted() < -48
                ):
                    return False
                band = _selected_price_band(price_eur, rules.up_to_3_years)
                calculated_eur = max(
                    price_eur * band.percent_rate,
                    Decimal(volume) * band.minimum_eur_per_cc,
                )
            else:
                if input_values.get("price_field_present") is not False:
                    return False
                bands = (
                    rules.over_3_to_5_years
                    if age_band == "over_3_to_5_years"
                    else rules.over_5_years
                )
                band = _selected_volume_band(volume, bands)
                calculated_eur = Decimal(volume) * band.eur_per_cc
            calculated_byn = (calculated_eur * gtk_input_rate).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            return (
                local_eur == calculated_eur
                and local_byn == calculated_byn
                and local_byn.quantize(CENT, rounding=ROUND_HALF_UP)
                == gtk_byn.quantize(CENT, rounding=ROUND_HALF_UP)
            )
    except (InvalidOperation, ValueError, TypeError):
        return False


def is_publicly_available(rules: CustomsRuleVersion) -> bool:
    control = rules.gtk_verification
    if not isinstance(control, dict) or control.get("status") != "verified":
        return False
    if control.get("rules_version") != rules.rules_version:
        return False
    if control.get("tariff_fingerprint") != rules.tariff_fingerprint:
        return False
    if not isinstance(control.get("verified_on"), str):
        return False
    try:
        date.fromisoformat(control["verified_on"])
    except ValueError:
        return False
    if not _source_host_is_official(control.get("source_url")):
        return False
    if not _SHA256_PATTERN.fullmatch(str(control.get("evidence_sha256", ""))):
        return False
    cases = control.get("cases")
    if not isinstance(cases, list):
        return False
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or len(set(case_ids)) != len(case_ids):
        return False
    if not REQUIRED_GTK_CASE_IDS.issubset(case_ids):
        return False
    cases_by_id = {case["id"]: case for case in cases}
    if not all(
        _valid_control_case(cases_by_id.get(case_id), case_id, rules)
        for case_id in REQUIRED_GTK_CASE_IDS
    ):
        return False
    if control.get("cases_sha256") != _canonical_sha256(cases):
        return False
    return True


def _anniversary(value: date, years: int) -> date:
    year = value.year + years
    try:
        return value.replace(year=year)
    except ValueError:
        # A 29 February manufacture date reaches its calendar anniversary on
        # the final day of February in a non-leap year.
        return date(year, value.month, 28)


def determine_age_band(manufacture_date: date, calculation_date: date) -> str:
    if type(manufacture_date) is not date or type(calculation_date) is not date:
        raise ValueError("Calculation dates must be calendar dates")
    if manufacture_date > calculation_date:
        raise ValueError("Manufacture date cannot be in the future")
    if calculation_date <= _anniversary(manufacture_date, 3):
        return "up_to_3_years"
    if calculation_date <= _anniversary(manufacture_date, 5):
        return "over_3_to_5_years"
    return "over_5_years"


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _money_text(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def _selected_price_band(value_eur: Decimal, bands: tuple[CustomsPriceBand, ...]) -> CustomsPriceBand:
    for band in bands:
        if band.max_customs_value_eur is None or value_eur <= band.max_customs_value_eur:
            return band
    raise CustomsRulesUnavailable("No customs value tariff band applies")


def _selected_volume_band(volume_cc: int, bands: tuple[CustomsVolumeBand, ...]) -> CustomsVolumeBand:
    for band in bands:
        if band.max_engine_volume_cc is None or volume_cc <= band.max_engine_volume_cc:
            return band
    raise CustomsRulesUnavailable("No engine volume tariff band applies")


def _validate_rate(rate: CurrencyRate, currency: str) -> None:
    if (
        rate.currency != currency
        or isinstance(rate.scale, bool)
        or not isinstance(rate.scale, int)
        or rate.scale <= 0
        or rate.scale > 1_000_000_000
        or not rate.official_rate.is_finite()
        or rate.official_rate <= 0
        or len(rate.official_rate.as_tuple().digits) > 32
        or rate.official_rate.adjusted() > 12
        or rate.official_rate.adjusted() < -12
        or not rate.byn_per_unit.is_finite()
        or rate.byn_per_unit <= 0
        or len(rate.byn_per_unit.as_tuple().digits) > 48
        or rate.byn_per_unit.adjusted() > 18
        or rate.byn_per_unit.adjusted() < -48
    ):
        raise ValueError(f"Invalid official rate for {currency}")


def calculate_customs(
    request: CustomsCalculationRequest,
    *,
    calculation_date: date,
    rates: RateSnapshot,
    rules: CustomsRuleVersion,
) -> CustomsCalculationResponse:
    if not isinstance(request, CustomsCalculationRequest):
        raise TypeError("request must be a validated CustomsCalculationRequest")
    if rules.effective_from > calculation_date or (
        rules.effective_to is not None and calculation_date >= rules.effective_to
    ):
        raise CustomsRulesUnavailable("Customs rules are not effective on the calculation date")
    if rates.rate_date != calculation_date:
        raise ValueError("Official rate date must match the calculation date")
    age_band = determine_age_band(request.manufacture_date, calculation_date)
    currency = request.currency
    if currency not in SUPPORTED_CURRENCIES or currency not in rates.rates or "EUR" not in rates.rates:
        raise ValueError("A required official rate is missing")
    input_rate = rates.rates[currency]
    eur_rate = rates.rates["EUR"]
    _validate_rate(input_rate, currency)
    _validate_rate(eur_rate, "EUR")
    price = Decimal(request.price_amount)
    if not price.is_finite() or price <= 0:
        raise ValueError("Price amount must be finite and positive")

    with localcontext() as context:
        context.prec = 96
        customs_value_eur_exact = price * input_rate.byn_per_unit / eur_rate.byn_per_unit
        if age_band == "up_to_3_years":
            band = _selected_price_band(customs_value_eur_exact, rules.up_to_3_years)
            percent_amount = customs_value_eur_exact * band.percent_rate
            minimum_amount = Decimal(request.engine_volume_cc) * band.minimum_eur_per_cc
            duty_eur_exact = max(percent_amount, minimum_amount)
            recycling_fee_exact = rules.recycling_fee_up_to_3_byn
        elif age_band == "over_3_to_5_years":
            band = _selected_volume_band(request.engine_volume_cc, rules.over_3_to_5_years)
            duty_eur_exact = Decimal(request.engine_volume_cc) * band.eur_per_cc
            recycling_fee_exact = rules.recycling_fee_over_3_byn
        else:
            band = _selected_volume_band(request.engine_volume_cc, rules.over_5_years)
            duty_eur_exact = Decimal(request.engine_volume_cc) * band.eur_per_cc
            recycling_fee_exact = rules.recycling_fee_over_3_byn

        duty_eur_rounded = duty_eur_exact.quantize(CENT, rounding=ROUND_HALF_UP)
        # Convert the unrounded duty, then round the displayed BYN duty once.
        duty_byn_rounded = (duty_eur_exact * eur_rate.byn_per_unit).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        recycling_fee_rounded = recycling_fee_exact.quantize(CENT, rounding=ROUND_HALF_UP)
        customs_fee_rounded = rules.customs_fee_byn.quantize(CENT, rounding=ROUND_HALF_UP)
        total_byn_rounded = duty_byn_rounded + recycling_fee_rounded + customs_fee_rounded
        customs_value_eur_rounded = customs_value_eur_exact.quantize(CENT, rounding=ROUND_HALF_UP)

    used_currency_codes = ["EUR"]
    if currency != "EUR":
        used_currency_codes.append(currency)
    rates_used = [
        CustomsRateUsed(
            currency=code,
            official_rate=_decimal_text(rates.rates[code].official_rate),
            scale=rates.rates[code].scale,
            byn_per_unit=_decimal_text(rates.rates[code].byn_per_unit),
        )
        for code in used_currency_codes
    ]
    source_urls = tuple(
        dict.fromkeys(
            (
                *rules.sources,
                band.source_url,
                f"{NBRB_API_URL}?periodicity=0&ondate={rates.rate_date.isoformat()}",
            )
        )
    )
    return CustomsCalculationResponse(
        calculation_date=calculation_date,
        rules_version=rules.rules_version,
        age_band=age_band,
        customs_value_eur=_money_text(customs_value_eur_rounded),
        duty_eur=_money_text(duty_eur_rounded),
        duty_byn=_money_text(duty_byn_rounded),
        recycling_fee_byn=_money_text(recycling_fee_rounded),
        customs_fee_byn=_money_text(customs_fee_rounded),
        total_byn=_money_text(total_byn_rounded),
        rate_date=rates.rate_date,
        rates_used=rates_used,
        sources=list(source_urls),
        warnings=[
            "Цена покупки используется как оценка таможенной стоимости; окончательную стоимость определяет таможня.",
            "Отдельный НДС не добавляется поверх единой ставки.",
            "Доставка, брокерские услуги и страхование не входят в итог таможенных платежей.",
        ],
    )
