import logging

import pytest
from fastapi.testclient import TestClient

from app.api import analytics as analytics_api

ENDPOINT = "/api/v1/analytics/errors"
VALID_REPORT = {
    "error_type": "TypeError",
    "release_id": "audit-20261111-r1",
    "breadcrumbs": ["listing_detail_loaded", "contact_click"],
}


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def recorded_events():
    handler = _RecordingHandler()
    analytics_api.logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        analytics_api.logger.removeHandler(handler)


def _client(integration, ip: str) -> TestClient:
    return TestClient(integration["client"].app, base_url="http://testserver", client=(ip, 50000))


def test_frontend_error_report_is_accepted_and_logged_without_auth(integration, recorded_events):
    response = _client(integration, "198.51.100.81").post(ENDPOINT, json=VALID_REPORT)

    assert response.status_code == 202, response.text
    assert response.json() == {"accepted": True}
    events = [record for record in recorded_events if record.getMessage() == "frontend_error"]
    assert len(events) == 1
    assert events[0].levelno == logging.WARNING
    payload = events[0].avtorinok_structured_data
    assert payload["error_type"] == "TypeError"
    assert payload["release_id"] == "audit-20261111-r1"
    assert payload["breadcrumbs"] == ["listing_detail_loaded", "contact_click"]


def test_frontend_error_report_accepts_empty_breadcrumbs(integration):
    report = {**VALID_REPORT, "breadcrumbs": []}

    response = _client(integration, "198.51.100.82").post(ENDPOINT, json=report)

    assert response.status_code == 202, response.text


@pytest.mark.parametrize(
    "report",
    [
        {**VALID_REPORT, "message": "secret stack"},
        {**VALID_REPORT, "url": "https://example.test/?token=abc"},
        {**VALID_REPORT, "error_type": "E" * 65},
        {**VALID_REPORT, "error_type": "SecretLeakError"},
        {**VALID_REPORT, "release_id": "r" * 65},
        {**VALID_REPORT, "release_id": "bad release?q=1"},
        {**VALID_REPORT, "breadcrumbs": ["contact_click"] * 11},
        {**VALID_REPORT, "breadcrumbs": ["user typed phone +375291234567"]},
        {key: value for key, value in VALID_REPORT.items() if key != "release_id"},
    ],
)
def test_frontend_error_report_rejects_extra_oversize_or_unknown_fields(integration, report):
    response = _client(integration, "198.51.100.83").post(ENDPOINT, json=report)

    assert response.status_code == 422, response.text


def test_frontend_error_report_is_rate_limited_per_ip(integration):
    limited = _client(integration, "198.51.100.84")
    other = _client(integration, "198.51.100.85")

    statuses = [
        limited.post(ENDPOINT, json=VALID_REPORT).status_code
        for _ in range(analytics_api.FRONTEND_ERROR_IP_HOURLY_LIMIT + 1)
    ]

    assert statuses[:-1] == [202] * analytics_api.FRONTEND_ERROR_IP_HOURLY_LIMIT
    assert statuses[-1] == 429
    assert other.post(ENDPOINT, json=VALID_REPORT).status_code == 202
