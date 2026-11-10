"""Public listing origin, derived only from import audit records."""
import re
from urllib.parse import urlsplit

from sqlalchemy import select

from app.models import AuditEvent


def listing_provenance(db, listings):
    ids = [listing.id for listing in listings]
    if not ids:
        return {}
    rows = db.scalars(select(AuditEvent).where(
        AuditEvent.entity_type == "listing", AuditEvent.entity_id.in_(ids),
        AuditEvent.action == "imported_onliner_listing",
    ).order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())).all()
    result = {}
    for row in rows:
        if row.entity_id in result:
            continue
        details = row.details if isinstance(row.details, dict) else {}
        url = details.get("source_url")
        verified = None
        if details.get("source") == "onliner.by" and isinstance(url, str):
            try:
                parsed = urlsplit(url)
                source_id = str(details.get("source_id", ""))
                if (parsed.scheme == "https" and parsed.netloc == "ab.onliner.by"
                    and not parsed.query and not parsed.fragment
                    and re.fullmatch(r"/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[0-9]+/?", parsed.path)
                    and parsed.path.rstrip("/").rsplit("/", 1)[-1] == source_id):
                    verified = {"source_name": "onliner.by", "original_url": url, "imported": True}
            except ValueError:
                pass
        result[row.entity_id] = (row.actor_id, verified)
    return result
