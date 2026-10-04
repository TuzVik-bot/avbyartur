from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _current_utc_year() -> int:
    return datetime.now(timezone.utc).year


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="forbid",
        hide_input_in_errors=True,
    )

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://avtorinok:avtorinok@localhost:5432/avtorinok"
    session_secret: SecretStr = SecretStr("development-only-change-me")
    session_cookie_name: str = "avtorinok_session"
    session_cookie_secure: bool = True
    session_days: int = 7
    catalog_path: Path = Path("/app/data/catalog.json")
    media_root: Path = Path("/app/private-media")
    private_listing_quota: int = Field(default=5, ge=1, le=10000)
    company_listing_quota: int = Field(default=50, ge=1, le=10000)
    saved_search_limit: int = Field(default=20, ge=1, le=10000)
    saved_search_mutations_per_hour: int = 60
    upload_max_bytes: int = 20 * 1024 * 1024
    upload_max_pixels: int = 60_000_000
    trusted_proxy_cidrs: str = ""
    sms_login_enabled: bool = False
    public_registration_enabled: bool = False
    email_registration_enabled: bool = False
    public_guest_contact_enabled: bool = False
    sms_otp_secret: SecretStr = SecretStr("")
    sms_otp_lifetime_seconds: int = 300
    sms_otp_max_attempts: int = 5
    sms_otp_sends_per_hour: int = 5
    sms_otp_resend_cooldown_seconds: int = 60
    sms_otp_ip_requests_per_hour: int = 30
    sms_otp_ip_verifications_per_hour: int = 30
    sms_otp_phone_verifications_per_hour: int = 10
    registration_terms_version: str = ""
    registration_privacy_version: str = ""
    sms_provider: str = "disabled"
    smsc_api_key: SecretStr = SecretStr("")
    smsc_api_url: str = "https://smsc.ru/sys/send.php"
    smsc_sender: str = ""
    smsc_timeout_seconds: int = 5
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout_seconds: int = 10
    public_app_url: str = ""
    sentry_dsn: SecretStr = SecretStr("")
    monitoring_status_path: Path | None = None
    listing_stop_words_csv: str = Field(default="", max_length=2000)
    minimum_photos_new: int = Field(default=1, ge=1, le=30)
    minimum_photos_used: int = Field(default=1, ge=1, le=30)
    minimum_photos_damaged: int = Field(default=1, ge=1, le=30)
    minimum_photos_parts: int = Field(default=1, ge=1, le=30)
    listing_year_min: int = Field(default=1886, ge=1886, le=2100)
    listing_future_new_years: int = Field(default=1, ge=0, le=1)

    @model_validator(mode="after")
    def validate_listing_year_range(self) -> "Settings":
        if self.listing_year_min > _current_utc_year():
            raise ValueError("listing_year_min exceeds the current used-year maximum")
        return self

    @field_validator("monitoring_status_path", mode="before")
    @classmethod
    def empty_monitoring_path_is_unconfigured(cls, value):
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_environment_security(self) -> "Settings":
        environment = self.app_env.strip().lower()
        if environment == "prod":
            environment = "production"
        if environment not in {"development", "production"}:
            raise ValueError("APP_ENV must be development or production")
        self.app_env = environment

        if environment == "production":
            if not self.session_cookie_secure:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            secret = self.session_secret.get_secret_value()
            if secret == "development-only-change-me" or len(secret) < 32:
                raise ValueError("SESSION_SECRET must contain at least 32 characters outside development")
        if self.session_days < 1 or self.session_days > 30:
            raise ValueError("SESSION_DAYS must be between 1 and 30")
        if not 60 <= self.sms_otp_lifetime_seconds <= 900:
            raise ValueError("SMS_OTP_LIFETIME_SECONDS must be between 60 and 900")
        if not 1 <= self.sms_otp_max_attempts <= 10:
            raise ValueError("SMS_OTP_MAX_ATTEMPTS must be between 1 and 10")
        if not 1 <= self.sms_otp_sends_per_hour <= 20:
            raise ValueError("SMS_OTP_SENDS_PER_HOUR must be between 1 and 20")
        if not 30 <= self.sms_otp_resend_cooldown_seconds <= 3600:
            raise ValueError("SMS_OTP_RESEND_COOLDOWN_SECONDS must be between 30 and 3600")
        if not 1 <= self.sms_otp_ip_requests_per_hour <= 100:
            raise ValueError("SMS_OTP_IP_REQUESTS_PER_HOUR must be between 1 and 100")
        if not 1 <= self.sms_otp_ip_verifications_per_hour <= 100:
            raise ValueError("SMS_OTP_IP_VERIFICATIONS_PER_HOUR must be between 1 and 100")
        if not 1 <= self.sms_otp_phone_verifications_per_hour <= 20:
            raise ValueError("SMS_OTP_PHONE_VERIFICATIONS_PER_HOUR must be between 1 and 20")
        if self.sms_login_enabled:
            otp_secret = self.sms_otp_secret.get_secret_value()
            if len(otp_secret) < 32:
                raise ValueError("SMS_OTP_SECRET must contain at least 32 characters when SMS login is enabled")
        if self.public_registration_enabled:
            if not self.sms_login_enabled:
                raise ValueError("PUBLIC_REGISTRATION_ENABLED requires SMS_LOGIN_ENABLED")
            if not self.registration_terms_version.strip() or not self.registration_privacy_version.strip():
                raise ValueError("Registration consent document versions must be configured before public registration")
        if self.email_registration_enabled and (
            not self.registration_terms_version.strip() or not self.registration_privacy_version.strip()
        ):
            raise ValueError("Registration consent document versions must be configured before email registration")
        if self.sms_provider not in {"disabled", "smsc"}:
            raise ValueError("SMS_PROVIDER must be disabled or smsc")
        if not self.smsc_api_url.startswith("https://"):
            raise ValueError("SMSC_API_URL must use HTTPS")
        if not 1 <= self.smsc_timeout_seconds <= 30:
            raise ValueError("SMSC_TIMEOUT_SECONDS must be between 1 and 30")
        if not 1 <= self.smtp_port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        if not 1 <= self.smtp_timeout_seconds <= 60:
            raise ValueError("SMTP_TIMEOUT_SECONDS must be between 1 and 60")
        if self.smtp_ssl and self.smtp_starttls:
            raise ValueError("SMTP_SSL and SMTP_STARTTLS cannot both be enabled")
        if bool(self.smtp_username.strip()) != bool(self.smtp_password.get_secret_value().strip()):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together")
        public_app_url = self.public_app_url.strip()
        if public_app_url:
            try:
                parsed_url = urlsplit(public_app_url)
                valid_origin = (
                    parsed_url.scheme == "https"
                    and bool(parsed_url.hostname)
                    and parsed_url.username is None
                    and parsed_url.password is None
                    and parsed_url.path in {"", "/"}
                    and not parsed_url.query
                    and not parsed_url.fragment
                )
            except ValueError:
                valid_origin = False
            if not valid_origin:
                raise ValueError(
                    "PUBLIC_APP_URL must be an HTTPS origin without credentials, path, query, or fragment"
                )
            self.public_app_url = f"https://{parsed_url.netloc}"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
