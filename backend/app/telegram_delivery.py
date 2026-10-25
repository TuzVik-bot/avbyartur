"""Telegram Bot API calls for notification delivery and account linking.

The worker is the only caller. Errors are converted into stable codes so the
outbox machinery can record them without leaking provider details.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

MESSAGE_MAX_CHARS = 3900


class TelegramDeliveryError(Exception):
    """Raised when the Bot API call did not succeed."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def token_from_settings(settings: object) -> str:
    """Read the bot token from real Settings or a substituted test double."""

    token = getattr(settings, "telegram_bot_token", None)
    value = token.get_secret_value() if hasattr(token, "get_secret_value") else token
    return str(value or "").strip()


def _api_url(api_url: str, token: str, method: str) -> str:
    base = api_url.rstrip("/")
    return f"{base}/bot{token}/{method}"


def _post_json(
    api_url: str, token: str, method: str, payload: dict, timeout: int
) -> dict:
    request = urllib.request.Request(
        _api_url(api_url, token, method),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {429} or exc.code >= 500:
            raise TelegramDeliveryError(
                "telegram_temporarily_unavailable", retryable=True
            ) from None
        raise TelegramDeliveryError(
            "telegram_request_rejected", retryable=False
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TelegramDeliveryError("telegram_unreachable", retryable=True) from None
    if not isinstance(body, dict) or body.get("ok") is not True:
        raise TelegramDeliveryError("telegram_request_rejected", retryable=False)
    return body


def send_telegram_message(
    *,
    api_url: str,
    token: str,
    chat_id: int,
    text: str,
    timeout: int,
) -> None:
    """Send one plain-text message; raise TelegramDeliveryError on failure."""

    _post_json(
        api_url,
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text[:MESSAGE_MAX_CHARS],
            "disable_web_page_preview": False,
        },
        timeout,
    )


def fetch_telegram_updates(
    *,
    api_url: str,
    token: str,
    offset: int | None,
    timeout: int,
    poll_seconds: int,
) -> list[dict]:
    """Fetch pending updates; returns an empty list on transient problems."""

    payload: dict = {"timeout": min(poll_seconds, 50), "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    try:
        body = _post_json(api_url, token, "getUpdates", payload, timeout + poll_seconds)
    except TelegramDeliveryError as exc:
        if exc.retryable:
            logger.info("telegram_poll_unavailable", extra={"code": exc.code})
            return []
        raise
    updates = body.get("result")
    return updates if isinstance(updates, list) else []
