from app.main import app


def test_health_routes_document_status_response() -> None:
    schema = app.openapi()
    health_response = {"$ref": "#/components/schemas/HealthResponse"}

    live = schema["paths"]["/health/live"]["get"]["responses"]
    ready = schema["paths"]["/health/ready"]["get"]["responses"]

    assert live["200"]["content"]["application/json"]["schema"] == health_response
    assert ready["200"]["content"]["application/json"]["schema"] == health_response
    assert ready["503"]["content"]["application/json"]["schema"] == health_response
