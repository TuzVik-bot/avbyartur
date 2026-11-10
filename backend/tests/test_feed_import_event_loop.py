import asyncio

from app.api import feeds
from tests.test_dealer_feed_policies import (
    _add_company,
    _add_user,
    _csrf,
    _login,
    _upload_csv,
)


def _inside_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def test_file_feed_import_parses_and_writes_off_the_event_loop(
    integration, monkeypatch
):
    factory = integration["SessionLocal"]
    owner_id, owner_email = _add_user(factory, label="feed-loop-owner")
    _add_company(factory, owner_id)
    client, csrf = _login(integration, owner_email)
    created = client.post(
        "/api/v1/dealer/feeds",
        json={"name": "Event loop feed", "format": "csv"},
        headers=_csrf(csrf),
    )
    assert created.status_code == 200, created.text
    feed_id = created.json()["feed"]["id"]

    observed: dict[str, bool] = {}
    original_lock_owner = feeds.lock_owner
    original_parse = feeds.parse_feed_bytes
    original_create = feeds.create_feed_import

    def spy(name, function):
        def wrapper(*args, **kwargs):
            observed[name] = _inside_event_loop()
            return function(*args, **kwargs)

        return wrapper

    monkeypatch.setattr(feeds, "lock_owner", spy("lock_owner", original_lock_owner))
    monkeypatch.setattr(feeds, "parse_feed_bytes", spy("parse", original_parse))
    monkeypatch.setattr(feeds, "create_feed_import", spy("create", original_create))

    response = _upload_csv(
        client,
        feed_id=feed_id,
        csrf=csrf,
        key="event-loop-import",
        content=b"dealer_external_id,manual_make,manual_model,title\nLOOP-1,Toyota,Camry,Loop one\n",
        dry_run=True,
    )

    assert response.status_code == 200, response.text
    assert observed == {"lock_owner": False, "parse": False, "create": False}
