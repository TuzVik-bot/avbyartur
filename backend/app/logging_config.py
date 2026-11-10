import json
import logging
import os
import re
import sys
import traceback
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from types import TracebackType
from typing import Any
from uuid import uuid4

_request_id: ContextVar[str | None] = ContextVar("avtorinok_request_id", default=None)
_STRUCTURED_DATA = "avtorinok_structured_data"
_JSON_HANDLER_MARKER = "_avtorinok_json_handler"

REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{8,128}")
ERROR_MESSAGE_MAX_CHARS = 500
TRACEBACK_MAX_CHARS = 16000
_REDACTED = "[redacted]"
# Ordered: broad structural patterns first, then single values.
_MESSAGE_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\[parameters:.*", re.DOTALL), "[parameters: redacted]"),
    (re.compile(r"(?m)^(\s*DETAIL:).*$"), r"\1 " + _REDACTED),
    (re.compile(r"/bot[^/\s]+"), "/bot" + _REDACTED),
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}"), _REDACTED),
    (re.compile(r"\?[^\s'\"<>]*"), "?" + _REDACTED),
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer " + _REDACTED),
    (
        re.compile(
            r"(?i)\b(token|access_token|refresh_token|password|passwd|secret|api_key|apikey"
            r"|authorization|cookie|session)(\s*[=:]\s*)[^\s,;&'\")}\]]+"
        ),
        r"\1\2" + _REDACTED,
    ),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), _REDACTED),
    (re.compile(r"\+\d[\d\s()-]{7,18}\d"), _REDACTED),
)

ExcInfo = (
    bool
    | BaseException
    | tuple[type[BaseException], BaseException, TracebackType | None]
    | tuple[None, None, None]
    | None
)


class JsonLogFormatter(logging.Formatter):
    """Format application events as one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = dict(getattr(record, _STRUCTURED_DATA, {}))
        payload.setdefault(
            "timestamp",
            datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        )
        payload.setdefault("level", record.levelname.lower())
        payload.setdefault("logger", record.name)
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def configure_json_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    has_json_handler = any(
        getattr(handler, _JSON_HANDLER_MARKER, False) for handler in logger.handlers
    )
    if not has_json_handler:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonLogFormatter())
        setattr(handler, _JSON_HANDLER_MARKER, True)
        logger.addHandler(handler)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level if isinstance(level, int) else logging.INFO)
    logger.propagate = False
    return logger


def accept_request_id(incoming: str | None) -> str:
    """Reuse a proxy-supplied request id when it is safe to echo, else mint one."""
    if incoming and REQUEST_ID_PATTERN.fullmatch(incoming):
        return incoming
    return uuid4().hex


def redact_text(text: str, *, limit: int = ERROR_MESSAGE_MAX_CHARS) -> str:
    """Strip query strings, credentials and contact data from free-form text."""
    for pattern, replacement in _MESSAGE_REDACTIONS:
        text = pattern.sub(replacement, text)
    return text[:limit]


def safe_exception_message(exc: BaseException) -> str:
    try:
        message = str(exc)
    except Exception:  # noqa: BLE001 - a broken __str__ must not break error logging.
        message = ""
    return redact_text(message)


def _format_frame(frame: traceback.FrameSummary) -> str:
    line = f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
    if frame.line:
        line += f"    {redact_text(frame.line.strip())}\n"
    return line


def format_safe_traceback(exc: BaseException) -> str:
    """Render the frame stack of an exception chain without locals or raw messages."""
    rendered: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        block = "Traceback (most recent call last):\n" + "".join(
            _format_frame(frame) for frame in traceback.extract_tb(current.__traceback__)
        )
        block += f"{type(current).__qualname__}: {safe_exception_message(current)}\n"
        rendered.insert(0, block)
        if current.__cause__ is not None:
            rendered.insert(0, "")
            current = current.__cause__
        elif current.__context__ is not None and not current.__suppress_context__:
            current = current.__context__
        else:
            current = None
    return "\n".join(part for part in rendered if part)[-TRACEBACK_MAX_CHARS:]


def _resolve_exception(exc_info: ExcInfo) -> BaseException | None:
    if exc_info is True:
        return sys.exc_info()[1]
    if isinstance(exc_info, BaseException):
        return exc_info
    if isinstance(exc_info, tuple) and len(exc_info) == 3:
        return exc_info[1]
    return None


def bind_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    exc_info: ExcInfo = None,
    **fields: Any,
) -> None:
    """Emit one JSON event; ``exc_info`` adds a redacted, locals-free ``traceback``."""
    payload: dict[str, Any] = {"event": event}
    request_id = _request_id.get()
    if request_id:
        payload["request_id"] = request_id
    payload.update(fields)
    exception = _resolve_exception(exc_info)
    if exception is not None:
        payload["traceback"] = format_safe_traceback(exception)
    logger.log(level, event, extra={_STRUCTURED_DATA: payload})
