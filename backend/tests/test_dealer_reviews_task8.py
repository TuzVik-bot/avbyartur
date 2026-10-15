import uuid
from io import BytesIO

import pytest
from PIL import Image

from app.models import AuditEvent, Company, DealerReview, DealerReviewReport, Listing, User
from app.security import hash_password

PASSWORD = "task8-dealer-review-test-password-123"


def add_user(factory, role="user"):
    email = f"{role}-{uuid.uuid4().hex[:12]}@example.test"
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


def test_public_stats_only_count_active_public_listings_and_approved_companies(integration):
    factory = integration["SessionLocal"]
    approved_owner, pending_owner, private_owner = add_user(factory), add_user(factory), add_user(factory)
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
        db.commit()
        pending_id = pending.id
    client = integration["client"]
    assert client.get("/api/v1/public-stats").json() == {"active_listings": 2, "approved_companies": 1}
    with factory() as db:
        db.get(Company, pending_id).status = "approved"
        db.commit()
    assert client.get("/api/v1/public-stats").json() == {"active_listings": 3, "approved_companies": 2}


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
