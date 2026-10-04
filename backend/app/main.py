import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import account, admin, admin_catalog, admin_settings, auth, billing, catalog, companies, conversations, dealer, feeds, listings, managed_content, media, moderation, monitoring, notifications, profile_identity, saved_searches
from app.api import admin_tariffs, catalog_requests, customs_calculator, vin_checks
from app.config import get_settings
from app.db import SessionLocal
from app.health_schemas import HealthResponse
from app.logging_config import (
    bind_request_id,
    configure_json_logger,
    log_event,
    reset_request_id,
)
from app.schemas import ApiErrorOut

settings = get_settings()
app = FastAPI(
    title="Авторынок API",
    version="1.0.0",
    docs_url="/docs" if settings.app_env.lower() == "development" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.app_env.lower() == "development" else None,
)
logger = configure_json_logger("avtorinok.api")
# Replace Uvicorn's unstructured access line, which includes the query string,
# with the correlated application event emitted by request_context below.
logging.getLogger("uvicorn.access").disabled = True
MULTIPART_OVERHEAD_LIMIT = 64 * 1024
FEED_REQUEST_LIMIT = 10 * 1024 * 1024
IDEMPOTENCY_REQUIRED_OPERATIONS = {
    ("/api/v1/auth/otp/request", "post"),
    ("/api/v1/auth/register/otp/request", "post"),
    ("/api/v1/listings/drafts", "post"),
    ("/api/v1/listings/{listing_id}/submit", "post"),
    ("/api/v1/listings/{listing_id}/photos", "post"),
    ("/api/v1/me/saved-searches", "post"),
    ("/api/v1/conversations", "post"),
    ("/api/v1/conversations/{conversation_id}/messages", "post"),
    ("/api/v1/conversations/{conversation_id}/read", "post"),
    ("/api/v1/conversations/{conversation_id}/block", "post"),
    ("/api/v1/dealer/feeds/{feed_id}/imports", "post"),
    ("/api/v1/dealer/feeds/{feed_id}/api-imports", "post"),
    ("/api/v1/dealer/feeds/{feed_id}/missing-candidates/pause", "post"),
    ("/api/v1/billing/orders", "post"),
    ("/api/v1/me/profile/phone-change/request", "post"),
    ("/api/v1/me/listings/{listing_id}/catalog-requests", "post"),
}
CSRF_REQUIRED_OPERATIONS = {
    ("/api/v1/auth/otp/request", "post"),
    ("/api/v1/auth/register/otp/request", "post"),
    ("/api/v1/auth/otp/verify", "post"),
    ("/api/v1/me/notification-preferences", "put"),
    ("/api/v1/me/profile/phone-change/request", "post"),
    ("/api/v1/me/profile/phone-change/confirm", "post"),
}
ROUTE_ERROR_STATUSES: dict[tuple[str, str], tuple[int, ...]] = {
    ("/api/v1/vin-check/status", "get"): (),
    ("/api/v1/customs-calculator/meta", "get"): (),
    ("/api/v1/customs-calculator/calculate", "post"): (422, 503),
    ("/api/v1/admin/users", "get"): (401, 403, 422),
    ("/api/v1/admin/users/{user_id}", "patch"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/admin/audit", "get"): (401, 403, 422),
    ("/api/v1/admin/operations", "get"): (401, 403),
    ("/api/v1/admin/catalog/{kind}", "get"): (401, 403, 422),
    ("/api/v1/admin/catalog/{kind}/{record_id}", "patch"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/admin/catalog/{kind}/{record_id}/versions", "get"): (401, 403, 404, 422),
    ("/api/v1/admin/settings", "get"): (401, 403),
    ("/api/v1/admin/settings/{key}", "patch"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/admin/tariffs", "get"): (401, 403, 422),
    ("/api/v1/admin/tariffs", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/admin/tariffs/{tariff_id}", "patch"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/admin/tariffs/{tariff_id}", "delete"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/dealer/team", "get"): (401, 403, 404),
    ("/api/v1/dealer/team", "post"): (401, 403, 404, 409, 422),
    ("/api/v1/dealer/team/{member_id}", "patch"): (401, 403, 404, 409, 422),
    ("/api/v1/dealer/analytics", "get"): (401, 403, 404, 422),
    ("/api/v1/dealer/feeds", "get"): (401, 403, 404),
    ("/api/v1/dealer/feeds/schema", "get"): (401, 403, 404),
    ("/api/v1/dealer/feeds/samples/{format_}", "get"): (401, 403, 404, 422),
    ("/api/v1/dealer/feeds/{feed_id}/missing-candidates", "get"): (401, 403, 404, 422),
    ("/api/v1/dealer/feeds/{feed_id}/missing-candidates/pause", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/dealer/feeds", "post"): (401, 403, 404, 409, 422),
    ("/api/v1/dealer/feeds/{feed_id}", "patch"): (401, 403, 404, 409, 422),
    ("/api/v1/dealer/feeds/{feed_id}/rotate-token", "post"): (401, 403, 404, 409),
    ("/api/v1/dealer/feeds/{feed_id}/imports", "post"): (401, 403, 404, 409, 413, 422, 429),
    ("/api/v1/dealer/feeds/{feed_id}/api-imports", "post"): (401, 403, 409, 413, 422, 429),
    ("/api/v1/dealer/feed-imports/{run_id}", "get"): (401, 403, 404),
    ("/api/v1/dealer/feed-imports/{run_id}/rows", "get"): (401, 403, 404),
    ("/api/v1/auth/login", "post"): (401, 429),
    ("/api/v1/billing/orders", "post"): (401, 403, 404, 409, 422, 503),
    ("/api/v1/billing/orders", "get"): (401, 403, 422),
    ("/api/v1/billing/orders/{order_id}", "get"): (401, 403, 404),
    ("/api/v1/billing/callbacks/{provider_name}", "post"): (401, 404, 409, 413, 422, 503),
    ("/api/v1/admin/content", "get"): (401, 403, 422),
    ("/api/v1/admin/monitoring", "get"): (401, 403),
    ("/api/v1/admin/content/{kind}/{key}", "put"): (401, 403, 409, 422, 429),
    ("/api/v1/admin/content/{kind}/{key}/versions", "get"): (401, 403, 404, 422),
    ("/api/v1/content/{kind}/{key}", "get"): (404, 422),
    ("/api/v1/me/profile", "get"): (401, 403),
    ("/api/v1/me/profile", "patch"): (401, 403, 422),
    ("/api/v1/me/consents", "get"): (401, 403),
    ("/api/v1/me/deletion-requests", "post"): (401, 403, 409, 422, 429),
    ("/api/v1/auth/email/verification/request", "post"): (401, 403, 409, 422, 429, 503),
    ("/api/v1/auth/email/verification/confirm", "post"): (401, 409, 422, 429),
    ("/api/v1/auth/recovery/request", "post"): (422, 429),
    ("/api/v1/auth/recovery/confirm", "post"): (401, 422, 429),
    ("/api/v1/me/notification-preferences", "get"): (401, 403),
    ("/api/v1/me/notification-preferences", "put"): (401, 403, 409, 422),
    ("/api/v1/me/profile/phone-change/request", "post"): (401, 403, 409, 422, 429, 503),
    ("/api/v1/me/profile/phone-change/confirm", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/listings/{listing_id}/related", "get"): (404,),
    ("/api/v1/listings/public-capabilities", "get"): (),
    ("/api/v1/listing-validation-policy", "get"): (),
    ("/api/v1/me/listings/{listing_id}/catalog-requests", "get"): (401, 403, 404, 422),
    ("/api/v1/me/listings/{listing_id}/catalog-requests", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/moderation/catalog-requests", "get"): (401, 403, 422),
    ("/api/v1/moderation/catalog-requests/{request_id}/matches", "get"): (401, 403, 404, 422),
    ("/api/v1/moderation/catalog-requests/{request_id}/review", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/moderation/listings/{listing_id}/history", "get"): (401, 403, 404, 422),
    ("/api/v1/listings/{listing_id}/analytics", "get"): (401, 403, 404, 422),
    ("/api/v1/auth/logout", "post"): (401, 403),
    ("/api/v1/auth/otp/request", "post"): (403, 404, 429, 503),
    ("/api/v1/auth/register/otp/request", "post"): (403, 404, 429, 503),
    ("/api/v1/auth/otp/verify", "post"): (401, 403, 404, 429),
    ("/api/v1/me", "get"): (401, 403),
    ("/api/v1/me/sessions", "get"): (401, 403),
    ("/api/v1/me/sessions/revoke-others", "post"): (401, 403),
    ("/api/v1/me/sessions/{session_id}", "delete"): (401, 403, 404),
    ("/api/v1/listings", "get"): (422,),
    ("/api/v1/listings/{listing_id}", "get"): (404, 410),
    ("/api/v1/listings/{listing_id}", "patch"): (401, 403, 404, 409, 422),
    ("/api/v1/listings/{listing_id}/phone-reveal", "post"): (401, 403, 404, 429),
    ("/api/v1/listings/{listing_id}/reports", "post"): (401, 403, 404, 429),
    ("/api/v1/listings/drafts", "post"): (401, 403, 422),
    ("/api/v1/listings/{listing_id}/submit", "post"): (401, 403, 404, 409, 422),
    ("/api/v1/listings/{listing_id}/pause", "post"): (401, 403, 404, 409),
    ("/api/v1/listings/{listing_id}/resume", "post"): (401, 403, 404, 409),
    ("/api/v1/listings/{listing_id}/sold", "post"): (401, 403, 404, 409),
    ("/api/v1/me/listings", "get"): (401, 403),
    ("/api/v1/me/favorites", "get"): (401, 403),
    ("/api/v1/me/favorites/{listing_id}", "put"): (401, 403, 404),
    ("/api/v1/me/favorites/{listing_id}", "delete"): (401, 403),
    ("/api/v1/me/saved-searches", "get"): (401,),
    ("/api/v1/me/saved-searches", "post"): (401, 403, 409, 422, 429),
    ("/api/v1/me/saved-searches/{saved_search_id}", "patch"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/me/saved-searches/{saved_search_id}", "delete"): (401, 403, 404, 429),
    ("/api/v1/me/saved-searches/{saved_search_id}/pause", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/me/saved-searches/{saved_search_id}/resume", "post"): (401, 403, 404, 409, 422, 429),
    ("/api/v1/me/notifications", "get"): (401,),
    ("/api/v1/me/notifications/{notification_id}/read", "post"): (401, 403, 404),
    ("/api/v1/conversations", "get"): (401,),
    ("/api/v1/conversations", "post"): (401, 403, 404, 409, 422),
    ("/api/v1/conversations/{conversation_id}", "get"): (401, 404),
    ("/api/v1/conversations/{conversation_id}/messages", "post"): (401, 403, 404, 409, 422),
    ("/api/v1/conversations/{conversation_id}/read", "post"): (401, 403, 404, 422),
    ("/api/v1/conversations/{conversation_id}/block", "post"): (401, 403, 404, 422),
    ("/api/v1/listings/{listing_id}/photos", "post"): (
        401, 403, 404, 409, 413, 415, 422, 500
    ),
    ("/api/v1/listings/{listing_id}/photos", "get"): (401, 403, 404),
    ("/api/v1/listings/{listing_id}/photos/{photo_id}", "delete"): (
        401, 403, 404, 409
    ),
    ("/api/v1/listings/{listing_id}/photos/reorder", "post"): (
        401, 403, 404, 409, 422
    ),
    ("/api/v1/listings/{listing_id}/photos/{photo_id}/cover", "post"): (
        401, 403, 404, 409
    ),
    ("/api/v1/photos/{photo_id}/{size}", "get"): (404,),
    ("/api/v1/me/company", "get"): (401, 403),
    ("/api/v1/companies", "post"): (401, 403, 409),
    ("/api/v1/companies/{company_id}", "patch"): (401, 403, 404, 409),
    ("/api/v1/dealers/{slug}", "get"): (404,),
    ("/api/v1/moderation/listings", "get"): (401, 403),
    ("/api/v1/moderation/listings/{listing_id}/approve", "post"): (
        401, 403, 404, 409
    ),
    ("/api/v1/moderation/listings/{listing_id}/reject", "post"): (
        401, 403, 404, 409, 422
    ),
    ("/api/v1/moderation/listings/{listing_id}/block", "post"): (
        401, 403, 404, 409, 422
    ),
    ("/api/v1/moderation/companies", "get"): (401, 403),
    ("/api/v1/moderation/companies/{company_id}/approve", "post"): (
        401, 403, 404, 409
    ),
    ("/api/v1/moderation/companies/{company_id}/reject", "post"): (
        401, 403, 404, 409, 422
    ),
    ("/api/v1/moderation/companies/{company_id}/block", "post"): (
        401, 403, 404, 409, 422
    ),
    ("/api/v1/moderation/reports", "get"): (401, 403),
    ("/api/v1/moderation/reports/{report_id}/resolve", "post"): (401, 403, 404, 409),
}
API_ERROR_DESCRIPTIONS = {
    401: "Authentication required or credentials are invalid",
    403: "The authenticated user is not allowed to perform this action",
    404: "The requested resource is not available",
    409: "The request conflicts with the current resource state",
    410: "The listing was previously published and has been archived",
    413: "The request or uploaded photo exceeds the allowed size",
    415: "The uploaded photo format is not supported",
    422: "Request validation error",
    429: "The request rate limit was exceeded",
    500: "Photo storage is unavailable",
    503: "An external service required for this action is unavailable",
}


def document_api_error_response(
    responses: dict[str, Any],
    status: int,
    description: str,
    *,
    replace_description: bool = False,
) -> None:
    response = responses.setdefault(str(status), {"description": description})
    if replace_description or not response.get("description"):
        response["description"] = description
    json_content = response.setdefault("content", {}).setdefault("application/json", {})
    json_content["schema"] = {"$ref": "#/components/schemas/ApiErrorOut"}

for route_module in (auth, catalog, listings, media, companies, moderation, saved_searches, notifications, conversations, admin, admin_tariffs, admin_catalog, admin_settings, dealer, feeds, account, billing, managed_content, monitoring, profile_identity, catalog_requests, customs_calculator, vin_checks):
    app.include_router(route_module.router)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema is not None:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        summary=app.summary,
        description=app.description,
        terms_of_service=app.terms_of_service,
        contact=app.contact,
        license_info=app.license_info,
        routes=app.routes,
        webhooks=app.webhooks.routes,
        tags=app.openapi_tags,
        servers=app.servers,
        separate_input_output_schemas=app.separate_input_output_schemas,
    )
    schema.setdefault("components", {}).setdefault("schemas", {})["ApiErrorOut"] = (
        ApiErrorOut.model_json_schema()
    )
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if path == "/api/v1" or path.startswith("/api/v1/"):
                operation.setdefault("responses", {})["default"] = {
                    "description": "API error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ApiErrorOut"}
                        }
                    },
                }
                responses = operation["responses"]
                for status in ROUTE_ERROR_STATUSES.get((path, method), ()):
                    document_api_error_response(
                        responses, status, API_ERROR_DESCRIPTIONS[status]
                    )
            if (path, method) in IDEMPOTENCY_REQUIRED_OPERATIONS:
                for parameter in operation.get("parameters", []):
                    if parameter.get("in") == "header" and parameter.get("name") == "Idempotency-Key":
                        parameter["required"] = True
                        header_schema = parameter.get("schema", {})
                        string_schema = next(
                            (
                                option
                                for option in header_schema.get("anyOf", [])
                                if option.get("type") == "string"
                            ),
                            {},
                        )
                        parameter["schema"] = {
                            **{
                                key: value
                                for key, value in header_schema.items()
                                if key not in {"anyOf", "nullable"}
                            },
                            **string_schema,
                            "type": "string",
                        }
            if (path, method) in CSRF_REQUIRED_OPERATIONS:
                for parameter in operation.get("parameters", []):
                    if parameter.get("in") == "header" and parameter.get("name") == "X-CSRF-Token":
                        parameter["required"] = True
                        header_schema = parameter.get("schema", {})
                        string_schema = next(
                            (
                                option
                                for option in header_schema.get("anyOf", [])
                                if option.get("type") == "string"
                            ),
                            {},
                        )
                        parameter["schema"] = {
                            **{
                                key: value
                                for key, value in header_schema.items()
                                if key not in {"anyOf", "nullable"}
                            },
                            **string_schema,
                            "type": "string",
                        }
            response = operation.get("responses", {}).get("422")
            if response is not None:
                document_api_error_response(
                    operation["responses"],
                    422,
                    "Request validation error",
                    replace_description=True,
                )

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


class RequestBodyLimitExceeded(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=413,
            detail={
                "code": "request_body_too_large",
                "message": "Photo upload request exceeds the allowed size",
                "field_errors": {},
            },
        )


class UploadBodyLimitMiddleware:
    def __init__(self, app, *, max_body_bytes: int | None = None) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        is_feed_upload = self._is_feed_upload(scope)
        if not self._is_photo_upload(scope) and not is_feed_upload:
            await self.app(scope, receive, send)
            return

        max_body_bytes = self.max_body_bytes
        if max_body_bytes is None:
            if is_feed_upload:
                overhead = MULTIPART_OVERHEAD_LIMIT if scope.get("path", "").endswith("/imports") else 0
                max_body_bytes = FEED_REQUEST_LIMIT + overhead
            else:
                max_body_bytes = get_settings().upload_max_bytes + MULTIPART_OVERHEAD_LIMIT

        content_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_body_bytes:
                    raise RequestBodyLimitExceeded()
            return message

        response_started = False

        async def tracked_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyLimitExceeded:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    @staticmethod
    def _is_photo_upload(scope) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        parts = scope.get("path", "").split("/")
        return len(parts) == 6 and parts[1:4] == ["api", "v1", "listings"] and parts[5] == "photos"

    @staticmethod
    def _is_feed_upload(scope) -> bool:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return False
        parts = scope.get("path", "").split("/")
        return len(parts) == 7 and parts[1:5] == ["api", "v1", "dealer", "feeds"] and parts[6] in {"imports", "api-imports"}

    @staticmethod
    async def _reject(scope, receive, send) -> None:
        request_id = (scope.get("state") or {}).get("request_id") or uuid4().hex
        is_feed = UploadBodyLimitMiddleware._is_feed_upload(scope)
        response = JSONResponse(
            status_code=413,
            content={
                "code": "feed_body_too_large" if is_feed else "request_body_too_large",
                "message": "Dealer feed request exceeds the allowed size" if is_feed else "Photo upload request exceeds the allowed size",
                "field_errors": {},
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
        await response(scope, receive, send)


app.add_middleware(UploadBodyLimitMiddleware)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    token = bind_request_id(request_id)
    started_at = perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log_event(
            logger,
            logging.INFO,
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return response
    finally:
        reset_request_id(token)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    field_errors = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part not in {"body", "query", "path", "header"})
        field_errors[location or "request"] = str(error.get("msg", "Invalid value"))
    return JSONResponse(status_code=422, content={
        "code": "validation_error", "message": "Request validation failed", "field_errors": field_errors,
        "request_id": getattr(request.state, "request_id", ""),
    }, headers={"X-Request-ID": getattr(request.state, "request_id", "")})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    from app.error_monitoring import capture_safe_error
    capture_safe_error("api", type(exc).__name__, request_id=request_id)
    log_event(
        logger,
        logging.ERROR,
        "request_failed",
        method=request.method,
        path=request.url.path,
        error_type=type(exc).__name__,
        request_id=request_id,
    )
    return JSONResponse(status_code=500, content={
        "code": "internal_error", "message": "An unexpected error occurred", "field_errors": {},
        "request_id": request_id,
    }, headers={"X-Request-ID": request_id})


@app.exception_handler(StarletteHTTPException)
async def starlette_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    if isinstance(exc.detail, dict):
        body = {
            "code": exc.detail.get("code", "request_failed"),
            "message": exc.detail.get("message", "Request failed"),
            "field_errors": exc.detail.get("field_errors", {}),
        }
    else:
        body = {"code": "request_failed", "message": str(exc.detail), "field_errors": {}}
    body["request_id"] = request_id
    headers = dict(exc.headers or {})
    headers["X-Request-ID"] = request_id
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        body = {
            "code": exc.detail.get("code", "request_failed"),
            "message": exc.detail.get("message", "Request failed"),
            "field_errors": exc.detail.get("field_errors", {}),
        }
    else:
        body = {"code": "request_failed", "message": str(exc.detail), "field_errors": {}}
    body["request_id"] = getattr(request.state, "request_id", "")
    headers = dict(exc.headers or {})
    headers["X-Request-ID"] = body["request_id"]
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


@app.get("/health/live", response_model=HealthResponse)
def live() -> dict:
    return {"status": "ok"}


@app.get(
    "/health/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
def ready() -> JSONResponse:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(status_code=200, content={"status": "ok"})
