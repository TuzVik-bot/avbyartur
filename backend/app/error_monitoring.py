"""Optional Sentry boundary with strict local redaction and fail-open transport."""

import re
from threading import Lock

from app.config import get_settings

_configured_dsn: str | None = None
_configuration_lock = Lock()
_delivery_counts = {"attempted": 0, "accepted": 0, "failed": 0}


def error_delivery_snapshot() -> dict:
    """Return only local aggregate counts; Sentry gives no remote delivery receipt."""
    try:
        configured = bool(get_settings().sentry_dsn.get_secret_value().strip())
    except Exception:  # noqa: BLE001 - monitoring must fail open when settings are unavailable.
        configured = False
    if not configured:
        return {"configured": False, "attempted": None, "accepted": None, "failed": None}
    with _configuration_lock:
        return {"configured": True, **_delivery_counts}


def scrub_error_event(event: dict, hint: dict | None = None) -> dict:
    source_tags = event.get("tags") if isinstance(event.get("tags"), dict) else {}
    tags = {}
    for name in ("component", "error_type"):
        value = source_tags.get(name)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,79}", value):
            tags[name] = value
    correlation = source_tags.get("request_id")
    if isinstance(correlation, str) and re.fullmatch(r"[0-9a-f]{32}", correlation):
        tags["request_id"] = correlation
    cleaned = {"message": tags.get("error_type", "error"), "level": "error", "tags": tags}
    event_id = event.get("event_id")
    if isinstance(event_id, str) and re.fullmatch(r"[0-9a-f]{32}", event_id):
        cleaned["event_id"] = event_id
    return cleaned


def capture_safe_error(component: str, error_type: str, *, request_id: str | None = None) -> None:
    global _configured_dsn
    try:
        dsn = get_settings().sentry_dsn.get_secret_value().strip()
    except Exception:  # noqa: BLE001 - optional error reporting never breaks application errors.
        return
    if not dsn:
        return
    with _configuration_lock:
        _delivery_counts["attempted"] += 1
    try:
        import sentry_sdk
        with _configuration_lock:
            if _configured_dsn != dsn:
                sentry_sdk.init(
                    dsn=dsn, default_integrations=False, auto_enabling_integrations=False,
                    send_default_pii=False, include_local_variables=False, include_source_context=False,
                    max_request_body_size="never", traces_sample_rate=0.0,
                    before_send=scrub_error_event, before_breadcrumb=lambda *_: None,
                    debug=False, send_client_reports=False,
                )
                _configured_dsn = dsn
        event = {"message": error_type, "tags": {"component": component, "error_type": error_type}}
        if request_id:
            event["tags"]["request_id"] = request_id
        accepted = sentry_sdk.capture_event(scrub_error_event(event, {}))
        with _configuration_lock:
            _delivery_counts["accepted" if accepted else "failed"] += 1
    except Exception:  # noqa: BLE001 - an optional Sentry transport must fail open.
        with _configuration_lock:
            _delivery_counts["failed"] += 1
        return
