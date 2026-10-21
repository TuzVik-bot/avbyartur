import uuid
from io import BytesIO

import pytest
from PIL import Image

from app.models import AuditEvent, Company, DealerReview, DealerReviewReport, Listing, User
from app.security import hash_password

PASSWORD = "task8-dealer-review-test-password-123"


def add_user(factory, role="user"):
    email = f"{role}-{uuid.uuid4().hex[:12]}@example.com"
    user = User(email=email, display_name=email.split("@", 1)[0], password_hash=hash_password(PASSWORD), role=role, status="active")
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_public_stats_only_count_active_public_listings_approved_companies_and_published_reviews(integration):
    factory = integration["SessionLocal"]
    approved_owner, pending_owner, private_owner = add_user(factory), add_user(factory), add_user(factory)
    review_authors = [add_user(factory) for _ in range(5)]
    approved = Company(owner_id=approved_owner.id, name="Approved", slug=f"approved-{uuid.uuid4().hex[:8]}", unp=str(100000000 + uuid.uuid4().int % 899999999), address="", phone="", status="approved")
    pending = Company(owner_id=pending_owner.id, name="Pending", slug=f"pending-{uuid.uuid4().hex[:8]}", unp=str(100000000 + uuid.uuid4().int % 899999999), address="", phone="", status="pending")
    with factory() as db:
        db.add_all([approved, pending])
        db.flush()
        db.add_all([
            Listing(owner_id=approved_owner.id, company_id=approved.id, slug=f"approved-listing-{uuid.uuid4().hex[:8]}", status="active"),
            Listing(owner_id=pending_owner.id, company_id=pending.id, slug=f"pending-listing-{uuid.uuid4().hex[:8]}", status="active"),
            Listing(owner_id=private_owner.id, company_id=None, slug=f"private-listing-{uuid.uuid4().hex[:8]}", status="active"),
            Listing(owner_id=private_owner.id, company_id=None, slug=f"archived-listing-{uuid.uuid4().hex[:8]}", status="archived"),
        ])
        db.add_all([
            DealerReview(
                company_id=approved.id, author_id=review_authors[0].id,
                rating=5, text="published review", status="published",
            ),
            DealerReview(
                company_id=approved.id, author_id=review_authors[1].id,
                rating=4, text="pending review", status="pending",
            ),
            DealerReview(
                company_id=approved.id, author_id=review_authors[2].id,
                rating=2, text="rejected review", status="rejected",
            ),
            DealerReview(
                company_id=approved.id, author_id=review_authors[3].id,
                rating=1, text="hidden review", status="hidden",
            ),
            DealerReview(
                company_id=pending.id, author_id=review_authors[4].id,
                rating=5, text="published review on unapproved company", status="published",
            ),
        ])
        db.commit()
        pending_id = pending.id
    client = integration["client"]
    assert client.get("/api/v1/public-stats").json() == {
        "active_listings": 2,
        "approved_companies": 1,
        "published_reviews": 1,
    }
    with factory() as db:
        db.get(Company, pending_id).status = "approved"
        db.commit()
    assert client.get("/api/v1/public-stats").json() == {
        "active_listings": 3,
        "approved_companies": 2,
        "published_reviews": 2,
    }


def test_company_logo_upload_sanitizes_image_and_uses_company_revision(integration):
    factory = integration["SessionLocal"]
    owner = add_user(factory)
    company = Company(owner_id=owner.id, name="Logo Motors", slug=f"logo-{uuid.uuid4().hex[:8]}", unp=str(100000000 + uuid.uuid4().int % 899999999), address="", phone="", status="approved")
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        company_id, slug = str(company.id), company.slug
    client = integration["client"]
    headers = login(client, owner.email)
    image_data = BytesIO()
    Image.new("RGB", (8, 8), color=(20, 50, 90)).save(image_data, format="PNG")
    response = client.put(
        f"/api/v1/companies/{company_id}/logo",
        data={"expected_revision": "1"},
        files={"file": ("brand.png", image_data.getvalue(), "image/png")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    logo_url = response.json()["logo_url"]
    assert response.json()["revision"] == 2
    public = client.get(f"/api/v1/dealers/{slug}").json()
    assert public["company"]["logo_url"] == logo_url
    served = client.get(logo_url)
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    with Image.open(BytesIO(served.content)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (8, 8)


@pytest.mark.parametrize("status", ["pending", "rejected", "hidden"])
def test_dealer_review_is_not_public_until_moderator_publishes(integration, status):
    factory = integration["SessionLocal"]
    owner, reviewer = add_user(factory), add_user(factory)
    company = Company(owner_id=owner.id, name="Reviewed Motors", slug=f"reviewed-{uuid.uuid4().hex[:8]}", unp=str(100000000 + uuid.uuid4().int % 899999999), address="Minsk", phone="+375291234567", status="approved")
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        slug = company.slug
        review = DealerReview(company_id=company.id, author_id=reviewer.id, rating=5, text="Хорошая коммуникация", status=status)
        db.add(review)
        db.commit()
        review_id = review.id
    client = integration["client"]
    public = client.get(f"/api/v1/dealers/{slug}")
    assert public.status_code == 200
    assert public.json()["reviews"]["count"] == 0
    assert public.json()["reviews"]["items"] == []
    assert public.json()["reviews"]["average_rating"] is None


def test_dealer_review_create_edit_duplicate_report_and_public_aggregate(integration):
    factory = integration["SessionLocal"]
    owner, reviewer, reporter, moderator = add_user(factory), add_user(factory), add_user(factory), add_user(factory, "moderator")
    company = Company(owner_id=owner.id, name="Review Motors", slug=f"review-{uuid.uuid4().hex[:8]}", unp=str(100000000 + uuid.uuid4().int % 899999999), address="", phone="+375291234567", status="approved")
    with factory() as db:
        db.add(company)
        db.commit()
        db.refresh(company)
        slug = company.slug
    client = integration["client"]
    headers = login(client, reviewer.email)
    created = client.post(f"/api/v1/dealers/{slug}/reviews", json={"rating": 4, "text": "Всё прошло хорошо"}, headers=headers)
    assert created.status_code == 201, created.text
    review_id = created.json()["review"]["id"]
    assert created.json()["review"]["status"] == "pending"
    assert client.post(f"/api/v1/dealers/{slug}/reviews", json={"rating": 5, "text": "Повтор"}, headers=headers).status_code == 409
    edited = client.patch(f"/api/v1/dealer-reviews/{review_id}", json={"expected_revision": 1, "rating": 5, "text": "Исправленный отзыв"}, headers=headers)
    assert edited.status_code == 200, edited.text
    public = client.get(f"/api/v1/dealers/{slug}").json()["reviews"]
    assert public["count"] == 0 and public["average_rating"] is None and public["items"] == []

    moderator_client = type(client)(client.app, base_url="http://testserver")
    moderator_headers = login(moderator_client, moderator.email)
    queue = moderator_client.get("/api/v1/moderation/dealer-reviews?status=pending")
    assert queue.status_code == 200
    review = next(item for item in queue.json()["items"] if item["id"] == review_id)
    published = moderator_client.post(
        f"/api/v1/moderation/dealer-reviews/{review_id}/review",
        json={"expected_revision": review["revision"], "status": "published", "reason": "Проверен"},
        headers=moderator_headers,
    )
    assert published.status_code == 200, published.text
    public = client.get(f"/api/v1/dealers/{slug}").json()["reviews"]
    assert public["count"] == 1 and public["average_rating"] == 5
    assert public["items"][0]["text"] == "Исправленный отзыв"
    reporter_client = type(client)(client.app, base_url="http://testserver")
    report = reporter_client.post(
        f"/api/v1/dealer-reviews/{review_id}/reports", json={"reason": "Проверить содержание"},
        headers=login(reporter_client, reporter.email),
    )
    assert report.status_code == 201, report.text
    with factory() as db:
        actions = db.query(AuditEvent).filter_by(entity_type="dealer_review").all()
        assert {event.action for event in actions} >= {"created", "updated", "reported", "published"}
        assert db.query(DealerReviewReport).count() == 1
    moderator_queue = moderator_client.get("/api/v1/moderation/dealer-review-reports?status=open")
    assert moderator_queue.status_code == 200, moderator_queue.text
    report_item = next(item for item in moderator_queue.json()["items"] if item["id"] == report.json()["id"])
    assert report_item["company_name"] == company.name
    assert report_item["reason"] == "Проверить содержание"
    assert "reporter_id" not in report_item
    assert moderator_client.post(
        f"/api/v1/moderation/dealer-review-reports/{report.json()['id']}/resolve",
        json={"resolution": "Жалоба рассмотрена"},
    ).status_code == 403
    resolved = moderator_client.post(
        f"/api/v1/moderation/dealer-review-reports/{report.json()['id']}/resolve",
        json={"resolution": "Жалоба рассмотрена"},
        headers=moderator_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["report"]["status"] == "resolved"
    with factory() as db:
        resolution_event = db.query(AuditEvent).filter_by(
            entity_type="dealer_review_report", entity_id=uuid.UUID(report.json()["id"]),
        ).one()
        assert resolution_event.actor_id == moderator.id
        assert resolution_event.action == "resolved"
        assert resolution_event.details["resolution"] == "Жалоба рассмотрена"


def test_dealer_review_report_moderation_routes_require_moderator_and_csrf():
    from app.api.dependencies import require_csrf, require_moderator
    from app.api import dealer_reviews
    from app.main import CSRF_REQUIRED_OPERATIONS

    routes = {route.path: route for route in dealer_reviews.router.routes}
    queue = routes.get("/api/v1/moderation/dealer-review-reports")
    resolve = routes.get("/api/v1/moderation/dealer-review-reports/{report_id}/resolve")

    assert queue is not None
    assert resolve is not None
    assert require_moderator in [dependency.call for dependency in queue.dependant.dependencies]
    assert require_moderator in [dependency.call for dependency in resolve.dependant.dependencies]
    assert require_csrf in [dependency.call for dependency in resolve.dependant.dependencies]
    assert ("/api/v1/moderation/dealer-review-reports/{report_id}/resolve", "post") in CSRF_REQUIRED_OPERATIONS


def test_dealer_review_report_queue_hides_reporter_identity_and_resolution_is_audited():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.api import dealer_reviews

    routes = {route.path: route for route in dealer_reviews.router.routes}
    queue_route = routes.get("/api/v1/moderation/dealer-review-reports")
    resolve_route = routes.get("/api/v1/moderation/dealer-review-reports/{report_id}/resolve")
    assert queue_route is not None and resolve_route is not None

    report_id, review_id, company_id, reporter_id, moderator_id = [uuid.uuid4() for _ in range(5)]
    created_at = datetime.now(UTC)
    report = DealerReviewReport(id=report_id, review_id=review_id, reporter_id=reporter_id, reason="Утверждение не подтверждено", status="open", created_at=created_at)
    review = DealerReview(id=review_id, company_id=company_id, author_id=uuid.uuid4(), rating=4, text="Публичный текст отзыва", status="published")
    company = Company(id=company_id, name="Компания", slug="company", status="approved")

    class FakeDB:
        def __init__(self):
            self.added = []
            self.committed = False

        def execute(self, _statement):
            return SimpleNamespace(all=lambda: [(report, review, company)])

        def scalar(self, _statement):
            return report

        def add(self, value):
            self.added.append(value)

        def commit(self):
            self.committed = True

        def refresh(self, _value):
            pass

    db = FakeDB()
    moderator = User(id=moderator_id, role="moderator")
    queue = queue_route.endpoint(_moderator=moderator, db=db, status="open")
    assert queue["items"] == [{
        "id": report_id,
        "review_id": review_id,
        "company_name": "Компания",
        "review_rating": 4,
        "review_text": "Публичный текст отзыва",
        "reason": "Утверждение не подтверждено",
        "status": "open",
        "created_at": created_at,
    }]
    assert "reporter_id" not in queue["items"][0]

    resolved = resolve_route.endpoint(
        report_id=report_id,
        payload=SimpleNamespace(resolution="Жалоба рассмотрена"),
        moderator=moderator,
        _csrf=object(),
        db=db,
    )
    assert report.status == "resolved"
    assert db.committed
    assert resolved["report"]["status"] == "resolved"
    event = next(value for value in db.added if isinstance(value, AuditEvent))
    assert event.actor_id == moderator_id
    assert event.entity_type == "dealer_review_report"
    assert event.entity_id == report_id
    assert event.action == "resolved"
    assert event.details["resolution"] == "Жалоба рассмотрена"


def test_dealer_review_moderation_audit_preserves_moderator_rationale():
    from types import SimpleNamespace

    from app.api import dealer_reviews

    route = next(
        route for route in dealer_reviews.router.routes
        if route.path == "/api/v1/moderation/dealer-reviews/{review_id}/review"
    )
    review = DealerReview(
        id=uuid.uuid4(), company_id=uuid.uuid4(), author_id=uuid.uuid4(),
        rating=2, text="Отзыв", status="pending", revision=1,
    )
    moderator = User(id=uuid.uuid4(), role="moderator")

    class FakeDB:
        added = []

        def scalar(self, _statement):
            return review

        def add(self, value):
            self.added.append(value)

        def commit(self):
            pass

        def refresh(self, _value):
            pass

    db = FakeDB()
    route.endpoint(
        review_id=review.id,
        payload=SimpleNamespace(expected_revision=1, status="rejected", reason="Нет подтверждения покупки"),
        moderator=moderator,
        _csrf=object(),
        db=db,
    )
    event = next(item for item in db.added if isinstance(item, AuditEvent))
    assert event.details["reason"] == "Нет подтверждения покупки"
