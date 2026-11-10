from app.main import app
from app.services import MAX_PAGE


def test_moderation_listing_queue_caps_page_number():
    parameters = app.openapi()["paths"]["/api/v1/moderation/listings"]["get"]["parameters"]
    page = next(item for item in parameters if item["name"] == "page")

    assert page["schema"]["maximum"] == MAX_PAGE
    assert page["schema"]["minimum"] == 1
