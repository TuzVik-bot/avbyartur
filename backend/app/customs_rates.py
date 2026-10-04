from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen


NBRB_API_URL = "https://api.nbrb.by/exrates/rates"
SUPPORTED_CURRENCIES = ("EUR", "USD", "BYN", "RUB", "CNY")
_NBRB_CURRENCIES = frozenset({"EUR", "USD", "RUB", "CNY"})
MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_CACHE_TTL_SECONDS = 300.0


class RatesUnavailable(RuntimeError):
    """Raised when a current, valid same-date NBRB snapshot is unavailable."""


@dataclass(frozen=True)
class CurrencyRate:
    currency: str
    official_rate: Decimal
    scale: int
    byn_per_unit: Decimal


@dataclass(frozen=True)
class RateSnapshot:
    rate_date: date
    rates: Mapping[str, CurrencyRate]


def _parse_date(value: object) -> date:
    if not isinstance(value, str) or len(value) < 10:
        raise RatesUnavailable("NBRB response contains an invalid rate date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise RatesUnavailable("NBRB response contains an invalid rate date") from None


def _parse_decimal(value: object, *, currency: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RatesUnavailable(f"NBRB response contains an invalid rate for {currency}")
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RatesUnavailable(f"NBRB response contains an invalid rate for {currency}") from None
    if (
        not rate.is_finite()
        or rate <= 0
        or len(rate.as_tuple().digits) > 32
        or rate.adjusted() > 12
        or rate.adjusted() < -12
    ):
        raise RatesUnavailable(f"NBRB response contains a non-positive or non-finite rate for {currency}")
    return rate


def _decode_snapshot(body: bytes, requested_date: date) -> RateSnapshot:
    try:
        decoded = json.loads(body.decode("utf-8"), parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation, ValueError):
        raise RatesUnavailable("NBRB response is not valid UTF-8 JSON") from None
    if not isinstance(decoded, list):
        raise RatesUnavailable("NBRB response must be a list of rates")

    rates: dict[str, CurrencyRate] = {}
    for row in decoded:
        if not isinstance(row, dict):
            raise RatesUnavailable("NBRB response contains an invalid rate row")
        currency = row.get("Cur_Abbreviation")
        if not isinstance(currency, str):
            continue
        currency = currency.upper()
        if currency == "BYN" or currency not in _NBRB_CURRENCIES:
            continue
        if currency in rates:
            raise RatesUnavailable(f"NBRB response contains duplicate {currency} rates")

        row_date = _parse_date(row.get("Date"))
        if row_date != requested_date:
            raise RatesUnavailable("NBRB response does not match the requested rate date")
        official_rate = _parse_decimal(row.get("Cur_OfficialRate"), currency=currency)
        scale = row.get("Cur_Scale")
        if (
            isinstance(scale, bool)
            or not isinstance(scale, int)
            or scale <= 0
            or scale > 1_000_000_000
        ):
            raise RatesUnavailable(f"NBRB response contains an invalid scale for {currency}")
        rates[currency] = CurrencyRate(
            currency=currency,
            official_rate=official_rate,
            scale=scale,
            byn_per_unit=official_rate / Decimal(scale),
        )

    missing = _NBRB_CURRENCIES - rates.keys()
    if missing:
        if "EUR" in missing:
            raise RatesUnavailable("NBRB response is missing the required EUR rate")
        raise RatesUnavailable(
            "NBRB response is missing supported currency rates: " + ", ".join(sorted(missing))
        )
    if not rates["EUR"].byn_per_unit.is_finite() or rates["EUR"].byn_per_unit <= 0:
        raise RatesUnavailable("NBRB response contains an invalid EUR rate")
    rates["BYN"] = CurrencyRate(
        currency="BYN",
        official_rate=Decimal("1"),
        scale=1,
        byn_per_unit=Decimal("1"),
    )
    return RateSnapshot(rate_date=requested_date, rates=MappingProxyType(rates))


class NbrbRateClient:
    """Fetch and cache one bounded, validated NBRB snapshot at a time."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        opener: Callable = urlopen,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0 < timeout_seconds <= 5:
            raise ValueError("timeout_seconds must be between 0 and 5")
        if not 0 < cache_ttl_seconds <= 900:
            raise ValueError("cache_ttl_seconds must be between 0 and 900")
        if not 0 < max_response_bytes <= 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 1048576")
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_response_bytes = max_response_bytes
        self._opener = opener
        self._clock = clock
        self._lock = threading.Lock()
        self._cached: tuple[date, float, RateSnapshot] | None = None

    def get_rates(self, on_date: date) -> RateSnapshot:
        if type(on_date) is not date:
            raise TypeError("on_date must be a date")
        with self._lock:
            now = self._clock()
            if self._cached is not None:
                cached_date, expires_at, snapshot = self._cached
                if cached_date == on_date and now < expires_at:
                    return snapshot
            snapshot = self._fetch(on_date)
            self._cached = (on_date, self._clock() + self.cache_ttl_seconds, snapshot)
            return snapshot

    def _fetch(self, on_date: date) -> RateSnapshot:
        url = f"{NBRB_API_URL}?periodicity=0&ondate={on_date.isoformat()}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "AvtorinokCustomsCalculator/1.0",
            },
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                headers = getattr(response, "headers", None)
                content_length = headers.get("Content-Length") if headers else None
                if content_length is not None:
                    try:
                        if int(content_length) > self.max_response_bytes:
                            raise RatesUnavailable("NBRB response exceeds the size limit")
                    except ValueError:
                        raise RatesUnavailable("NBRB response has an invalid Content-Length") from None
                body = response.read(self.max_response_bytes + 1)
        except RatesUnavailable:
            raise
        except (TimeoutError, URLError, OSError) as exc:
            raise RatesUnavailable("NBRB rate service is unavailable") from exc
        except Exception as exc:
            raise RatesUnavailable("NBRB rate service is unavailable") from exc
        if not isinstance(body, bytes) or len(body) > self.max_response_bytes:
            raise RatesUnavailable("NBRB response exceeds the size limit")
        return _decode_snapshot(body, on_date)


_default_client = NbrbRateClient()


def get_nbrb_rates(on_date: date) -> RateSnapshot:
    return _default_client.get_rates(on_date)
