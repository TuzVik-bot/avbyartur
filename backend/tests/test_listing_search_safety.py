import pytest

from app.services import contains_pattern
from tests.test_listing_currency import add_listing, add_owner


def test_contains_pattern_escapes_like_wildcards_and_truncates():
    assert contains_pattern("  50%_off\\x  ", 100) == "%50\\%\\_off\\\\x%"
    assert contains_pattern("a" * 150, 100) == f"%{'a' * 100}%"


def test_text_search_treats_wildcards_literally(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        owner = add_owner(db)
        plain = add_listing(db, owner, "18000", "BYN")
        plain.title = "Audi A4"
        literal = add_listing(db, owner, "17000", "BYN")
        literal.title = "Скидка 100% на_всё"
        plain_id, literal_id = str(plain.id), str(literal.id)
        db.commit()

    client = integration["client"]

    def ids(term: str) -> set[str]:
        response = client.get("/api/v1/listings", params={"q": term})
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["items"]}

    assert ids("%") == {literal_id}
    assert ids("_") == {literal_id}
    assert ids("A_di") == set()
    assert ids("audi") == {plain_id}


@pytest.mark.parametrize(
    "path",
    ["/api/v1/listings", "/api/v1/listings/count", "/api/v1/dealers"],
)
def test_public_page_number_has_upper_bound(integration, path):
    client = integration["client"]

    assert client.get(path, params={"page": 1000}).status_code == 200
    rejected = client.get(path, params={"page": 1001})
    assert rejected.status_code == 422, rejected.text
