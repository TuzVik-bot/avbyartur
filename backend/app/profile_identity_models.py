"""Profile identity and global notification preference persistence."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


class ProfilePhoneChangeChallenge(Base):
    """Short-lived, purpose-bound proof for both sides of a phone change."""

    __tablename__ = "profile_phone_change_challenges"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key_hash", name="uq_profile_phone_change_idempotency"
        ),
        CheckConstraint("attempt_count >= 0", name="ck_profile_phone_change_attempts"),
        Index("ix_profile_phone_change_user_id", "user_id"),
        Index("ix_profile_phone_change_user_created", "user_id", "created_at"),
        Index("ix_profile_phone_change_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    old_phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    new_phone_e164: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    old_code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    new_code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserNotificationPreferences(Base):
    """Global web/email channel settings; saved-search choices remain local."""

    __tablename__ = "user_notification_preferences"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_user_notification_preferences_revision"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    web_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
