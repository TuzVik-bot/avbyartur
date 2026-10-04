"""Versioned template and SEO administration must reach real consumers."""

from fastapi.testclient import TestClient
from datetime import datetime, timezone
from types import SimpleNamespace
from sqlalchemy import select

from app import models

from test_admin_management import add_user, signed_client, PASSWORD


def admin(integration):
    return signed_client(integration, add_user(integration["SessionLocal"], role="admin"))


def content_body(payload, **changes):
    return {"payload": payload, "status": "published", "expected_revision": 0,
            "reason": "Утверждённая редакция материала", "confirmation": "UPDATE_CONTENT",
            "current_password": PASSWORD, **changes}


def test_notification_template_is_versioned_and_applied_by_renderer(integration):
    client, headers = admin(integration)
    payload = {"subject": "Автомобиль: {listing_title}", "body": "Новый вариант по поиску {search_name}\n{listing_url}"}
    endpoint = "/api/v1/admin/content/notification_template/saved_search_email"
    response = client.put(endpoint, json=content_body(payload), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["content"]["revision"] == 1
    with integration["SessionLocal"]() as db:
        from app.managed_content import render_notification_template
        subject, body = render_notification_template(db, "saved_search_email", {
            "listing_title": "Audi A4", "search_name": "Семейный автомобиль", "listing_url": "https://cars.example/cars/audi-1",
        }, default_subject="Default", default_body="Default body")
        assert subject == "Автомобиль: Audi A4"
        assert body == "Новый вариант по поиску Семейный автомобиль\nhttps://cars.example/cars/audi-1"
    assert client.put(endpoint, json=content_body(payload), headers=headers).status_code == 409
    history = client.get(endpoint + "/versions")
    assert history.status_code == 200 and history.json()["items"][0]["payload"] == payload


def test_templates_reject_attribute_access_and_unknown_variables(integration):
    client, headers = admin(integration)
    endpoint = "/api/v1/admin/content/notification_template/saved_search_email"
    for body in ["{settings.session_secret}", "{listing_title.__class__}", "{password}", "<script>{listing_title}</script>"]:
        response = client.put(endpoint, json=content_body({"subject": "Извещение", "body": body}), headers=headers)
        assert response.status_code == 422, response.text
    assert client.put(endpoint, json=content_body({"subject": "Извещение", "body": "{listing_title}"})).status_code == 403
    guest = TestClient(integration["client"].app)
    assert guest.get("/api/v1/admin/content").status_code == 401


def test_seo_content_drafts_are_private_and_empty_results_prevent_indexing(integration):
    client, headers = admin(integration)
    endpoint = "/api/v1/admin/content/seo_page/cars-minsk"
    payload = {"title": "Автомобили в Минске", "description": "Собственные объявления продавцов в Минске",
               "heading": "Автомобили в Минске", "body": "Описание выбора автомобилей, проверки продавцов и условий покупки. " * 4,
               "canonical_path": "/cars/city/minsk", "minimum_results": 5, "indexable": True}
    created = client.put(endpoint, json=content_body(payload, status="draft"), headers=headers)
    assert created.status_code == 200, created.text
    assert client.get("/api/v1/content/seo_page/cars-minsk").status_code == 404
    published = client.put(endpoint, json=content_body(payload, expected_revision=1), headers=headers)
    assert published.status_code == 200, published.text
    public = client.get("/api/v1/content/seo_page/cars-minsk")
    assert public.status_code == 200, public.text
    assert public.json()["content"]["payload"]["title"] == "Автомобили в Минске"
    assert public.json()["indexable"] is False
    unsafe = client.put(endpoint, json=content_body({**payload, "canonical_path": "https://foreign.example/"}, expected_revision=2), headers=headers)
    assert unsafe.status_code == 422


def test_legal_publication_requires_operator_and_document_approval(integration):
    client, headers = admin(integration)
    endpoint = "/api/v1/admin/content/legal_document/privacy_policy"
    payload = {"title": "Политика конфиденциальности", "body": "Утверждённый текст политики обработки данных. " * 5,
               "document_version": "2026-10-01", "approved": False,
               "operator": {"legal_name": "Тестовый оператор", "unp": "123456789", "address": "Тестовый адрес", "contact_email": "operator@example.com"}}
    assert client.put(endpoint, json=content_body(payload), headers=headers).status_code == 422
    draft = client.put(endpoint, json=content_body(payload, status="draft"), headers=headers)
    assert draft.status_code == 200, draft.text
    published = client.put(endpoint, json=content_body({**payload, "approved": True}, expected_revision=1), headers=headers)
    assert published.status_code == 200, published.text
    public = client.get("/api/v1/content/legal_document/privacy_policy")
    assert public.status_code == 200 and public.json()["content"]["payload"]["document_version"] == "2026-10-01"


def test_published_template_changes_actual_saved_search_email_delivery(integration, monkeypatch):
    from app.identity_models import VerifiedEmailContact
    from app.services import enqueue_saved_search_match
    from test_saved_search_notifications import add_listing, add_user as subscriber_user, run_job
    import app.worker as worker

    client, headers = admin(integration)
    payload = {"subject": "Подборка: {listing_title}", "body": "Поиск {search_name}\n{listing_url}"}
    saved = client.put("/api/v1/admin/content/notification_template/saved_search_email", json=content_body(payload), headers=headers)
    assert saved.status_code == 200, saved.text
    factory = integration["SessionLocal"]
    owner = subscriber_user(factory, "template-owner@example.com")
    subscriber = subscriber_user(factory, "template-subscriber@example.com")
    listing = add_listing(factory, owner.id, title="Audi A4")
    with factory() as db:
        search = models.SavedSearch(user_id=subscriber.id, name="Семейный", search_url="/cars?q=audi", filters={},
                                    notifications_enabled=True, notification_channel="email", notification_frequency="instant")
        db.add_all([search, VerifiedEmailContact(user_id=subscriber.id, email=subscriber.email, verified_at=datetime.now(timezone.utc))])
        db.flush(); enqueue_saved_search_match(db, listing); db.commit()
        match_id = db.scalar(select(models.WorkerJob.id).where(models.WorkerJob.kind == "saved-search.match"))
    class Sender:
        is_configured = True
        sent = []
        def send_email(self, recipient, subject, body, *, idempotency_key):
            self.sent.append((recipient, subject, body))
    sender = Sender()
    monkeypatch.setattr(worker, "get_email_sender", lambda *_: sender)
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(public_app_url="https://cars.example.com"))
    run_job(factory, match_id)
    with factory() as db:
        delivery_id = db.scalar(select(models.WorkerJob.id).where(models.WorkerJob.kind == "notification.deliver"))
    assert delivery_id is not None
    run_job(factory, delivery_id)
    assert sender.sent == [(subscriber.email, "Подборка: Audi A4", "Поиск Семейный\nhttps://cars.example.com/cars?q=audi")]


def test_identity_email_template_is_applied_when_challenge_is_queued(integration, monkeypatch):
    from app.api import account
    from app.identity_models import IdentityEmailOutbox

    client, headers = admin(integration)
    payload = {"subject": "Адрес: {display_name}", "body": "Подтверждение. Код: {confirmation_code}"}
    saved = client.put("/api/v1/admin/content/notification_template/email_verification", json=content_body(payload), headers=headers)
    assert saved.status_code == 200, saved.text
    class Sender:
        is_configured = True
    monkeypatch.setattr(account, "get_email_sender", lambda *_: Sender())
    requested = client.post("/api/v1/auth/email/verification/request", json={"email": "template-new@example.com"}, headers=headers)
    assert requested.status_code == 202, requested.text
    with integration["SessionLocal"]() as db:
        outbox = db.scalar(select(IdentityEmailOutbox))
        assert outbox.subject == "Адрес: Участник"
        assert outbox.body.startswith("Подтверждение. Код: ")
