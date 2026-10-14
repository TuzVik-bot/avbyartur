import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import auth
from app.config import get_settings
from app.main import app
from app.models import User, UserConsent
from app.security import verify_password
from test_sms_otp_auth import _seed_registration_documents


def setup_registration(integration, monkeypatch):
    from app.managed_content import ManagedContent
    with integration['SessionLocal']() as db:
        seeded = db.scalar(select(ManagedContent.id).where(ManagedContent.key == 'terms_of_use'))
    if not seeded:
        _seed_registration_documents(integration['SessionLocal'])
    settings = get_settings().model_copy(update={
        'email_registration_enabled': True,
        'registration_terms_version': 'terms-test-v3',
        'registration_privacy_version': 'privacy-test-v2',
        'session_cookie_secure': False,
    })
    monkeypatch.setattr(auth, 'get_settings', lambda: settings)
    return TestClient(app)


def payload():
    return dict(email=f'{uuid.uuid4().hex}@example.com', password='Strong-password-123',
                display_name='Новый пользователь', accept_terms=True, accept_privacy=True,
                terms_version='terms-test-v3', privacy_version='privacy-test-v2')


def register(client, data):
    csrf = client.get('/api/v1/auth/otp/csrf').json()['csrf_token']
    return client.post('/api/v1/auth/register', json=data, headers={'X-CSRF-Token': csrf})


def test_email_registration_session_consents_and_listing(integration, monkeypatch):
    client = setup_registration(integration, monkeypatch)
    data = payload()
    data['email'] = data['email'].upper()
    result = register(client, data)
    assert result.status_code == 201, result.text
    assert result.json()['user']['role'] == 'user'
    assert client.get('/api/v1/me').status_code == 200
    with integration['SessionLocal']() as db:
        user = db.scalar(select(User).where(User.email == data['email'].lower()))
        assert verify_password(data['password'], user.password_hash)
        assert user.phone_verified_at is None
        consents = db.scalars(select(UserConsent).where(UserConsent.user_id == user.id)).all()
        assert {c.document_type for c in consents} == {'terms', 'privacy'}
        assert all(c.source == 'email_registration' for c in consents)
    draft = client.post('/api/v1/listings/drafts', json={}, headers={
        'X-CSRF-Token': result.json()['csrf_token'], 'Idempotency-Key': uuid.uuid4().hex})
    assert draft.status_code in (200, 201), draft.text
    assert register(client, data).status_code == 409
    login = client.post('/api/v1/auth/login', json={'email': data['email'], 'password': data['password']})
    assert login.status_code == 200


def test_registration_rejects_missing_csrf_bad_consent_and_weak_password(integration, monkeypatch):
    client = setup_registration(integration, monkeypatch)
    data = payload()
    assert client.post('/api/v1/auth/register', json=data).status_code == 403
    data['terms_version'] = 'old'
    assert register(client, data).status_code == 409
    data['password'] = 'short'
    assert register(client, data).status_code == 422


def test_registration_disabled_by_default(integration):
    assert register(TestClient(app), payload()).status_code == 404


def test_registration_rate_limit_and_unapproved_documents(integration, monkeypatch):
    client = setup_registration(integration, monkeypatch)
    data = payload()
    data['terms_version'] = 'old'
    for _ in range(5):
        assert register(client, data).status_code == 409
    assert register(client, data).status_code == 429


def test_registration_requires_published_documents(integration, monkeypatch):
    from app.managed_content import ManagedContent
    client = setup_registration(integration, monkeypatch)
    with integration['SessionLocal']() as db:
        document = db.scalar(select(ManagedContent).where(ManagedContent.key == 'privacy_policy'))
        document.status = 'draft'
        db.commit()
    assert client.get('/api/v1/auth/capabilities').json()['email_registration'] is False
    data = payload()
    assert register(client, data).status_code == 503
    with integration['SessionLocal']() as db:
        assert db.scalar(select(User.id).where(User.email == data['email'])) is None


def test_explicit_temporary_registration_without_managed_documents(integration, monkeypatch):
    from app.email_registration_policy import PILOT_TERMS_VERSION, PILOT_PRIVACY_VERSION
    settings = get_settings().model_copy(update={
        'email_registration_enabled': True, 'email_registration_pilot_enabled': True,
        'registration_terms_version': PILOT_TERMS_VERSION,
        'registration_privacy_version': PILOT_PRIVACY_VERSION, 'session_cookie_secure': False})
    monkeypatch.setattr(auth, 'get_settings', lambda: settings)
    client = TestClient(app)
    data = payload()
    data.update(terms_version=PILOT_TERMS_VERSION, privacy_version=PILOT_PRIVACY_VERSION)
    assert client.get('/api/v1/auth/capabilities').json()['email_registration'] is True
    assert register(client, data).status_code == 201


def test_different_users_are_not_limited_to_five_registrations_in_total(integration, monkeypatch):
    client = setup_registration(integration, monkeypatch)
    for _ in range(6):
        data = payload()
        data['terms_version'] = 'old'
        assert register(client, data).status_code == 409
