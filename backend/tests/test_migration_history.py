from pathlib import Path

from alembic.script import ScriptDirectory


def test_migrations_continue_from_deployed_photo_badge_and_dealer_click_head():
    scripts = ScriptDirectory(str(Path(__file__).parents[1] / "alembic"))
    assert scripts.get_heads() == ["0031_contact_click_analytics"]
    for revision, parent in EXPECTED_REVISIONS.items():
        assert scripts.get_revision(revision).down_revision == parent


EXPECTED_REVISIONS = {'0023_managed_articles': '0022_listing_categories',
 '0024_saved_search_batches': '0023_managed_articles',
 '0025_listing_photo_badges': '0024_saved_search_batches',
 '0026_dealer_click_events': '0025_listing_photo_badges',
 '0027_listing_contact_channels': '0026_dealer_click_events',
 '0028_listing_trust_evidence': '0027_listing_contact_channels',
 '0029_urgent_promotion_service': '0028_listing_trust_evidence',
 '0030_dealer_reviews_and_logo': '0029_urgent_promotion_service',
 '0031_contact_click_analytics': '0030_dealer_reviews_and_logo'}
