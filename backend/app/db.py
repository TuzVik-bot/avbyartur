from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# Sized under Postgres max_connections=40 (docker-compose.yml).
POOL_SIZE = 15
POOL_MAX_OVERFLOW = 10
# Fail a request quickly instead of queueing behind an exhausted pool.
POOL_TIMEOUT_SECONDS = 10


def _make_engine(url: str):
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=POOL_SIZE,
        max_overflow=POOL_MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT_SECONDS,
    )


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configure_database(url: str) -> None:
    global engine, SessionLocal
    engine.dispose()
    engine = _make_engine(url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
