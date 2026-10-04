"""Provider-neutral helpers for Belarus mobile SMS authentication."""

import hashlib
import hmac
import json
import re
import secrets
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import SecretStr


class SmsProviderUnavailable(RuntimeError):
    """Raised when SMS delivery cannot be performed without leaking details."""


class SmsCodeProvider(Protocol):
    @property
    def is_configured(self) -> bool: ...

    def send_code(self, phone_e164: str, code: str, *, idempotency_key: str) -> None: ...


class UnconfiguredSmsCodeProvider:
    """Explicit safe default; a real vendor adapter must be supplied separately."""

    @property
    def is_configured(self) -> bool:
        return False

    def send_code(self, phone_e164: str, code: str, *, idempotency_key: str) -> None:
        raise SmsProviderUnavailable("SMS provider is not configured")


class SmscSmsCodeProvider:
    """SMSC.ru HTTPS adapter; application idempotency remains authoritative."""

    def __init__(
        self,
        api_key: SecretStr,
        *,
        sender: str = "",
        api_url: str = "https://smsc.ru/sys/send.php",
        timeout_seconds: int = 5,
        opener=urlopen,
    ) -> None:
        self._api_key = api_key
        self._sender = sender.strip()
        self._api_url = api_url
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key.get_secret_value().strip()) and self._api_url.startswith("https://")

    def send_code(self, phone_e164: str, code: str, *, idempotency_key: str) -> None:
        if not self.is_configured:
            raise SmsProviderUnavailable("SMS provider is not configured")
        fields = {
            "apikey": self._api_key.get_secret_value(),
            "phones": phone_e164,
            "mes": f"Код для входа в Авторынок: {code}. Никому не сообщайте код.",
            "fmt": "3",
        }
        if self._sender:
            fields["sender"] = self._sender
        # SMSC's caller-supplied id is a correlation value, not a delivery guarantee.
        fields["id"] = str(int(hashlib.sha256(idempotency_key.encode()).hexdigest()[:8], 16))
        request = Request(
            self._api_url,
            data=urlencode(fields).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception:
            # Third-party exception text may contain credentials or message data.
            raise SmsProviderUnavailable("SMS delivery status is unavailable") from None
        if not isinstance(result, dict) or result.get("error") or result.get("error_code"):
            raise SmsProviderUnavailable("SMS provider rejected the delivery request")


_PHONE_SEPARATORS = re.compile(r"[\s().-]+")
_BELARUS_MOBILE = re.compile(r"^\+375(?:25|29|33|44)\d{7}$")


def normalize_belarus_mobile_phone(value: str) -> str:
    """Normalize common Belarus mobile input forms to canonical E.164."""
    compact = _PHONE_SEPARATORS.sub("", value.strip())
    if compact.startswith("+"):
        digits = compact[1:]
    else:
        digits = compact
    if digits.startswith("375"):
        normalized = "+" + digits
    elif digits.startswith("0") and len(digits) == 10:
        normalized = "+375" + digits[1:]
    elif len(digits) == 9:
        normalized = "+375" + digits
    else:
        normalized = "+" + digits
    if _BELARUS_MOBILE.fullmatch(normalized) is None:
        raise ValueError("Phone must be a supported Belarus mobile number")
    return normalized


def create_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_code_digest(phone_e164: str, code: str, key: str) -> str:
    payload = b"avtorinok:sms-otp:v1:" + phone_e164.encode() + b":" + code.encode()
    return hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def phone_subject_digest(phone_e164: str, key: str) -> str:
    payload = b"avtorinok:sms-otp-phone:v1:" + phone_e164.encode()
    return hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def idempotency_key_digest(phone_e164: str, key: str, idempotency_key: str) -> str:
    payload = b"avtorinok:sms-otp-idempotency:v1:" + phone_e164.encode() + b":" + idempotency_key.encode()
    return hmac.new(key.encode(), payload, hashlib.sha256).hexdigest()


def digest_matches(expected: str, provided: str) -> bool:
    return hmac.compare_digest(expected.encode("ascii"), provided.encode("ascii"))
