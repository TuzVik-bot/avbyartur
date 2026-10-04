from types import SimpleNamespace
from uuid import UUID

import pytest
from app.api.companies import _company_out
from app.main import app
from app.schemas import CompanyInput
from pydantic import ValidationError


def _response_schema(schema: dict, path: str, method: str) -> dict:
    response = schema["paths"][path][method]["responses"]["200"]
    return response["content"]["application/json"]["schema"]


def _component(schema: dict, ref: str) -> dict:
    prefix = "#/components/schemas/"
    assert ref.startswith(prefix)
    return schema["components"]["schemas"][ref.removeprefix(prefix)]


def test_company_routes_document_typed_responses() -> None:
    schema = app.openapi()

    assert _response_schema(schema, "/api/v1/me/company", "get") == {
        "$ref": "#/components/schemas/MyCompanyResponse"
    }
    assert _response_schema(schema, "/api/v1/companies", "post") == {
        "$ref": "#/components/schemas/CompanyMutationResponse"
    }
    assert _response_schema(schema, "/api/v1/companies/{company_id}", "patch") == {
        "$ref": "#/components/schemas/CompanyMutationResponse"
    }
    assert _response_schema(schema, "/api/v1/dealers", "get") == {
        "$ref": "#/components/schemas/DealerDirectoryResponse"
    }
    assert _response_schema(schema, "/api/v1/dealers/{slug}", "get") == {
        "$ref": "#/components/schemas/DealerDetailResponse"
    }


def test_company_openapi_shapes_keep_private_and_public_fields_separate() -> None:
    schema = app.openapi()
    components = schema["components"]["schemas"]

    my_company = components["MyCompanyResponse"]["properties"]["company"]
    assert my_company["anyOf"][0] == {"$ref": "#/components/schemas/PrivateCompanyOut"}
    assert {"type": "null"} in my_company["anyOf"]
    assert set(components["PrivateCompanyOut"]["properties"]) == {
        "id", "name", "slug", "status", "revision", "address", "business_hours",
        "moderation_reason", "unp", "phone",
    }
    assert set(components["PublicCompanyOut"]["properties"]) == {
        "id", "name", "slug", "status", "revision", "address", "business_hours",
    }

    directory = components["DealerDirectoryResponse"]["properties"]
    assert directory["items"]["items"] == {"$ref": "#/components/schemas/PublicCompanyOut"}
    assert directory["pagination"] == {"$ref": "#/components/schemas/CompanyPaginationOut"}

    detail = components["DealerDetailResponse"]["properties"]
    assert detail["company"] == {"$ref": "#/components/schemas/PublicCompanyOut"}
    assert detail["listings"] == {"$ref": "#/components/schemas/DealerListingsPageOut"}
    listings = components["DealerListingsPageOut"]["properties"]
    assert listings["pagination"] == {"$ref": "#/components/schemas/CompanyPaginationOut"}
    summary_ref = listings["items"]["items"]["$ref"]
    summary = _component(schema, summary_ref)
    assert "contact_phone" not in summary["properties"]
    assert "vin" not in summary["properties"]
    assert "moderation_reason" not in summary["properties"]
    assert summary["properties"]["seller"] == {
        "$ref": "#/components/schemas/DealerListingSellerOut"
    }
    assert components["DealerListingSellerOut"]["properties"]["type"]["const"] == "company"


def test_company_moderation_reason_is_private_to_the_owner() -> None:
    company = SimpleNamespace(
        id=UUID("edbb213f-f508-4b2b-a12d-c235137143cb"),
        name="Private Motors",
        slug="private-motors",
        status="approved",
        address="Minsk",
        moderation_reason="Internal review note",
        unp="123456789",
        phone="+375291234567",
        business_hours={"mon": {"open": "09:00", "close": "18:00"}},
    )

    public = _company_out(company, private=False)
    private = _company_out(company, private=True)

    assert "moderation_reason" not in public
    assert "unp" not in public
    assert "phone" not in public
    assert private["moderation_reason"] == "Internal review note"
    assert public["business_hours"] == {"mon": {"open": "09:00", "close": "18:00"}}
    assert private["business_hours"] == public["business_hours"]


def test_company_business_hours_require_all_days_and_valid_24_hour_pairs() -> None:
    hours = {
        "mon": {"open": "09:00", "close": "18:00"},
        "tue": {"open": "09:30", "close": "18:30"},
        "wed": {"closed": True},
        "thu": {"open": "10:00", "close": "19:00"},
        "fri": {"open": "09:00", "close": "17:00"},
        "sat": {"closed": True},
        "sun": {"closed": True},
    }
    payload = CompanyInput.model_validate({
        "name": "Pilot Motors",
        "unp": "123456789",
        "address": "Minsk",
        "phone": "+375291234567",
        "business_hours": hours,
    })

    assert payload.business_hours.model_dump(mode="json") == hours

    for invalid in (
        {**hours, "sun": {"open": "24:00", "close": "25:00"}},
        {key: value for key, value in hours.items() if key != "sun"},
        {**hours, "sun": {"closed": False}},
        {**hours, "sun": {"open": "18:00", "close": "09:00"}},
        {**hours, "extra": {"closed": True}},
    ):
        with pytest.raises(ValidationError):
            CompanyInput.model_validate({
                "name": "Pilot Motors",
                "unp": "123456789",
                "address": "Minsk",
                "phone": "+375291234567",
                "business_hours": invalid,
            })


def test_auth_user_response_exposes_company_role_context() -> None:
    user = app.openapi()["components"]["schemas"]["UserOut"]["properties"]

    assert {"company_id", "company_role"}.issubset(user)
