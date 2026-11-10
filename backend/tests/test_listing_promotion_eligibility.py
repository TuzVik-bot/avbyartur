from fastapi.testclient import TestClient
from test_moderation_risk_signals import _add_listing, _add_user, _moderator_client


def test_owner_sees_eligibility_for_own_listings_only(integration):
    factory = integration["SessionLocal"]
    owner, stranger = _add_user(factory), _add_user(factory)
    active = _add_listing(factory, owner.id, status="active")
    paused = _add_listing(factory, owner.id, status="paused")
    owner_client = _moderator_client(integration, owner.email)
    assert owner_client.get(f"/api/v1/billing/listings/{active.id}/eligibility").json() == {"promotable": True}
    assert owner_client.get(f"/api/v1/billing/listings/{paused.id}/eligibility").json() == {"promotable": False}

    stranger_client = _moderator_client(integration, stranger.email)
    assert stranger_client.get(f"/api/v1/billing/listings/{active.id}/eligibility").status_code == 404
    assert (
        TestClient(integration["client"].app).get(f"/api/v1/billing/listings/{active.id}/eligibility").status_code
        == 401
    )
    assert owner_client.get("/api/v1/billing/listings/not-a-uuid/eligibility").status_code == 422
