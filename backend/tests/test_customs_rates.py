from datetime import date
from decimal import Decimal
import json
import threading
import time

import pytest

from app.customs_rates import (
    NbrbRateClient,
    RatesUnavailable,
    SUPPORTED_CURRENCIES,
)


def _payload(*, on_date: str = "2026-10-04", overrides: dict[str, dict] | None = None) -> bytes:
    values = {
        "EUR": ("3.386", 1),
        "USD": ("3.0051", 1),
        "RUB": ("3.6121", 100),
        "CNY": ("4.5035", 10),
    }
    for currency, row in (overrides or {}).items():
        values[currency] = (str(row.get("Cur_OfficialRate", values[currency][0])), row.get("Cur_Scale", values[currency][1]))
    data = [
        {
            "Cur_Abbreviation": currency,
            "Cur_OfficialRate": rate,
            "Cur_Scale": scale,
            "Date": f"{on_date}T00:00:00",
        }
        for currency, (rate, scale) in values.items()
    ]
    return json.dumps(data, allow_nan=True).encode()


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def _client(body: bytes, **kwargs) -> NbrbRateClient:
    return NbrbRateClient(opener=lambda request, timeout: _Response(body), **kwargs)


def test_supported_currencies_and_scales_are_normalized_to_byn_per_unit() -> None:
    snapshot = _client(_payload()).get_rates(date(2026, 10, 4))

    assert set(snapshot.rates) == set(SUPPORTED_CURRENCIES)
    assert snapshot.rates["EUR"].byn_per_unit == Decimal("3.386")
    assert snapshot.rates["RUB"].scale == 100
    assert snapshot.rates["RUB"].byn_per_unit == Decimal("0.036121")
    assert snapshot.rates["CNY"].scale == 10
    assert snapshot.rates["CNY"].byn_per_unit == Decimal("0.45035")
    assert snapshot.rates["BYN"].byn_per_unit == Decimal("1")


@pytest.mark.parametrize(
    "overrides",
    [
        {"EUR": {"Cur_OfficialRate": "NaN"}},
        {"EUR": {"Cur_OfficialRate": "Infinity"}},
        {"EUR": {"Cur_OfficialRate": "0"}},
        {"EUR": {"Cur_OfficialRate": "-1"}},
        {"RUB": {"Cur_Scale": 0}},
        {"CNY": {"Cur_Scale": 2.5}},
    ],
)
def test_rejects_nonfinite_nonpositive_rates_or_invalid_scales(overrides) -> None:
    with pytest.raises(RatesUnavailable):
        _client(_payload(overrides=overrides)).get_rates(date(2026, 10, 4))


def test_rejects_rows_with_mismatched_dates_and_duplicate_supported_currencies() -> None:
    mismatched = json.loads(_payload())
    mismatched[1]["Date"] = "2026-10-03T00:00:00"
    duplicate = json.loads(_payload())
    duplicate.append(duplicate[0])

    for payload in (mismatched, duplicate):
        with pytest.raises(RatesUnavailable):
            _client(json.dumps(payload).encode()).get_rates(date(2026, 10, 4))


def test_rejects_response_missing_or_mislabeling_a_supported_currency() -> None:
    data = json.loads(_payload())
    data = [
        {**row, "Cur_Abbreviation": "GBP"}
        if row["Cur_Abbreviation"] == "USD"
        else row
        for row in data
    ]

    with pytest.raises(RatesUnavailable, match="USD"):
        _client(json.dumps(data).encode()).get_rates(date(2026, 10, 4))


def test_requires_eur_even_when_a_non_eur_currency_is_present() -> None:
    data = json.loads(_payload())
    payload = json.dumps([row for row in data if row["Cur_Abbreviation"] != "EUR"]).encode()

    with pytest.raises(RatesUnavailable, match="EUR"):
        _client(payload).get_rates(date(2026, 10, 4))


def test_rejects_snapshot_for_a_different_requested_date() -> None:
    with pytest.raises(RatesUnavailable):
        _client(_payload(on_date="2026-10-03")).get_rates(date(2026, 10, 4))


def test_timeout_is_reported_as_unavailable_without_stale_fallback() -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _Response(_payload())
        raise TimeoutError("timed out")

    clock = iter((0.0, 0.0, 999.0)).__next__
    client = NbrbRateClient(opener=opener, cache_ttl_seconds=10, clock=clock)
    client.get_rates(date(2026, 10, 4))

    with pytest.raises(RatesUnavailable):
        client.get_rates(date(2026, 10, 4))
    assert calls == 2


def test_rejects_oversized_response_before_parsing() -> None:
    client = _client(b"[]" + b" " * 100, max_response_bytes=16)

    with pytest.raises(RatesUnavailable, match="size"):
        client.get_rates(date(2026, 10, 4))


def test_successful_same_date_snapshot_is_cached_but_other_date_reloads() -> None:
    calls = 0

    def opener(request, timeout):
        nonlocal calls
        calls += 1
        requested = "2026-10-04" if "ondate=2026-10-04" in request.full_url else "2026-10-05"
        return _Response(_payload(on_date=requested))

    client = NbrbRateClient(opener=opener)
    first = client.get_rates(date(2026, 10, 4))
    assert client.get_rates(date(2026, 10, 4)) is first
    client.get_rates(date(2026, 10, 5))
    assert calls == 2


def test_simultaneous_same_date_misses_make_one_bounded_upstream_call() -> None:
    calls = 0
    lock = threading.Lock()

    def opener(request, timeout):
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.02)
        return _Response(_payload())

    client = NbrbRateClient(opener=opener)
    results: list[object] = []
    threads = [
        threading.Thread(
            target=lambda: results.append(client.get_rates(date(2026, 10, 4)))
        )
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=1)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 8
    assert calls == 1


def test_fixed_nbrb_host_is_used_and_user_cannot_choose_a_url() -> None:
    seen = []

    def opener(request, timeout):
        seen.append(request.full_url)
        return _Response(_payload())

    client = NbrbRateClient(opener=opener)
    client.get_rates(date(2026, 10, 4))

    assert seen == [
        "https://api.nbrb.by/exrates/rates?periodicity=0&ondate=2026-10-04"
    ]
