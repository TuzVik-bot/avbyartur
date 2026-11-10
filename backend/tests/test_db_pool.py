from sqlalchemy.pool import QueuePool

from app import db


def test_engine_pool_is_explicit_and_fits_postgres_connection_limit():
    engine = db._make_engine("postgresql+psycopg://user:secret@127.0.0.1:1/example_test")
    try:
        pool = engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == db.POOL_SIZE == 15
        assert pool._max_overflow == db.POOL_MAX_OVERFLOW == 10
        assert pool._timeout == db.POOL_TIMEOUT_SECONDS == 10
        assert pool._pre_ping is True
        # docker-compose.yml: max_connections=40 minus 3 superuser slots.
        assert db.POOL_SIZE + db.POOL_MAX_OVERFLOW <= 37 - 10
    finally:
        engine.dispose()
