from datetime import UTC, datetime

from app import models
from tests.test_listing_completion import _add_listing, _add_user, _login

# 22:30 UTC on Sep 30 is already 01:30 on Oct 1 in Minsk.
LATE_UTC_EVENING = datetime(2026, 9, 30, 22, 30, tzinfo=UTC)


def test_analytics_period_uses_minsk_calendar_days(integration):
    factory = integration["SessionLocal"]
    owner = _add_user(factory, label="analytics-minsk-owner")
    listing = _add_listing(factory, owner.id, title="Minsk day listing")
    with factory() as db:
        db.add(models.ListingViewEvent(listing_id=listing.id, created_at=LATE_UTC_EVENING))
        db.commit()
    client, _ = _login(integration, owner.email)

    def views(day: str) -> int:
        response = client.get(
            f"/api/v1/listings/{listing.id}/analytics",
            params={"date_from": day, "date_to": day},
        )
        assert response.status_code == 200, response.text
        return response.json()["views"]

    assert views("2026-10-01") == 1
    assert views("2026-09-30") == 0
