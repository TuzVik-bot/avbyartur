"""Optional Sentry boundary with strict local redaction and fail-open transport."""

import re
from threading import Lock
from typing import Any

from app.config import get_settings
from app.logging_config import REQUEST_ID_PATTERN, redact_text

_configured_dsn: str | None = None
_configuration_lock = Lock()
_delivery_counts = {"attempted": 0, "accepted": 0, "failed": 0}

_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,79}")
_EVENT_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
# Frame keys that describe code location only; vars and source context are dropped.
_FRAME_KEYS = ("filename", "abs_path", "function", "module", "lineno", "in_app")
_MAX_FRAMES = 100
_MAX_EXCEPTIONS = 10


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


def _scrub_tags(source: Any) -> dict:
    source_tags = source if isinstance(source, dict) else {}
    tags = {}
    for name in ("component", "error_type"):
        value = source_tags.get(name)
        if isinstance(value, str) and _NAME_PATTERN.fullmatch(value):
            tags[name] = value
    correlation = source_tags.get("request_id")
    if isinstance(correlation, str) and REQUEST_ID_PATTERN.fullmatch(correlation):
        tags["request_id"] = correlation
    return tags


def _scrub_frame(frame: Any) -> dict:
    if not isinstance(frame, dict):
        return {}
    return {key: frame[key] for key in _FRAME_KEYS if isinstance(frame.get(key), (str, int, bool))}


def _scrub_exception_value(value: Any) -> dict | None:
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        return None
    cleaned: dict = {"type": value["type"][:200]}
    if isinstance(value.get("value"), str):
        cleaned["value"] = redact_text(value["value"])
    if isinstance(value.get("module"), str) and _NAME_PATTERN.fullmatch(value["module"]):
        cleaned["module"] = value["module"]
    mechanism = value.get("mechanism")
    if isinstance(mechanism, dict) and isinstance(mechanism.get("type"), str):
        cleaned["mechanism"] = {"type": mechanism["type"][:80], "handled": mechanism.get("handled") is not False}
    stacktrace = value.get("stacktrace")
    frames = stacktrace.get("frames") if isinstance(stacktrace, dict) else None
    if isinstance(frames, list):
        cleaned["stacktrace"] = {"frames": [_scrub_frame(frame) for frame in frames[-_MAX_FRAMES:]]}
    return cleaned


def _scrub_exception(exception: Any) -> dict | None:
    values = exception.get("values") if isinstance(exception, dict) else None
    if not isinstance(values, list):
        return None
    cleaned = [item for item in (_scrub_exception_value(value) for value in values[-_MAX_EXCEPTIONS:]) if item]
    return {"values": cleaned} if cleaned else None


def _scrub_request(request: Any) -> dict | None:
    """Keep only the HTTP method and URL path: no query, headers, cookies, body or env."""
    if not isinstance(request, dict):
        return None
    cleaned = {}
    method = request.get("method")
    if isinstance(method, str) and method.upper() in _HTTP_METHODS:
        cleaned["method"] = method.upper()
    url = request.get("url")
    if isinstance(url, str):
        path = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/]*", "", url).split("?", 1)[0].split("#", 1)[0]
        if path.startswith("/"):
            cleaned["url"] = path[:500]
    return cleaned or None


def scrub_error_event(event: dict, hint: dict | None = None) -> dict:
    """Build a new event from allowlisted fields only (Sentry before_send hook)."""
    tags = _scrub_tags(event.get("tags"))
    cleaned: dict = {"message": tags.get("error_type", "error"), "level": "error", "tags": tags}
    event_id = event.get("event_id")
    if isinstance(event_id, str) and _EVENT_ID_PATTERN.fullmatch(event_id):
        cleaned["event_id"] = event_id
    for key in ("platform", "timestamp"):
        if isinstance(event.get(key), str):
            cleaned[key] = event[key]
    exception = _scrub_exception(event.get("exception"))
    if exception:
        cleaned["exception"] = exception
    request = _scrub_request(event.get("request"))
    if request:
        cleaned["request"] = request
    return cleaned


def _ensure_initialized(sentry_sdk, dsn: str) -> None:
    global _configured_dsn
    with _configuration_lock:
        if _configured_dsn == dsn:
            return
        sentry_sdk.init(
            dsn=dsn, default_integrations=False, auto_enabling_integrations=False,
            send_default_pii=False, include_local_variables=False, include_source_context=False,
            max_request_body_size="never", traces_sample_rate=0.0,
            before_send=scrub_error_event, before_breadcrumb=lambda *_: None,
            debug=False, send_client_reports=False,
        )
        _configured_dsn = dsn


def _capture_exception(sentry_sdk, exc: BaseException, tags: dict, method: str | None, path: str | None):
    request = {"method": method, "url": path} if method or path else None

    def attach_request(event: dict, _hint: dict) -> dict:
        return {**event, "request": request} if request else event

    with sentry_sdk.new_scope() as scope:
        for name, value in tags.items():
            scope.set_tag(name, value)
        scope.add_event_processor(attach_request)
        return sentry_sdk.capture_exception(exc)


def capture_safe_error(
    component: str,
    error_type: str,
    *,
    request_id: str | None = None,
    exc: BaseException | None = None,
    method: str | None = None,
    path: str | None = None,
) -> None:
    """Report an error to Sentry when configured; with ``exc`` the stack frames are sent."""
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
        _ensure_initialized(sentry_sdk, dsn)
        tags = {"component": component, "error_type": error_type}
        if request_id:
            tags["request_id"] = request_id
        if exc is not None:
            accepted = _capture_exception(sentry_sdk, exc, tags, method, path)
        else:
            accepted = sentry_sdk.capture_event(scrub_error_event({"message": error_type, "tags": tags}, {}))
        with _configuration_lock:
            _delivery_counts["accepted" if accepted else "failed"] += 1
    except Exception:  # noqa: BLE001 - an optional Sentry transport must fail open.
        with _configuration_lock:
            _delivery_counts["failed"] += 1
        return
