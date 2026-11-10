"""Read-only commercial preflight; it cannot verify actual delivery or approval."""

import json

from app.email_delivery import get_email_sender
from app.profile_identity_service import registration_consent_error


def assess_commercial_readiness(db, settings) -> dict[str, bool]:
    documents_valid = registration_consent_error(
        db, settings, settings.registration_terms_version, settings.registration_privacy_version
    ) is None
    return {
        "registration_enabled": bool(settings.email_registration_enabled),
        "pilot_disabled": not settings.email_registration_pilot_enabled,
        "test_mail_disabled": not settings.test_mail_enabled,
        "smtp_configured": get_email_sender(settings).is_configured,
        "public_app_url_configured": bool(settings.public_app_url.strip()),
        "managed_registration_documents": documents_valid,
        # A configuration check cannot establish either actual approval or delivery.
        "human_document_approval_verified": False,
        "live_delivery_verified": False,
        "ready": False,
    }


def main() -> int:
    try:
        from app.config import get_settings
        from app.db import SessionLocal

        with SessionLocal() as db:
            result = assess_commercial_readiness(db, get_settings())
    except Exception:
        # Connection and configuration errors can contain credentials or addresses.
        print('{"preflight_error": true, "ready": false}')
        return 1
    print(json.dumps(result, sort_keys=True))
    return 1  # Manual approval and real delivery always remain outstanding here.


if __name__ == "__main__":
    raise SystemExit(main())
