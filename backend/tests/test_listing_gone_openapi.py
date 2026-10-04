from app.main import app


def test_public_listing_detail_documents_archived_gone_response() -> None:
    response = app.openapi()["paths"]["/api/v1/listings/{listing_id}"]["get"]["responses"]["410"]

    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ApiErrorOut"
    }
