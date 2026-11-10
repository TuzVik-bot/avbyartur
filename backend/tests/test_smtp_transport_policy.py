"""Production must not send SMTP credentials over an unencrypted connection."""

import pytest
from pydantic import ValidationError

from app.config import Settings

PRODUCTION = {"app_env": "production", "session_secret": "x" * 40, "session_cookie_secure": True}


def test_production_rejects_plaintext_smtp_to_remote_host():
    with pytest.raises(ValidationError, match="SMTP_STARTTLS or SMTP_SSL"):
        Settings(**PRODUCTION, smtp_host="smtp.example.com", smtp_starttls=False, smtp_ssl=False)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "mailpit", "test-mail", ""])
def test_production_allows_plaintext_smtp_to_local_capture(host):
    settings = Settings(**PRODUCTION, smtp_host=host, smtp_starttls=False, smtp_ssl=False)

    assert settings.smtp_starttls is False


@pytest.mark.parametrize(("starttls", "ssl"), [(True, False), (False, True)])
def test_production_allows_encrypted_smtp(starttls, ssl):
    settings = Settings(**PRODUCTION, smtp_host="smtp.example.com", smtp_starttls=starttls, smtp_ssl=ssl)

    assert settings.smtp_host == "smtp.example.com"


def test_development_allows_plaintext_smtp():
    settings = Settings(app_env="development", smtp_host="smtp.example.com", smtp_starttls=False, smtp_ssl=False)

    assert settings.smtp_ssl is False
