from fastapi.testclient import TestClient

from app.main import app


def test_vin_check_status_is_explicitly_unavailable_without_a_provider():
    response = TestClient(app).get("/api/v1/vin-check/status")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "available": False,
        "provider": None,
        "supported_categories": [],
        "message": "Поставщик проверки VIN пока не подключён.",
    }
