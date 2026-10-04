import io
import os
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Event, Lock

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import event, select, text

from app.models import Listing, ListingPhoto, User
from app.security import hash_password


PASSWORD = "upload-concurrency-test-password"


def _large_jpeg() -> bytes:
    image = Image.frombytes("RGB", (1000, 1000), os.urandom(3_000_000))
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=95, subsampling=0)
    data = stream.getvalue()
    assert len(data) > 1024 * 1024
    return data


def _upload_lock_is_waiting(engine) -> bool:
    with engine.connect() as connection:
        return bool(connection.execute(text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND state = 'active'
                  AND wait_event_type = 'Lock'
                  AND position('FOR UPDATE' in upper(query)) > 0
            )
        """)).scalar_one())


def test_two_large_uploads_keep_health_live_during_row_lock(integration, monkeypatch):
    engine = integration["engine"]

    def bound_lock_wait(dbapi_connection, _connection_record, _connection_proxy):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SET lock_timeout = '8s'")
        finally:
            cursor.close()

    factory = integration["SessionLocal"]
    with factory() as db:
        owner = User(
            email=f"upload-concurrency-{uuid.uuid4().hex}@example.com",
            display_name="Upload concurrency test",
            password_hash=hash_password(PASSWORD),
            role="user",
            status="active",
        )
        db.add(owner)
        db.flush()
        listing = Listing(
            owner_id=owner.id,
            slug=f"upload-concurrency-{uuid.uuid4().hex}",
            title="Local concurrency test",
            status="draft",
        )
        db.add(listing)
        db.commit()
        owner_email = owner.email
        listing_id = listing.id

    image = _large_jpeg()
    read_started = Event()
    release_read = Event()
    read_lock = Lock()
    original_read = tempfile.SpooledTemporaryFile.read

    def gated_read(spooled_file, size=-1):
        should_pause = False
        if getattr(spooled_file, "_rolled", False):
            with read_lock:
                if not read_started.is_set():
                    read_started.set()
                    should_pause = True
        if should_pause and not release_read.wait(timeout=12):
            raise TimeoutError("upload read gate was not released")
        return original_read(spooled_file, size)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "read", gated_read)
    app = integration["client"].app
    first_response = second_response = health_response = None
    upload_wait_observed = False
    health_responded_before_release = False
    request_errors = []

    event.listen(engine, "checkout", bound_lock_wait)
    try:
        with TestClient(app) as client:
            login = client.post("/api/v1/auth/login", json={"email": owner_email, "password": PASSWORD})
            assert login.status_code == 200, login.text
            upload_url = f"/api/v1/listings/{listing_id}/photos"

            def upload(key: str):
                return client.post(
                    upload_url,
                    files={"file": ("large.jpg", image, "image/jpeg")},
                    headers={"X-CSRF-Token": login.json()["csrf_token"], "Idempotency-Key": key},
                )

            with ThreadPoolExecutor(max_workers=3) as requests:
                first = second = probe = None
                try:
                    first = requests.submit(upload, "concurrent-photo-1")
                    if read_started.wait(timeout=5):
                        second = requests.submit(upload, "concurrent-photo-2")
                        deadline = time.monotonic() + 5
                        while time.monotonic() < deadline and not _upload_lock_is_waiting(engine):
                            time.sleep(0.025)
                        upload_wait_observed = _upload_lock_is_waiting(engine)
                        if upload_wait_observed:
                            probe = requests.submit(client.get, "/health/live")
                            try:
                                health_response = probe.result(timeout=1)
                                health_responded_before_release = True
                            except FutureTimeout:
                                pass
                finally:
                    release_read.set()
                    for future, name in ((first, "first upload"), (second, "second upload"), (probe, "health probe")):
                        if future is None:
                            continue
                        try:
                            response = future.result(timeout=15)
                            if name == "first upload":
                                first_response = response
                            elif name == "second upload":
                                second_response = response
                            elif health_response is None:
                                health_response = response
                        except Exception as error:
                            request_errors.append(f"{name}: {type(error).__name__}")
    finally:
        release_read.set()
        event.remove(engine, "checkout", bound_lock_wait)

    assert read_started.is_set(), "large upload did not reach the spooled-file read"
    assert upload_wait_observed, "second upload never reached a PostgreSQL row-lock wait"
    assert health_responded_before_release, "/health/live stalled while the second upload waited for a lock"
    assert health_response is not None and health_response.status_code == 200
    assert first_response is not None and first_response.status_code == 200, getattr(first_response, "text", None)
    assert second_response is not None and second_response.status_code == 200, getattr(second_response, "text", None)
    assert request_errors == []

    with factory() as db:
        photos = db.scalars(
            select(ListingPhoto).where(ListingPhoto.listing_id == listing_id).order_by(ListingPhoto.position)
        ).all()
        assert len(photos) == 2
        assert [photo.position for photo in photos] == [0, 1]
