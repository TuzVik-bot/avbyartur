import json
import logging
import os
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("avtorinok_request_id", default=None)
_STRUCTURED_DATA = "avtorinok_structured_data"
_JSON_HANDLER_MARKER = "_avtorinok_json_handler"


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


def bind_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> None:
    payload: dict[str, Any] = {"event": event}
    request_id = _request_id.get()
    if request_id:
        payload["request_id"] = request_id
    payload.update(fields)
    logger.log(level, event, extra={_STRUCTURED_DATA: payload})
