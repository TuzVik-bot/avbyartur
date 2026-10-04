import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db import Base, configure_database, get_db
from app.main import app
from app import models  # noqa: F401


KNOWN_PREVIEW_DATABASES = frozenset({"avtorinok_preview_20260927_00aa22_test"})
TEST_DATABASE_CONFIRMATION_ENV = "TEST_DATABASE_DISPOSABLE_CONFIRMATION"


def _postgres_database_target(url: str, setting_name: str) -> tuple[str, str, int, str]:
    try:
        parsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        raise ValueError(f"{setting_name} must be a valid PostgreSQL URL") from None
    if parsed.get_backend_name() != "postgresql":
        raise ValueError(f"{setting_name} must use PostgreSQL")

    database_name = parsed.database or ""
    if not database_name:
        raise ValueError(f"{setting_name} must include a database name")

    host = parsed.host or parsed.query.get("host")
    if isinstance(host, (list, tuple)):
        host = host[0] if host else None
    normalized_host = str(host or "").strip().lower().rstrip(".")
    if (
        not normalized_host
        or normalized_host in {"localhost", "127.0.0.1", "::1"}
        or normalized_host.startswith("/")
    ):
        normalized_host = "<local>"
    port = parsed.port or 5432
    return parsed.get_backend_name(), normalized_host, port, database_name


def _validate_disposable_test_database(
    test_url: str,
    *,
    runtime_url: str,
    confirmation: str | None,
) -> URL:
    test_target = _postgres_database_target(test_url, "TEST_DATABASE_URL")
    runtime_target = _postgres_database_target(runtime_url, "DATABASE_URL")
    database_name = test_target[3]

    if not database_name.endswith("_test"):
        raise ValueError("TEST_DATABASE_URL database name must end in _test")
    if database_name in KNOWN_PREVIEW_DATABASES:
        raise ValueError("TEST_DATABASE_URL points at a reserved preview database")
    if test_target == runtime_target:
        raise ValueError("TEST_DATABASE_URL must not point at the runtime database")
    if confirmation != database_name:
        raise ValueError(
            f"Set {TEST_DATABASE_CONFIRMATION_ENV} to the exact name of the dedicated disposable database"
        )
    return make_url(test_url)


@pytest.fixture(scope="session")
def integration(tmp_path_factory) -> Generator[dict, None, None]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL and "
            f"{TEST_DATABASE_CONFIRMATION_ENV} for a dedicated disposable PostgreSQL database"
        )
    runtime_url = os.environ.get("DATABASE_URL") or get_settings().database_url
    try:
        url = _validate_disposable_test_database(
            url,
            runtime_url=runtime_url,
            confirmation=os.getenv(TEST_DATABASE_CONFIRMATION_ENV),
        )
    except ValueError as exc:
        pytest.fail(str(exc), pytrace=False)
    os.environ["SESSION_SECRET"] = "integration-test-secret-with-over-32-characters"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["APP_ENV"] = "development"
    media_root = tmp_path_factory.mktemp("avtorinok-media")
    os.environ["MEDIA_ROOT"] = str(media_root)
    get_settings.cache_clear()
    configure_database(url)
    from app.db import engine, SessionLocal

    Base.metadata.create_all(engine)
    factory = SessionLocal
    import app.worker as worker
    worker.SessionLocal = factory
    worker.engine = engine

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {"engine": engine, "SessionLocal": factory, "client": TestClient(app), "media_root": Path(media_root)}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def isolate_integration_database_between_tests(request):
    """Prevent rows written by one integration test from affecting another."""
    if "integration" not in request.fixturenames:
        return
    integration = request.getfixturevalue("integration")
    engine = integration["engine"]
    preparer = engine.dialect.identifier_preparer
    tables = []
    for table in Base.metadata.sorted_tables:
        name = preparer.quote(table.name)
        if table.schema:
            name = f"{preparer.quote_schema(table.schema)}.{name}"
        tables.append(name)
    if tables:
        with engine.begin() as connection:
            connection.execute(text(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    # The session DB fixture also owns a pytest-created media directory.
    # Isolate files as well as rows so a prior photo test cannot change a
    # later upload's quarantine or derivative preconditions.
    for entry in integration["media_root"].iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
