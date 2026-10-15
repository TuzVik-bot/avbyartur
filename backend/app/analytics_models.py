"""Privacy-limited first-party contact click events."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ContactClickEvent(Base):
    __tablename__ = "contact_click_events"
    __table_args__ = (
        CheckConstraint("channel IN ('phone', 'telegram', 'viber', 'internal_chat')", name="ck_contact_click_channel"),
        UniqueConstraint("dedup_id", name="uq_contact_click_dedup"),
        Index("ix_contact_click_listing_created", "listing_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    dedup_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
