"""Explicitly enabled temporary registration terms for the test service."""
from app.profile_identity_service import registration_consent_error

PILOT_TERMS_VERSION = "pilot-email-terms-2026-10-05-v2"
PILOT_PRIVACY_VERSION = "pilot-email-privacy-2026-10-05-v2"


def email_registration_consent_error(db, settings, terms_version, privacy_version):
    if settings.email_registration_pilot_enabled:
        if (settings.registration_terms_version != PILOT_TERMS_VERSION
                or settings.registration_privacy_version != PILOT_PRIVACY_VERSION):
            return "unavailable"
        if terms_version != PILOT_TERMS_VERSION or privacy_version != PILOT_PRIVACY_VERSION:
            return "mismatch"
        return None
    return registration_consent_error(db, settings, terms_version, privacy_version)
