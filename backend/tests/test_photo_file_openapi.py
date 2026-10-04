from app.main import app


def test_processed_photo_is_documented_as_binary_webp() -> None:
    response = app.openapi()["paths"]["/api/v1/photos/{photo_id}/{size}"]["get"]["responses"]["200"]

    assert response["content"] == {
        "image/webp": {"schema": {"type": "string", "format": "binary"}}
    }
