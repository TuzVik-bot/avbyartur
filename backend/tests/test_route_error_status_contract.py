from app.main import app

EXPECTED_ROUTE_ERROR_STATUSES: dict[tuple[str, str], set[str]] = {
    ("/api/v1/catalog/category-subtypes", "get"): set(),
    ("/api/v1/vin-check/status", "get"): set(),
    ("/api/v1/customs-calculator/meta", "get"): set(),
    ("/api/v1/customs-calculator/rates", "get"): {"503"},
    ("/api/v1/customs-calculator/calculate", "post"): {"422", "503"},
    ("/api/v1/admin/users", "get"): {"401", "403", "422"},
    ("/api/v1/admin/users/{user_id}", "patch"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/admin/audit", "get"): {"401", "403", "422"},
    ("/api/v1/admin/operations", "get"): {"401", "403"},
    ("/api/v1/admin/catalog/{kind}", "get"): {"401", "403", "422"},
    ("/api/v1/admin/catalog/{kind}/{record_id}", "patch"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/admin/catalog/{kind}/{record_id}/versions", "get"): {"401", "403", "404", "422"},
    ("/api/v1/admin/settings", "get"): {"401", "403"},
    ("/api/v1/admin/settings/{key}", "patch"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/admin/tariffs", "get"): {"401", "403", "422"},
    ("/api/v1/admin/tariffs", "post"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/admin/tariffs/{tariff_id}", "patch"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/admin/tariffs/{tariff_id}", "delete"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/dealer/team", "get"): {"401", "403", "404"},
    ("/api/v1/dealer/team", "post"): {"401", "403", "404", "409", "422"},
    ("/api/v1/dealer/team/{member_id}", "patch"): {"401", "403", "404", "409", "422"},
    ("/api/v1/dealer/analytics", "get"): {"401", "403", "404", "422"},
    ("/api/v1/dealer/feeds", "get"): {"401", "403", "404"},
    ("/api/v1/dealer/feeds/schema", "get"): {"401", "403", "404"},
    ("/api/v1/dealer/feeds/samples/{format_}", "get"): {"401", "403", "404", "422"},
    ("/api/v1/dealer/feeds/{feed_id}/missing-candidates", "get"): {"401", "403", "404", "422"},
    ("/api/v1/dealer/feeds/{feed_id}/missing-candidates/pause", "post"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/dealer/feeds", "post"): {"401", "403", "404", "409", "422"},
    ("/api/v1/dealer/feeds/{feed_id}", "patch"): {"401", "403", "404", "409", "422"},
    ("/api/v1/dealer/feeds/{feed_id}/rotate-token", "post"): {"401", "403", "404", "409"},
    ("/api/v1/dealer/feeds/{feed_id}/imports", "post"): {"401", "403", "404", "409", "413", "422", "429"},
    ("/api/v1/dealer/feeds/{feed_id}/api-imports", "post"): {"401", "403", "409", "413", "422", "429"},
    ("/api/v1/dealer/feed-imports/{run_id}", "get"): {"401", "403", "404"},
    ("/api/v1/dealer/feed-imports/{run_id}/rows", "get"): {"401", "403", "404"},
    ("/api/v1/auth/register", "post"): {"403", "404", "409", "422", "429", "503"},
    ("/api/v1/admin/test-mail/messages", "get"): {"401", "403", "404", "503"},
    ("/api/v1/admin/test-mail/messages/{message_id}", "get"): {"401", "403", "404", "422", "503"},
    ("/api/v1/auth/login", "post"): {"401", "429"},
    ("/api/v1/auth/capabilities", "get"): set(),
    ("/api/v1/listing-options", "get"): set(),
    ("/api/v1/listing-validation-policy", "get"): set(),
    ("/api/v1/listings/public-capabilities", "get"): set(),
    ("/api/v1/me/listings/{listing_id}/catalog-requests", "get"): {"401", "403", "404", "422"},
    ("/api/v1/me/listings/{listing_id}/catalog-requests", "post"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/moderation/catalog-requests", "get"): {"401", "403", "422"},
    ("/api/v1/moderation/catalog-requests/{request_id}/matches", "get"): {"401", "403", "404", "422"},
    ("/api/v1/moderation/catalog-requests/{request_id}/review", "post"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/moderation/listings/{listing_id}/history", "get"): {"401", "403", "404", "422"},
    ("/api/v1/listings/{listing_id}/related", "get"): {"404"},
    ("/api/v1/listings/{listing_id}/analytics", "get"): {"401", "403", "404", "422"},
    ("/api/v1/billing/tariffs", "get"): set(),
    ("/api/v1/billing/orders", "post"): {"401", "403", "404", "409", "422", "503"},
    ("/api/v1/billing/orders", "get"): {"401", "403", "422"},
    ("/api/v1/billing/orders/{order_id}", "get"): {"401", "403", "404"},
    ("/api/v1/billing/callbacks/{provider_name}", "post"): {"401", "404", "409", "413", "422", "503"},
    ("/api/v1/admin/content", "get"): {"401", "403", "422"},
    ("/api/v1/admin/monitoring", "get"): {"401", "403"},
    ("/api/v1/admin/content/{kind}/{key}", "put"): {"401", "403", "409", "422", "429"},
    ("/api/v1/admin/content/{kind}/{key}/versions", "get"): {"401", "403", "404", "422"},
    ("/api/v1/content/{kind}/{key}", "get"): {"404", "422"},
    ("/api/v1/content/articles", "get"): set(),
    ("/api/v1/me/profile", "get"): {"401", "403"},
    ("/api/v1/me/notification-preferences", "get"): {"401", "403"},
    ("/api/v1/me/notification-preferences", "put"): {"401", "403", "409", "422"},
    ("/api/v1/me/profile/phone-change/request", "post"): {"401", "403", "409", "422", "429", "503"},
    ("/api/v1/me/profile/phone-change/confirm", "post"): {"401", "403", "404", "409", "422", "429"},
    ("/api/v1/me/profile", "patch"): {"401", "403", "422"},
    ("/api/v1/me/consents", "get"): {"401", "403"},
    ("/api/v1/me/deletion-requests", "post"): {"401", "403", "409", "422", "429"},
    ("/api/v1/auth/email/verification/request", "post"): {"401", "403", "409", "422", "429", "503"},
    ("/api/v1/auth/email/verification/confirm", "post"): {"401", "409", "422", "429"},
    ("/api/v1/auth/recovery/request", "post"): {"422", "429"},
    ("/api/v1/auth/recovery/confirm", "post"): {"401", "422", "429"},
    ("/api/v1/auth/logout", "post"): {"401", "403"},
    ("/api/v1/auth/otp/csrf", "get"): set(),
    ("/api/v1/auth/otp/request", "post"): {"403", "404", "429", "503"},
    ("/api/v1/auth/otp/verify", "post"): {"401", "403", "404", "429"},
    ("/api/v1/auth/register/otp/request", "post"): {"403", "404", "429", "503"},
    ("/api/v1/me", "get"): {"401", "403"},
    ("/api/v1/me/sessions", "get"): {"401", "403"},
    ("/api/v1/me/sessions/revoke-others", "post"): {"401", "403"},
    ("/api/v1/me/sessions/{session_id}", "delete"): {"401", "403", "404"},
    ("/api/v1/catalog/makes", "get"): set(),
    ("/api/v1/catalog/models", "get"): set(),
    ("/api/v1/catalog/generations", "get"): set(),
    ("/api/v1/catalog/body-types", "get"): set(),
    ("/api/v1/catalog/body-variants", "get"): set(),
    ("/api/v1/catalog/modifications", "get"): set(),
    ("/api/v1/locations/regions", "get"): set(),
    ("/api/v1/locations/cities", "get"): set(),
    ("/api/v1/listings", "get"): {"422"},
    ("/api/v1/listings/count", "get"): {"422"},
    ("/api/v1/listings/{listing_id}", "get"): {"404", "410"},
    ("/api/v1/listings/{listing_id}", "patch"): {"401", "403", "404", "409", "422"},
    ("/api/v1/listings/{listing_id}/phone-reveal", "post"): {"401", "403", "404", "429"},
    ("/api/v1/listings/{listing_id}/reports", "post"): {"401", "403", "404", "429"},
    ("/api/v1/listings/drafts", "post"): {"401", "403", "422"},
    ("/api/v1/listings/{listing_id}/submit", "post"): {"401", "403", "404", "409", "422"},
    ("/api/v1/listings/{listing_id}/pause", "post"): {"401", "403", "404", "409"},
    ("/api/v1/listings/{listing_id}/resume", "post"): {"401", "403", "404", "409"},
    ("/api/v1/listings/{listing_id}/sold", "post"): {"401", "403", "404", "409"},
    ("/api/v1/me/listings", "get"): {"401", "403"},
    ("/api/v1/me/favorites", "get"): {"401", "403"},
    ("/api/v1/me/favorites/{listing_id}", "put"): {"401", "403", "404"},
    ("/api/v1/me/favorites/{listing_id}", "delete"): {"401", "403"},
    ("/api/v1/me/saved-searches", "get"): {"401"},
    ("/api/v1/me/saved-searches", "post"): {"401", "403", "409", "422", "429"},
    ("/api/v1/me/saved-searches/{saved_search_id}", "patch"): {
        "401", "403", "404", "409", "422", "429"
    },
    ("/api/v1/me/saved-searches/{saved_search_id}", "delete"): {
        "401", "403", "404", "429"
    },
    ("/api/v1/me/saved-searches/{saved_search_id}/pause", "post"): {
        "401", "403", "404", "409", "422", "429"
    },
    ("/api/v1/me/saved-searches/{saved_search_id}/resume", "post"): {
        "401", "403", "404", "409", "422", "429"
    },
    ("/api/v1/me/notifications", "get"): {"401"},
    ("/api/v1/me/notifications/{notification_id}/read", "post"): {"401", "403", "404"},
    ("/api/v1/conversations", "get"): {"401"},
    ("/api/v1/conversations", "post"): {"401", "403", "404", "409", "422"},
    ("/api/v1/conversations/{conversation_id}", "get"): {"401", "404"},
    ("/api/v1/conversations/{conversation_id}/messages", "post"): {"401", "403", "404", "409", "422"},
    ("/api/v1/conversations/{conversation_id}/read", "post"): {"401", "403", "404", "422"},
    ("/api/v1/conversations/{conversation_id}/block", "post"): {"401", "403", "404", "422"},
    ("/api/v1/listings/{listing_id}/photos", "post"): {
        "401", "403", "404", "409", "413", "415", "422", "500"
    },
    ("/api/v1/listings/{listing_id}/photos", "get"): {"401", "403", "404"},
    ("/api/v1/listings/{listing_id}/photos/{photo_id}", "delete"): {
        "401", "403", "404", "409"
    },
    ("/api/v1/listings/{listing_id}/photos/reorder", "post"): {
        "401", "403", "404", "409", "422"
    },
    ("/api/v1/listings/{listing_id}/photos/{photo_id}/cover", "post"): {
        "401", "403", "404", "409"
    },
    ("/api/v1/photos/{photo_id}/{size}", "get"): {"404"},
    ("/api/v1/me/company", "get"): {"401", "403"},
    ("/api/v1/companies", "post"): {"401", "403", "409"},
    ("/api/v1/companies/{company_id}", "patch"): {"401", "403", "404", "409"},
    ("/api/v1/dealers", "get"): set(),
    ("/api/v1/dealers/{slug}", "get"): {"404"},
    ("/api/v1/vin-check/status", "get"): set(),
    ("/api/v1/moderation/listings", "get"): {"401", "403"},
    ("/api/v1/moderation/listings/{listing_id}/approve", "post"): {
        "401", "403", "404", "409"
    },
    ("/api/v1/moderation/listings/{listing_id}/reject", "post"): {
        "401", "403", "404", "409", "422"
    },
    ("/api/v1/moderation/listings/{listing_id}/block", "post"): {
        "401", "403", "404", "409", "422"
    },
    ("/api/v1/moderation/companies", "get"): {"401", "403"},
    ("/api/v1/moderation/companies/{company_id}/approve", "post"): {
        "401", "403", "404", "409"
    },
    ("/api/v1/moderation/companies/{company_id}/reject", "post"): {
        "401", "403", "404", "409", "422"
    },
    ("/api/v1/moderation/companies/{company_id}/block", "post"): {
        "401", "403", "404", "409", "422"
    },
    ("/api/v1/moderation/reports", "get"): {"401", "403"},
    ("/api/v1/moderation/reports/{report_id}/resolve", "post"): {
        "401", "403", "404", "409"
    },
}


def test_openapi_documents_exact_route_specific_error_statuses() -> None:
    schema = app.openapi()
    api_operations = {
        (path, method): operation
        for path, path_item in schema["paths"].items()
        if path == "/api/v1" or path.startswith("/api/v1/")
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }

    assert set(api_operations) == set(EXPECTED_ROUTE_ERROR_STATUSES)

    for operation_key, operation in api_operations.items():
        path, method = operation_key
        expected = EXPECTED_ROUTE_ERROR_STATUSES[operation_key]
        responses = operation["responses"]
        actual_route_errors = {
            status
            for status in responses
            if status.isdigit() and status not in {"200", "201", "202", "204", "422"}
        }

        assert actual_route_errors == expected - {"422"}, f"{method.upper()} {path}"
        for status in expected:
            response = responses[status]
            assert response["description"].strip(), f"{method.upper()} {path} {status}"
            assert response["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ApiErrorOut"
            }, f"{method.upper()} {path} {status}"


def test_openapi_documents_dealer_listing_category_fields() -> None:
    summary = app.openapi()["components"]["schemas"]["DealerListingSummaryOut"]

    assert {"category_code", "category_details"} <= set(summary["properties"])
    assert {"category_code", "category_details"} <= set(summary["required"])
