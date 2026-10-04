"""A narrow, versioned set of non-secret application limits."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.db import Base

LIMIT_KEYS = frozenset({"private_listing_quota", "company_listing_quota", "saved_search_limit"})


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"
    __table_args__ = (
        CheckConstraint("key IN ('private_listing_quota', 'company_listing_quota', 'saved_search_limit')", name="ck_runtime_setting_key"),
        CheckConstraint("value BETWEEN 1 AND 10000", name="ck_runtime_setting_value"),
        CheckConstraint("revision >= 1", name="ck_runtime_setting_revision"),
    )

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def runtime_limit(db: Session | None, key: str, *, fallback: int | None = None) -> int:
    if key not in LIMIT_KEYS:
        raise ValueError("Unknown runtime limit")
    row = db.get(RuntimeSetting, key) if db is not None else None
    if row is not None:
        if type(row.value) is not int or not 1 <= row.value <= 10000 or type(row.revision) is not int or row.revision < 1:
            raise RuntimeError("runtime setting integrity failure")
        return row.value
    value = fallback if fallback is not None else getattr(get_settings(), key)
    if type(value) is not int or not 1 <= value <= 10000:
        raise RuntimeError("runtime setting integrity failure")
    return value
