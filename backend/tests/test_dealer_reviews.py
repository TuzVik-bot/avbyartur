import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent, Company, DealerReview, DealerReviewReport, DealerTeamMember, User
from app.security import hash_password

PASSWORD = "dealer-review-test-password-123"


def _add_user(factory, role: str = "user") -> User:
    email = f"review-{role}-{uuid.uuid4().hex[:12]}@example.com"
    user = User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password(PASSWORD),
        role=role,
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _add_company(factory, owner: User, status: str = "approved") -> Company:
    company = Company(
        owner_id=owner.id,
        name=f"Review Motors {uuid.uuid4().hex[:6]}",
        slug=f"review-{uuid.uuid4().hex[:10]}",
        unp=str(100000000 + uuid.uuid4().int % 899999999),
        address="Минск",
        phone="+375291234567",
        status=status,
    )
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        db.expunge(company)
    return company


def _client(integration, user: User) -> tuple[TestClient, dict]:
    client = TestClient(integration["client"].app)
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, {"X-CSRF-Token": response.json()["csrf_token"]}


def _create_review(client, headers, slug, rating=4, text="Всё прошло хорошо"):
    return client.post(f"/api/v1/dealers/{slug}/reviews", json={"rating": rating, "text": text}, headers=headers)


@pytest.mark.parametrize("status", ["pending", "rejected", "hidden"])
def test_unpublished_review_is_not_public(integration, status):
    factory = integration["SessionLocal"]
    owner, author = _add_user(factory), _add_user(factory)
    company = _add_company(factory, owner)
    with factory() as db:
        db.add(DealerReview(company_id=company.id, author_id=author.id, rating=5, text="Отзыв", status=status))
        db.commit()
    public = integration["client"].get(f"/api/v1/dealers/{company.slug}")
    assert public.status_code == 200, public.text
    assert public.json()["reviews"] == {"items": [], "count": 0, "average_rating": None}


def test_review_lifecycle_publish_report_and_resolve(integration):
    factory = integration["SessionLocal"]
    owner, author, reporter = _add_user(factory), _add_user(factory), _add_user(factory)
    moderator = _add_user(factory, "moderator")
    company = _add_company(factory, owner)
    client, headers = _client(integration, author)

    created = _create_review(client, headers, company.slug)
    assert created.status_code == 201, created.text
    review = created.json()["review"]
    assert review["status"] == "pending" and review["revision"] == 1 and review["moderation_reason"] is None
    assert _create_review(client, headers, company.slug).status_code == 409

    mine = client.get(f"/api/v1/dealers/{company.slug}/reviews/mine")
    assert mine.status_code == 200 and mine.json()["review"]["id"] == review["id"]

    edited = client.patch(
        f"/api/v1/dealer-reviews/{review['id']}",
        json={"expected_revision": 1, "rating": 5, "text": "Исправленный отзыв"},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["review"]["revision"] == 2
    stale = client.patch(
        f"/api/v1/dealer-reviews/{review['id']}",
        json={"expected_revision": 1, "rating": 3, "text": "Старая ревизия"},
        headers=headers,
    )
    assert stale.status_code == 409

    mod_client, mod_headers = _client(integration, moderator)
    queue = mod_client.get("/api/v1/moderation/dealer-reviews?status=pending")
    assert queue.status_code == 200, queue.text
    item = next(row for row in queue.json()["items"] if row["id"] == review["id"])
    assert item["company_id"] == str(company.id) and item["author_id"] == str(author.id)
    published = mod_client.post(
        f"/api/v1/moderation/dealer-reviews/{review['id']}/review",
        json={"expected_revision": item["revision"], "status": "published", "reason": "Проверен"},
        headers=mod_headers,
    )
    assert published.status_code == 200, published.text
    assert published.json()["review"]["status"] == "published"

    public = integration["client"].get(f"/api/v1/dealers/{company.slug}").json()["reviews"]
    assert public["count"] == 1 and public["average_rating"] == 5
    assert public["items"][0]["text"] == "Исправленный отзыв"
    assert set(public["items"][0]) == {"id", "rating", "text", "created_at"}

    rep_client, rep_headers = _client(integration, reporter)
    report = rep_client.post(
        f"/api/v1/dealer-reviews/{review['id']}/reports", json={"reason": "Проверить"}, headers=rep_headers
    )
    assert report.status_code == 201, report.text
    assert report.json()["status"] == "open"
    duplicate = rep_client.post(
        f"/api/v1/dealer-reviews/{review['id']}/reports", json={"reason": "Ещё раз"}, headers=rep_headers
    )
    assert duplicate.status_code == 409

    reports = mod_client.get("/api/v1/moderation/dealer-review-reports?status=open")
    assert reports.status_code == 200, reports.text
    report_item = next(row for row in reports.json()["items"] if row["id"] == report.json()["id"])
    assert report_item["company_name"] == company.name and "reporter_id" not in report_item
    resolved = mod_client.post(
        f"/api/v1/moderation/dealer-review-reports/{report.json()['id']}/resolve",
        json={"resolution": "Жалоба рассмотрена"},
        headers=mod_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["report"] == {
        "id": report.json()["id"],
        "status": "resolved",
        "resolution": "Жалоба рассмотрена",
    }
    again = mod_client.post(
        f"/api/v1/moderation/dealer-review-reports/{report.json()['id']}/resolve",
        json={"resolution": "Повтор"},
        headers=mod_headers,
    )
    assert again.status_code == 409

    with factory() as db:
        actions = {
            event.action for event in db.scalars(select(AuditEvent).where(AuditEvent.entity_type == "dealer_review"))
        }
        assert {"created", "updated", "published", "reported"} <= actions
        assert (
            db.scalar(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "dealer_review_report",
                    AuditEvent.action == "resolved",
                )
            ).actor_id
            == moderator.id
        )


def test_author_edit_returns_published_review_to_moderation(integration):
    factory = integration["SessionLocal"]
    owner, author = _add_user(factory), _add_user(factory)
    company = _add_company(factory, owner)
    with factory() as db:
        review = DealerReview(
            company_id=company.id, author_id=author.id, rating=5, text="Опубликован", status="published"
        )
        db.add(review)
        db.commit()
        review_id = review.id
    client, headers = _client(integration, author)
    edited = client.patch(
        f"/api/v1/dealer-reviews/{review_id}",
        json={"expected_revision": 1, "rating": 1, "text": "Изменённый"},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["review"]["status"] == "pending"
    assert integration["client"].get(f"/api/v1/dealers/{company.slug}").json()["reviews"]["count"] == 0


def test_company_owner_and_team_member_cannot_review_own_company(integration):
    factory = integration["SessionLocal"]
    owner, member = _add_user(factory), _add_user(factory)
    company = _add_company(factory, owner)
    with factory() as db:
        db.add(DealerTeamMember(company_id=company.id, user_id=member.id, role="seller", status="active", granted_by=owner.id))
        db.commit()
    for user in (owner, member):
        client, headers = _client(integration, user)
        response = _create_review(client, headers, company.slug)
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "dealer_self_review"


def test_review_requires_auth_csrf_and_approved_company(integration):
    factory = integration["SessionLocal"]
    owner, author = _add_user(factory), _add_user(factory)
    company = _add_company(factory, owner)
    pending = _add_company(factory, _add_user(factory), status="pending")
    anonymous = TestClient(integration["client"].app)
    assert (
        anonymous.post(f"/api/v1/dealers/{company.slug}/reviews", json={"rating": 5, "text": "Аноним"}).status_code
        == 401
    )
    assert anonymous.get(f"/api/v1/dealers/{company.slug}/reviews/mine").status_code == 401
    client, headers = _client(integration, author)
    assert (
        client.post(f"/api/v1/dealers/{company.slug}/reviews", json={"rating": 5, "text": "Без CSRF"}).status_code
        == 403
    )
    assert _create_review(client, headers, pending.slug).status_code == 404
    assert client.get(f"/api/v1/dealers/{pending.slug}/reviews/mine").status_code == 404
    for invalid in ({"rating": 0, "text": "x"}, {"rating": 6, "text": "x"}, {"rating": 5, "text": "   "}):
        assert client.post(f"/api/v1/dealers/{company.slug}/reviews", json=invalid, headers=headers).status_code == 422
    assert client.get(f"/api/v1/dealers/{company.slug}/reviews/mine").json() == {"review": None}


def test_review_idor_other_users_cannot_edit_see_or_moderate(integration):
    factory = integration["SessionLocal"]
    owner, author, stranger = _add_user(factory), _add_user(factory), _add_user(factory)
    company = _add_company(factory, owner)
    author_client, author_headers = _client(integration, author)
    review_id = _create_review(author_client, author_headers, company.slug).json()["review"]["id"]

    stranger_client, stranger_headers = _client(integration, stranger)
    edit = stranger_client.patch(
        f"/api/v1/dealer-reviews/{review_id}",
        json={"expected_revision": 1, "rating": 1, "text": "Чужая правка"},
        headers=stranger_headers,
    )
    assert edit.status_code == 404
    assert stranger_client.get(f"/api/v1/dealers/{company.slug}/reviews/mine").json() == {"review": None}
    # A pending review cannot be reported: it is not public yet.
    assert (
        stranger_client.post(
            f"/api/v1/dealer-reviews/{review_id}/reports",
            json={"reason": "Жалоба"},
            headers=stranger_headers,
        ).status_code
        == 404
    )
    assert stranger_client.get("/api/v1/moderation/dealer-reviews").status_code == 403
    assert stranger_client.get("/api/v1/moderation/dealer-review-reports").status_code == 403
    assert (
        stranger_client.post(
            f"/api/v1/moderation/dealer-reviews/{review_id}/review",
            json={"expected_revision": 1, "status": "published", "reason": "Сам себе"},
            headers=stranger_headers,
        ).status_code
        == 403
    )
    # The company owner is not a moderator either.
    owner_client, owner_headers = _client(integration, owner)
    assert (
        owner_client.post(
            f"/api/v1/moderation/dealer-reviews/{review_id}/review",
            json={"expected_revision": 1, "status": "rejected", "reason": "Не нравится"},
            headers=owner_headers,
        ).status_code
        == 403
    )
    with factory() as db:
        stored = db.get(DealerReview, uuid.UUID(review_id))
        assert stored.status == "pending" and stored.text == "Всё прошло хорошо"


def test_author_cannot_report_own_review_and_moderation_requires_csrf(integration):
    factory = integration["SessionLocal"]
    owner, author = _add_user(factory), _add_user(factory)
    moderator = _add_user(factory, "moderator")
    company = _add_company(factory, owner)
    with factory() as db:
        review = DealerReview(
            company_id=company.id, author_id=author.id, rating=4, text="Опубликован", status="published"
        )
        db.add(review)
        db.commit()
        review_id = review.id
    client, headers = _client(integration, author)
    own = client.post(f"/api/v1/dealer-reviews/{review_id}/reports", json={"reason": "Свой"}, headers=headers)
    assert own.status_code == 403
    mod_client, _headers = _client(integration, moderator)
    assert (
        mod_client.post(
            f"/api/v1/moderation/dealer-reviews/{review_id}/review",
            json={"expected_revision": 1, "status": "hidden", "reason": "Без CSRF"},
        ).status_code
        == 403
    )
    with factory() as db:
        assert db.scalar(select(DealerReviewReport).where(DealerReviewReport.review_id == review_id)) is None
