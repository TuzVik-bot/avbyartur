from app.main import app
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

client = TestClient(app)


def test_validation_error_has_russian_message_and_stable_error_types():
    response = client.get("/api/v1/listings", params={"page": 0})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Проверьте правильность заполнения полей"
    assert isinstance(body["field_errors"]["page"], str)
    assert body["field_error_types"] == {"page": "greater_than_equal"}
    assert body["field_error_context"] == {"page": {"ge": 1}}


def test_validation_error_without_context_omits_context_entry():
    response = client.get("/api/v1/listings", params={"page": "abc"})

    body = response.json()
    assert body["field_error_types"] == {"page": "int_parsing"}
    assert body["field_error_context"] == {}


def test_validation_error_context_keeps_only_primitive_values():
    class Payload(BaseModel):
        name: str

        @field_validator("name")
        @classmethod
        def reject(cls, value: str) -> str:
            raise ValueError("secret-value-error")

    @app.post("/api/v1/__validation_ctx_test")
    def _endpoint(payload: Payload) -> dict:
        return {}

    route = next(
        r
        for r in app.routes
        if getattr(r, "path", None) == "/api/v1/__validation_ctx_test"
    )
    try:
        response = client.post("/api/v1/__validation_ctx_test", json={"name": "x"})
    finally:
        app.router.routes.remove(route)

    body = response.json()
    assert body["field_error_types"] == {"name": "value_error"}
    assert body["field_error_context"] == {}
