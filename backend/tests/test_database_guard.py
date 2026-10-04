import pytest

from conftest import _validate_disposable_test_database


RUNTIME_DATABASE_URL = "postgresql+psycopg://runtime:runtime-secret@db:5432/avtorinok"


def test_test_database_requires_exact_disposable_confirmation():
    with pytest.raises(ValueError, match="DISPOSABLE_CONFIRMATION"):
        _validate_disposable_test_database(
            "postgresql+psycopg://test:test-secret@db:5432/avtorinok_run_test",
            runtime_url=RUNTIME_DATABASE_URL,
            confirmation=None,
        )


def test_test_database_rejects_known_preview_database():
    database_name = "avtorinok_preview_20260927_00aa22_test"
    with pytest.raises(ValueError, match="preview"):
        _validate_disposable_test_database(
            f"postgresql+psycopg://test:test-secret@127.0.0.1:5432/{database_name}",
            runtime_url=RUNTIME_DATABASE_URL,
            confirmation=database_name,
        )


def test_test_database_rejects_runtime_database_target_without_disclosing_url():
    database_name = "avtorinok_run_test"
    with pytest.raises(ValueError, match="runtime database") as exc_info:
        _validate_disposable_test_database(
            f"postgresql+psycopg://other:do-not-print@localhost/{database_name}",
            runtime_url=f"postgresql+psycopg://runtime:runtime-secret@127.0.0.1:5432/{database_name}",
            confirmation=database_name,
        )

    assert "do-not-print" not in str(exc_info.value)
    assert "runtime-secret" not in str(exc_info.value)


def test_test_database_accepts_confirmed_isolated_postgres_target():
    database_name = "avtorinok_ci_run_test"
    url = _validate_disposable_test_database(
        f"postgresql+psycopg://test:test-secret@postgres-ci:5432/{database_name}",
        runtime_url=RUNTIME_DATABASE_URL,
        confirmation=database_name,
    )

    assert url.database == database_name


@pytest.mark.parametrize(
    ("url", "confirmation", "message"),
    [
        ("postgresql+psycopg://test:test-secret@db:5432/avtorinok", "avtorinok", "_test"),
        ("sqlite:///avtorinok_run_test", "avtorinok_run_test", "PostgreSQL"),
    ],
)
def test_test_database_requires_postgres_and_test_database_name(url, confirmation, message):
    with pytest.raises(ValueError, match=message):
        _validate_disposable_test_database(
            url,
            runtime_url=RUNTIME_DATABASE_URL,
            confirmation=confirmation,
        )
