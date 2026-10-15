"""Optional Sentry boundary with strict local redaction and fail-open transport."""

import os
import re
from threading import Lock

from app.config import get_settings

_configured_dsn: str | None = None
_configuration_lock = Lock()
_delivery_counts = {"attempted": 0, "accepted": 0, "failed": 0}
_RELEASE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
_BREADCRUMBS = frozenset({
    "listing_detail_loaded", "contact_click", "contact_reveal_success",
    "internal_chat_opened", "api_request_failed",
})


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


def _safe_breadcrumbs(values) -> list[dict[str, str]]:
    if not isinstance(values, (list, tuple)):
        return []
    cleaned = []
    for value in values[:10]:
        category = value if isinstance(value, str) else value.get("category") if isinstance(value, dict) else None
        if isinstance(category, str) and category in _BREADCRUMBS:
            cleaned.append({"category": category, "message": category, "level": "info"})
    return cleaned


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
    release_id = event.get("release")
    if isinstance(release_id, str) and _RELEASE_PATTERN.fullmatch(release_id):
        cleaned["release"] = release_id
    raw_breadcrumbs = event.get("breadcrumbs")
    if isinstance(raw_breadcrumbs, dict):
        values = raw_breadcrumbs.get("values")
        clean_values = _safe_breadcrumbs(values)
        if clean_values:
            cleaned["breadcrumbs"] = {"values": clean_values}
    return cleaned


def capture_safe_error(
    component: str,
    error_type: str,
    *,
    request_id: str | None = None,
    release_id: str | None = None,
    breadcrumbs: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """Send only allowlisted metadata; return true only when Sentry accepts it."""
    global _configured_dsn
    try:
        settings = get_settings()
        dsn = settings.sentry_dsn.get_secret_value().strip()
    except Exception:  # noqa: BLE001 - optional error reporting never breaks application errors.
        return False
    if not dsn:
        return False
    release = release_id if isinstance(release_id, str) and _RELEASE_PATTERN.fullmatch(release_id) else None
    if release is None:
        candidate = os.environ.get("RELEASE_ID", "")
        release = candidate if _RELEASE_PATTERN.fullmatch(candidate) else None
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
        if release:
            event["release"] = release
        safe_breadcrumbs = _safe_breadcrumbs(breadcrumbs or [])
        if safe_breadcrumbs:
            event["breadcrumbs"] = {"values": safe_breadcrumbs}
        accepted = bool(sentry_sdk.capture_event(scrub_error_event(event, {})))
        with _configuration_lock:
            _delivery_counts["accepted" if accepted else "failed"] += 1
        return accepted
    except Exception:  # noqa: BLE001 - an optional Sentry transport must fail open.
        with _configuration_lock:
            _delivery_counts["failed"] += 1
        return False
