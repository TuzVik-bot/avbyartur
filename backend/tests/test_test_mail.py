from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_current_user
from types import SimpleNamespace


def test_test_mail_never_exposes_inbox_to_guests():
    result = TestClient(app).get('/api/v1/admin/test-mail/messages')
    assert result.status_code == 401


def test_test_mail_denies_ordinary_accounts(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace(role='user'))
    assert TestClient(app).get('/api/v1/admin/test-mail/messages').status_code == 403


def test_test_mail_disabled_for_admin_by_default(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace(role='admin'))
    assert TestClient(app).get('/api/v1/admin/test-mail/messages').status_code == 404


def test_enabled_inbox_is_read_only_and_never_cached(monkeypatch):
    from app.api import test_mail
    import uuid
    identifier = "abcdefghijklmnopqrstuv"
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace(role='admin'))
    monkeypatch.setattr(test_mail, 'get_settings', lambda: SimpleNamespace(test_mail_enabled=True))
    monkeypatch.setattr(test_mail, 'read_test_mail', lambda path: {'messages':[{'ID':identifier,'Subject':'Подтверждение','To':[{'Address':'test@example.com'}],'Created':'2026-10-05'}]})
    client = TestClient(app)
    result = client.get('/api/v1/admin/test-mail/messages')
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    assert result.json()['items'][0]['id'] == identifier
    assert client.delete('/api/v1/admin/test-mail/messages').status_code == 405


def test_message_detail_accepts_mailpit_ids_and_rejects_paths(monkeypatch):
    from app.api import test_mail
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: SimpleNamespace(role='admin'))
    monkeypatch.setattr(test_mail, 'get_settings', lambda: SimpleNamespace(test_mail_enabled=True))
    monkeypatch.setattr(test_mail, 'read_test_mail', lambda path: {'Subject':'Подтверждение', 'Text':'Тело тестового письма'})
    client=TestClient(app)
    result=client.get('/api/v1/admin/test-mail/messages/abcdefghijklmnopqrstuv')
    assert result.status_code == 200
    assert result.json()['body'] == 'Тело тестового письма'
    assert client.get('/api/v1/admin/test-mail/messages/not-a-valid-id').status_code == 422
