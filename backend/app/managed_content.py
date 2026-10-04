"""Versioned non-secret editorial content and safe notification templates."""

from datetime import datetime
from string import Formatter
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base

CONTENT_KINDS = {"notification_template", "seo_page", "legal_document"}
TEMPLATE_VARIABLES = {
    "saved_search_email": {"listing_title", "listing_url", "search_name"},
    "email_verification": {"confirmation_url", "confirmation_code", "display_name"},
    "password_recovery": {"confirmation_url", "confirmation_code", "display_name"},
}
LEGAL_KEYS = {"terms_of_use", "privacy_policy", "cookie_policy", "listing_rules", "commercial_offer", "complaints_policy"}


class ManagedContent(Base):
    __tablename__ = "managed_content"
    __table_args__ = (
        UniqueConstraint("kind", "key", name="uq_managed_content_kind_key"),
        CheckConstraint("kind IN ('notification_template', 'seo_page', 'legal_document')", name="ck_managed_content_kind"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_managed_content_status"),
        CheckConstraint("revision >= 1", name="ck_managed_content_revision"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ManagedContentVersion(Base):
    __tablename__ = "managed_content_versions"
    __table_args__ = (
        UniqueConstraint("content_id", "revision", name="uq_managed_content_version"),
        CheckConstraint("revision >= 1", name="ck_managed_content_version_revision"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_managed_content_version_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    content_id: Mapped[UUID] = mapped_column(ForeignKey("managed_content.id", ondelete="RESTRICT"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    status: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reason: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlainContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def plain_text(cls, value):
        if isinstance(value, str) and ("<" in value or ">" in value or "\x00" in value):
            raise ValueError("Content must be plain text")
        return value


class TemplatePayload(PlainContent):
    subject: str = Field(min_length=1, max_length=180)
    body: str = Field(min_length=1, max_length=5000)


class SeoPayload(PlainContent):
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=10, max_length=500)
    heading: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=120, max_length=20000)
    canonical_path: str = Field(min_length=5, max_length=300)
    minimum_results: int = Field(default=5, ge=5, le=100)
    indexable: bool = False
    filters: dict[str, str] = Field(default_factory=dict)

    @field_validator("canonical_path")
    @classmethod
    def local_car_path(cls, value: str):
        if not (value == "/cars" or value.startswith("/cars/")) or any(part in value for part in ("//", "..", "?", "#", "\\")):
            raise ValueError("Canonical path must be a local car route")
        return value

    @field_validator("filters")
    @classmethod
    def known_identifiers(cls, value: dict[str, str]):
        if set(value) - {"make_id", "model_id", "region_id", "city_id"}:
            raise ValueError("Unsupported SEO filter")
        return {key: str(UUID(identifier)) for key, identifier in value.items()}


class OperatorPayload(PlainContent):
    legal_name: str = Field(min_length=2, max_length=180)
    unp: str = Field(pattern=r"^\d{9}$")
    address: str = Field(min_length=4, max_length=300)
    contact_email: EmailStr


class LegalPayload(PlainContent):
    title: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=120, max_length=100000)
    document_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    approved: bool = False
    operator: OperatorPayload


def validate_content(kind: str, key: str, payload: dict, status: str) -> dict:
    if kind == "notification_template":
        if key not in TEMPLATE_VARIABLES:
            raise ValueError("Unsupported notification template")
        content = TemplatePayload.model_validate(payload)
        if "\r" in content.subject or "\n" in content.subject:
            raise ValueError("Email subject cannot contain line breaks")
        for text in (content.subject, content.body):
            for _literal, variable, formatting, conversion in Formatter().parse(text):
                if variable is not None and (variable not in TEMPLATE_VARIABLES[key] or formatting or conversion):
                    raise ValueError("Unsupported template placeholder")
        return content.model_dump()
    if kind == "seo_page":
        return SeoPayload.model_validate(payload).model_dump()
    if kind == "legal_document" and key in LEGAL_KEYS:
        content = LegalPayload.model_validate(payload)
        if status == "published" and not content.approved:
            raise ValueError("Publication requires document approval")
        return content.model_dump(mode="json")
    raise ValueError("Unsupported content resource")


def render_notification_template(
    db: Session, key: str, values: dict[str, str], *, default_subject: str, default_body: str,
) -> tuple[str, str]:
    row = db.scalar(select(ManagedContent).where(ManagedContent.kind == "notification_template", ManagedContent.key == key, ManagedContent.status == "published"))
    if row is None:
        return default_subject, default_body
    try:
        payload = validate_content(row.kind, row.key, row.payload, row.status)
        safe_values = {name: str(values.get(name, "")) for name in TEMPLATE_VARIABLES[key]}
        subject = payload["subject"].format_map(safe_values)
        body = payload["body"].format_map(safe_values)
        if "\r" in subject or "\n" in subject:
            raise ValueError("Invalid rendered subject")
        return subject, body
    except (ValueError, KeyError, ValidationError):
        raise RuntimeError("Notification template configuration is invalid") from None
