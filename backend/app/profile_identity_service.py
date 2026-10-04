"""Shared policy helpers for identity-aware notification delivery."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.config import Settings
from app.profile_identity_models import UserNotificationPreferences
from app.identity_models import VerifiedEmailContact
from app.managed_content import ManagedContent, validate_content
from app.models import User


def verified_email(db: Session, user_id: UUID) -> str | None:
    """Return only the current email after a matching address was verified."""

    user = db.get(User, user_id)
    if user is None or not user.email:
        return None
    contact = db.scalar(
        select(VerifiedEmailContact).where(
            VerifiedEmailContact.user_id == user.id,
            VerifiedEmailContact.email == user.email,
        )
    )
    return contact.email if contact is not None else None


def notification_delivery_allowed(db: Session, user_id: UUID, channel: str) -> bool:
    """Apply the explicit global channel choice at delivery time.

    Email provider availability, public URL, verified-recipient checks and
    saved-search opt-in stay in the worker's existing email branch.
    """

    if channel not in {"web", "email"}:
        return False
    preferences = db.get(UserNotificationPreferences, user_id)
    if preferences is None:
        # Existing accounts were opted in to both channels by their saved
        # search. A missing global row must not silently disable delivery;
        # provider, URL, verified-recipient and per-search gates run later.
        return True
    return preferences.web_enabled if channel == "web" else preferences.email_enabled


def registration_consent_error(
    db: Session,
    settings: Settings,
    supplied_terms_version: str | None,
    supplied_privacy_version: str | None,
) -> str | None:
    """Return a stable failure class for public registration consent.

    Server configuration and managed documents must agree before a public
    registration can be accepted. Client versions are compared to the
    published, approved versions so a stale screen cannot silently consent to
    a newer document.
    """

    configured_terms = str(getattr(settings, "registration_terms_version", "") or "").strip()
    configured_privacy = str(getattr(settings, "registration_privacy_version", "") or "").strip()
    if not configured_terms or not configured_privacy:
        return "unavailable"

    rows = db.scalars(
        select(ManagedContent).where(
            ManagedContent.kind == "legal_document",
            ManagedContent.key.in_(("terms_of_use", "privacy_policy")),
            ManagedContent.status == "published",
        )
    ).all()
    by_key = {row.key: row for row in rows}
    versions: dict[str, str] = {}
    for key in ("terms_of_use", "privacy_policy"):
        row = by_key.get(key)
        if row is None:
            return "unavailable"
        try:
            payload = validate_content(row.kind, row.key, row.payload, row.status)
        except (ValidationError, ValueError, TypeError):
            return "unavailable"
        if not payload.get("approved"):
            return "unavailable"
        versions[key] = str(payload.get("document_version") or "").strip()
        if not versions[key]:
            return "unavailable"

    if versions["terms_of_use"] != configured_terms or versions["privacy_policy"] != configured_privacy:
        return "unavailable"
    if (
        not str(supplied_terms_version or "").strip()
        or not str(supplied_privacy_version or "").strip()
        or str(supplied_terms_version).strip() != versions["terms_of_use"]
        or str(supplied_privacy_version).strip() != versions["privacy_policy"]
    ):
        return "mismatch"
    return None
