"""SMTP email transport with safe disabled defaults and sanitized errors."""

from __future__ import annotations

import hashlib
import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings, get_settings


class EmailDeliveryUnavailable(RuntimeError):
    """Safe transport error; provider details and credentials are never retained."""

    def __init__(self, code: str = "email_delivery_failed") -> None:
        self.code = code
        super().__init__("Email delivery is unavailable")


class EmailSender(Protocol):
    @property
    def is_configured(self) -> bool: ...

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        *,
        idempotency_key: str,
    ) -> None: ...


class UnconfiguredEmailSender:
    @property
    def is_configured(self) -> bool:
        return False

    def send_email(self, recipient: str, subject: str, body: str, *, idempotency_key: str) -> None:
        raise EmailDeliveryUnavailable("email_provider_unconfigured")


class SmtpEmailSender:
    def __init__(
        self,
        settings: Settings,
        *,
        smtp_factory=None,
        smtp_ssl_factory=None,
    ) -> None:
        self._settings = settings
        self._smtp_factory = smtp_factory or smtplib.SMTP
        self._smtp_ssl_factory = smtp_ssl_factory or smtplib.SMTP_SSL

    @property
    def is_configured(self) -> bool:
        settings = self._settings
        return bool(settings.smtp_host.strip() and settings.smtp_from.strip())

    def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        *,
        idempotency_key: str,
    ) -> None:
        if not self.is_configured:
            raise EmailDeliveryUnavailable("email_provider_unconfigured")
        if any("\r" in value or "\n" in value for value in (recipient, subject, self._settings.smtp_from)):
            raise EmailDeliveryUnavailable("email_message_invalid")

        message = EmailMessage()
        message["From"] = self._settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        domain = self._settings.smtp_from.rsplit("@", 1)[-1].strip(">< ") or "avtorinok.local"
        stable_id = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        message["Message-ID"] = f"<{stable_id}@{domain}>"
        message.set_content(body)

        settings = self._settings
        try:
            if settings.smtp_ssl:
                with self._smtp_ssl_factory(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                    context=ssl.create_default_context(),
                ) as client:
                    self._authenticate(client)
                    client.send_message(message)
            else:
                with self._smtp_factory(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                ) as client:
                    if settings.smtp_starttls:
                        client.starttls(context=ssl.create_default_context())
                    self._authenticate(client)
                    client.send_message(message)
        except EmailDeliveryUnavailable:
            raise
        except Exception:
            # SMTP exception text can include server replies, usernames, or payload details.
            raise EmailDeliveryUnavailable() from None

    def _authenticate(self, client) -> None:
        username = self._settings.smtp_username.strip()
        password = self._settings.smtp_password.get_secret_value()
        if username:
            client.login(username, password)


def get_email_sender(settings: Settings | None = None) -> EmailSender:
    active_settings = settings or get_settings()
    if active_settings.smtp_host.strip() and active_settings.smtp_from.strip():
        return SmtpEmailSender(active_settings)
    return UnconfiguredEmailSender()
