from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.customs_calculator import (
    CustomsRulesUnavailable,
    calculate_customs,
    get_rules_for_date,
    is_publicly_available,
)
from app.customs_rates import NBRB_API_URL, RatesUnavailable, get_nbrb_rates
from app.customs_schemas import CustomsCalculationRequest, CustomsCalculationResponse, CustomsMetaResponse
from app.schemas import ApiErrorOut
from app.services import fail


router = APIRouter(prefix="/api/v1/customs-calculator", tags=["customs-calculator"])
SCENARIO = "private_m1_personal_use_outside_eaeu"
SUPPORTED_CURRENCIES = ["EUR", "USD", "BYN", "RUB", "CNY"]
SUPPORTED_ENGINES = ["petrol", "diesel"]
SCOPE_NOTES = [
    "Расчет предназначен для физического лица, ввозящего для личного пользования автомобиль категории M1 с бензиновым или дизельным двигателем из-за пределов ЕАЭС в Беларусь без льгот.",
    "Электромобили, гибриды, ввоз из ЕАЭС, юридические лица и льготы не поддерживаются.",
    "Цена покупки является оценкой таможенной стоимости; окончательную стоимость определяет таможня.",
    "Цена покупки, доставка, брокерские услуги и страхование не входят в сумму таможенных платежей.",
    "Отдельный НДС не начисляется поверх единой ставки.",
]


def minsk_today() -> date:
    return datetime.now(ZoneInfo("Europe/Minsk")).date()


def _meta_for_rules(rules, unavailable_reason: str | None = None) -> CustomsMetaResponse:
    available = rules is not None and is_publicly_available(rules)
    reason = unavailable_reason
    if rules is not None and not available and reason is None:
        reason = "customs_rules_unverified"
    source_urls = list(rules.sources) if rules is not None else []
    control = getattr(rules, "gtk_verification", None) if rules is not None else None
    if isinstance(control, dict) and isinstance(control.get("source_url"), str):
        source_urls.append(control["source_url"])
    source_urls.append(
        f"{NBRB_API_URL}?periodicity=0&ondate={minsk_today().isoformat()}"
    )
    return CustomsMetaResponse(
        scenario=SCENARIO,
        supported_currencies=SUPPORTED_CURRENCIES,
        supported_engines=SUPPORTED_ENGINES,
        calculation_available=available,
        unavailable_reason=None if available else reason or "customs_rules_unavailable",
        rules_version=rules.rules_version if rules is not None else None,
        verified_on=rules.verified_on if rules is not None else None,
        sources=list(dict.fromkeys(source_urls)),
        scope_notes=SCOPE_NOTES,
    )


@router.get("/meta", response_model=CustomsMetaResponse)
def customs_calculator_meta() -> CustomsMetaResponse:
    try:
        rules = get_rules_for_date(minsk_today())
    except CustomsRulesUnavailable:
        return _meta_for_rules(None, unavailable_reason="customs_rules_unavailable")
    return _meta_for_rules(rules)


@router.post(
    "/calculate",
    response_model=CustomsCalculationResponse,
    responses={
        422: {"model": ApiErrorOut, "description": "Input or scenario validation error"},
        503: {"model": ApiErrorOut, "description": "Customs rules or official rates are unavailable"},
    },
)
def calculate_customs_public(payload: CustomsCalculationRequest) -> CustomsCalculationResponse:
    calculation_date = minsk_today()
    try:
        rules = get_rules_for_date(calculation_date)
    except CustomsRulesUnavailable:
        fail(503, "customs_rules_unavailable", "Customs rules are not available for today")
    if not is_publicly_available(rules):
        fail(503, "customs_rules_unverified", "Customs calculations are temporarily unavailable")
    try:
        rates = get_nbrb_rates(calculation_date)
    except RatesUnavailable:
        fail(503, "customs_rates_unavailable", "Official exchange rates are unavailable for today")
    try:
        return calculate_customs(
            payload,
            calculation_date=calculation_date,
            rates=rates,
            rules=rules,
        )
    except CustomsRulesUnavailable:
        fail(503, "customs_rules_unavailable", "Customs rules are not available for today")
    except ValueError as exc:
        fail(422, "customs_input_invalid", str(exc), {"request": str(exc)})
