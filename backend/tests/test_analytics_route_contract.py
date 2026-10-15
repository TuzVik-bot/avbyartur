from app.main import app


def test_analytics_endpoints_are_registered_in_main_openapi() -> None:
    paths = app.openapi()["paths"]

    assert paths["/api/v1/analytics/events"]["post"]["operationId"] == "contact_click_api_v1_analytics_events_post"
    assert paths["/api/v1/analytics/errors"]["post"]["operationId"] == "report_frontend_error_api_v1_analytics_errors_post"
