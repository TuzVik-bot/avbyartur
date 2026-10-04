from app.main import app


def _response_schema(openapi: dict, path: str, method: str) -> dict:
    response = openapi["paths"][path][method]["responses"]["200"]
    return response["content"]["application/json"]["schema"]


def _component(openapi: dict, ref: str) -> dict:
    prefix = "#/components/schemas/"
    assert ref.startswith(prefix)
    return openapi["components"]["schemas"][ref.removeprefix(prefix)]


def test_authentication_routes_document_typed_responses() -> None:
    openapi = app.openapi()
    expected = {
        ("/api/v1/auth/login", "post"): "AuthSessionResponse",
        ("/api/v1/me", "get"): "AuthSessionResponse",
        ("/api/v1/auth/logout", "post"): "LogoutResponse",
    }

    for (path, method), model_name in expected.items():
        assert _response_schema(openapi, path, method) == {
            "$ref": f"#/components/schemas/{model_name}"
        }

    components = openapi["components"]["schemas"]
    assert set(components["AuthSessionResponse"]["properties"]) == {
        "user", "csrf_token",
    }
    assert components["AuthSessionResponse"]["properties"]["user"] == {
        "$ref": "#/components/schemas/UserOut"
    }
    assert set(components["UserOut"]["properties"]) == {
        "id", "email", "display_name", "role", "company_id", "company_role",
    }
    assert components["LogoutResponse"]["properties"]["ok"]["const"] is True


def test_moderation_routes_document_typed_responses() -> None:
    openapi = app.openapi()
    expected = {
        ("/api/v1/moderation/listings", "get"): "ModerationListingQueueResponse",
        ("/api/v1/moderation/listings/{listing_id}/approve", "post"): "ModerationListingResponse",
        ("/api/v1/moderation/listings/{listing_id}/reject", "post"): "ModerationListingResponse",
        ("/api/v1/moderation/listings/{listing_id}/block", "post"): "ModerationListingResponse",
        ("/api/v1/moderation/companies", "get"): "ModerationCompanyQueueResponse",
        ("/api/v1/moderation/companies/{company_id}/approve", "post"): "ModerationCompanyResponse",
        ("/api/v1/moderation/companies/{company_id}/reject", "post"): "ModerationCompanyResponse",
        ("/api/v1/moderation/companies/{company_id}/block", "post"): "ModerationCompanyResponse",
        ("/api/v1/moderation/reports", "get"): "ModerationReportQueueResponse",
        ("/api/v1/moderation/reports/{report_id}/resolve", "post"): "ModerationReportResponse",
    }

    for (path, method), model_name in expected.items():
        assert _response_schema(openapi, path, method) == {
            "$ref": f"#/components/schemas/{model_name}"
        }


def test_moderation_response_models_preserve_current_privacy_shapes() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]

    listing = components["ModerationListingOut"]["properties"]
    assert {"vin", "moderation_reason"}.issubset(listing)
    assert "contact_phone" not in listing
    queue_listing = components["ModerationListingQueueResponse"]["properties"][
        "items"
    ]["items"]
    assert queue_listing == {"$ref": "#/components/schemas/ModerationListingOut"}
    assert components["ModerationListingQueueResponse"]["properties"][
        "pagination"
    ] == {"$ref": "#/components/schemas/ListingPaginationOut"}

    company_queue = components["ModerationCompanyQueueItemOut"]["properties"]
    assert set(company_queue) == {
        "id", "name", "slug", "unp", "address", "phone", "status", "revision",
    }
    company_action = components["ModerationCompanyActionOut"]["properties"]
    assert set(company_action) == {
        "id", "name", "slug", "status", "revision", "moderation_reason",
    }

    report_queue = components["ModerationReportQueueItemOut"]["properties"]
    assert set(report_queue) == {
        "id", "listing_id", "category", "comment", "status", "revision", "created_at",
    }
    report_action = components["ModerationReportActionOut"]["properties"]
    assert set(report_action) == {"id", "status", "revision", "resolution"}

    for model_name in ("AuthSessionResponse", "LogoutResponse"):
        properties = components[model_name]["properties"]
        assert {"session_hash", "token_hash", "session_cookie"}.isdisjoint(properties)
