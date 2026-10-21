"""Managed articles stay draft-only until an administrator publishes them."""

from app.managed_content import validate_content
from test_managed_content import admin, content_body


def article_payload(**changes):
    payload = {
        "slug": "inspection-before-buying",
        "title": "Как осмотреть транспорт перед покупкой",
        "summary": "Краткий порядок проверки документов, состояния и истории транспортного средства.",
        "topic": "inspection",
        "body": "Проверьте документы и сопоставьте идентификаторы. Осмотрите кузов, агрегаты и салон. "
                "Зафиксируйте обнаруженные недостатки до оформления сделки.",
        "published_at": "2026-10-04",
        "sources": [{"title": "Официальный источник", "url": "https://example.gov.by/checklist"}],
    }
    payload.update(changes)
    return payload


def test_article_payload_validates_slug_topic_safe_text_and_https_sources():
    validated = validate_content("article", "inspection-before-buying", article_payload(), "draft")

    assert validated["slug"] == "inspection-before-buying"
    assert validated["topic"] == "inspection"
    assert validated["published_at"] == "2026-10-04"
    assert validated["sources"] == [{"title": "Официальный источник", "url": "https://example.gov.by/checklist"}]


def test_article_payload_rejects_mismatched_slug_unknown_topic_html_and_http_source():
    invalid_payloads = [
        article_payload(slug="different-slug"),
        article_payload(topic="unreviewed-topic"),
        article_payload(body="Текст статьи <script>alert(1)</script>"),
        article_payload(sources=[{"title": "Сомнительная ссылка", "url": "http://example.com"}]),
    ]

    for payload in invalid_payloads:
        try:
            validate_content("article", "inspection-before-buying", payload, "draft")
        except ValueError:
            continue
        raise AssertionError(f"Unsafe article payload was accepted: {payload!r}")


def test_published_article_requires_publication_date():
    try:
        validate_content("article", "inspection-before-buying", article_payload(published_at=None), "published")
    except ValueError:
        return
    raise AssertionError("Published article without a publication date was accepted")


def test_draft_article_is_not_returned_by_public_list_or_detail(integration):
    client, headers = admin(integration)
    endpoint = "/api/v1/admin/content/article/inspection-before-buying"
    saved = client.put(endpoint, json=content_body(article_payload(), status="draft"), headers=headers)
    assert saved.status_code == 200, saved.text
    assert client.get("/api/v1/content/article/inspection-before-buying").status_code == 404

    listing = client.get("/api/v1/content/articles")
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"] == []
    assert listing.json()["total"] == 0


def test_publishing_article_exposes_safe_detail_and_topic_filtered_summary_with_history(integration):
    client, headers = admin(integration)
    endpoint = "/api/v1/admin/content/article/inspection-before-buying"
    draft = client.put(endpoint, json=content_body(article_payload(), status="draft"), headers=headers)
    assert draft.status_code == 200, draft.text

    published = client.put(endpoint, json=content_body(article_payload(), expected_revision=1), headers=headers)
    assert published.status_code == 200, published.text
    assert published.json()["content"]["revision"] == 2

    public = client.get("/api/v1/content/article/inspection-before-buying")
    assert public.status_code == 200, public.text
    assert public.json()["content"]["payload"]["title"] == article_payload()["title"]
    assert public.json()["content"]["payload"]["sources"] == article_payload()["sources"]
    assert public.json()["indexable"] is False

    listing = client.get("/api/v1/content/articles", params={"topic": "inspection"})
    assert listing.status_code == 200, listing.text
    assert listing.json()["total"] == 1
    assert listing.json()["items"] == [{
        "slug": "inspection-before-buying",
        "title": article_payload()["title"],
        "summary": article_payload()["summary"],
        "topic": "inspection",
        "published_at": "2026-10-04",
        "updated_at": published.json()["content"]["updated_at"],
    }]
    assert client.get("/api/v1/content/articles", params={"topic": "vin"}).json()["items"] == []

    history = client.get(endpoint + "/versions")
    assert history.status_code == 200
    assert [item["status"] for item in history.json()["items"]] == ["published", "draft"]

    unpublished = client.put(endpoint, json=content_body(article_payload(), status="draft", expected_revision=2), headers=headers)
    assert unpublished.status_code == 200, unpublished.text
    assert client.get("/api/v1/content/article/inspection-before-buying").status_code == 404
    assert client.get("/api/v1/content/articles").json()["items"] == []


def test_public_list_orders_by_publication_date_desc_hides_drafts_and_private_fields(integration):
    client, headers = admin(integration)
    specs = [("older-article", "2026-09-01", "published"), ("newer-article", "2026-10-10", "published"),
             ("hidden-draft", "2026-10-20", "draft")]
    for slug, day, status in specs:
        saved = client.put(f"/api/v1/admin/content/article/{slug}",
                           json=content_body(article_payload(slug=slug, published_at=day), status=status), headers=headers)
        assert saved.status_code == 200, saved.text

    listing = client.get("/api/v1/content/articles")
    assert listing.status_code == 200, listing.text
    assert [item["slug"] for item in listing.json()["items"]] == ["newer-article", "older-article"]
    assert set(listing.json()["items"][0]) == {"slug", "title", "summary", "topic", "published_at", "updated_at"}
    assert client.get("/api/v1/content/article/hidden-draft").status_code == 404

    second_page = client.get("/api/v1/content/articles", params={"page": 2, "page_size": 1})
    assert [item["slug"] for item in second_page.json()["items"]] == ["older-article"]
    assert second_page.json()["total"] == 2

    detail = client.get("/api/v1/content/article/newer-article").json()["content"]
    assert "updated_by" not in detail


def test_article_key_rejects_uppercase_characters():
    try:
        validate_content("article", "Inspection-Before-Buying", article_payload(slug="Inspection-Before-Buying"), "draft")
    except ValueError:
        return
    raise AssertionError("Uppercase article key was accepted")


def test_public_article_list_is_ordered_filtered_and_paginated_in_sql(integration):
    client, headers = admin(integration)
    specs = [("alpha-one", "2026-10-01", "vin"), ("bravo-two", "2026-10-05", "inspection"), ("charlie-three", "2026-10-03", "vin"),
             ("delta-four", "2026-10-04", "vin"), ("echo-five", "2026-10-02", "inspection")]
    for slug, published_at, topic in specs:
        payload = article_payload(slug=slug, published_at=published_at, topic=topic)
        saved = client.put(f"/api/v1/admin/content/article/{slug}", json=content_body(payload), headers=headers)
        assert saved.status_code == 200, saved.text

    def slugs(**params):
        response = client.get("/api/v1/content/articles", params=params)
        assert response.status_code == 200, response.text
        return [item["slug"] for item in response.json()["items"]], response.json()

    first, body = slugs(page=1, page_size=2)
    assert first == ["bravo-two", "delta-four"] and body["total"] == 5 and body["page_size"] == 2
    assert slugs(page=2, page_size=2)[0] == ["charlie-three", "echo-five"]
    assert slugs(page=3, page_size=2)[0] == ["alpha-one"]
    assert slugs(page=4, page_size=2)[0] == []
    vin, body = slugs(topic="vin", page=1, page_size=2)
    assert vin == ["delta-four", "charlie-three"] and body["total"] == 3
    assert slugs(topic="vin", page=2, page_size=2)[0] == ["alpha-one"]
