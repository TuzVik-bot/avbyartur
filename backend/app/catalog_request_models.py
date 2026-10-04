"""Durable, auditable seller requests for absent catalog modifications."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import new_id


class CatalogRequest(Base):
    __tablename__ = "catalog_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'resolved', 'rejected')",
            name="ck_catalog_request_status",
        ),
        CheckConstraint("revision > 0", name="ck_catalog_request_revision_positive"),
        CheckConstraint(
            "length(idempotency_key_hash) = 64",
            name="ck_catalog_request_idempotency_hash_length",
        ),
        CheckConstraint(
            "length(request_digest) = 64",
            name="ck_catalog_request_digest_length",
        ),
        CheckConstraint(
            "length(idempotency_payload_digest) = 64",
            name="ck_catalog_request_idempotency_payload_digest_length",
        ),
        UniqueConstraint(
            "actor_id",
            "idempotency_key_hash",
            name="uq_catalog_request_actor_idempotency_hash",
        ),
        Index(
            "ix_catalog_requests_status_created",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "ix_catalog_requests_listing_created",
            "listing_id",
            "created_at",
            "id",
        ),
        Index(
            "uq_catalog_request_pending_listing_digest",
            "listing_id",
            "request_digest",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    listing_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    manual_modification_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    resolved_modification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("catalog_modifications.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
