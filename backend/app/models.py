import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
    func,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("phone_e164", name="uq_user_phone_e164"),
        CheckConstraint(
            "phone_e164 IS NULL OR phone_e164 ~ '^\\+375(25|29|33|44)[0-9]{7}$'",
            name="ck_user_phone_e164_supported",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "phone_e164 IS NULL OR phone_verified_at IS NOT NULL",
            name="ck_user_phone_verified_timestamp",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str | None] = mapped_column(String(512), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(16), nullable=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("owner_id", name="uq_company_owner"),
        UniqueConstraint("slug", name="uq_company_slug"),
        UniqueConstraint("unp", name="uq_company_unp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(200))
    unp: Mapped[str] = mapped_column(String(9))
    address: Mapped[str] = mapped_column(String(300))
    phone: Mapped[str] = mapped_column(String(40))
    business_hours: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    moderation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DealerTeamMember(Base):
    __tablename__ = "dealer_team_members"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_dealer_team_company_user"),
        CheckConstraint("role IN ('admin', 'seller', 'viewer')", name="ck_dealer_team_role"),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_dealer_team_status"),
        Index("ix_dealer_team_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DealerFeed(Base):
    __tablename__ = "dealer_feeds"
    __table_args__ = (
        CheckConstraint("format IN ('csv', 'xml', 'api')", name="ck_dealer_feed_format"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_dealer_feed_status"),
        CheckConstraint("manual_conflict_policy IN ('review', 'feed_wins')", name="ck_dealer_feed_manual_conflict_policy"),
        CheckConstraint("missing_retirement_delay_hours BETWEEN 1 AND 8760", name="ck_dealer_feed_missing_retirement_delay_hours"),
        UniqueConstraint("api_token_digest", name="uq_dealer_feed_api_token_digest"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    format: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    field_mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    manual_conflict_policy: Mapped[str] = mapped_column(String(16), default="review", server_default="review", nullable=False)
    missing_retirement_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    missing_retirement_delay_hours: Mapped[int] = mapped_column(Integer, default=168, server_default="168", nullable=False)
    api_token_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    api_token_prefix: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FeedImportRun(Base):
    __tablename__ = "feed_import_runs"
    __table_args__ = (
        UniqueConstraint("feed_id", "idempotency_key", name="uq_feed_import_idempotency"),
        CheckConstraint("status IN ('preview', 'succeeded', 'partial', 'failed')", name="ck_feed_import_status"),
        CheckConstraint("total_rows >= 0 AND applied_rows >= 0 AND rejected_rows >= 0", name="ck_feed_import_counts_nonnegative"),
        Index("ix_feed_import_company_created", "company_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dealer_feeds.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    initiated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    payload_digest: Mapped[str] = mapped_column(String(64))
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="preview", index=True)
    source_filename: Mapped[str] = mapped_column(String(180), default="upload")
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    applied_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FeedImportRow(Base):
    __tablename__ = "feed_import_rows"
    __table_args__ = (
        UniqueConstraint("run_id", "row_number", name="uq_feed_import_run_row"),
        CheckConstraint("row_number > 0", name="ck_feed_import_row_number_positive"),
        CheckConstraint("status IN ('preview', 'draft', 'submitted', 'unchanged', 'rejected')", name="ck_feed_import_row_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feed_import_runs.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    dealer_external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="preview")
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_errors: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DealerExternalListingKey(Base):
    __tablename__ = "dealer_external_listing_keys"
    __table_args__ = (
        UniqueConstraint("feed_id", "dealer_external_id", name="uq_dealer_feed_external_id"),
        CheckConstraint("length(dealer_external_id) > 0", name="ck_dealer_external_id_nonempty"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dealer_feeds.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    dealer_external_id: Mapped[str] = mapped_column(String(120))
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), unique=True)
    last_applied_hash: Mapped[str] = mapped_column(String(64))
    source_fields: Mapped[list] = mapped_column(JSONB, default=list)
    last_applied_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_applied_listing_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    missing_snapshot_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    missing_listing_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    missing_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    missing_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserSession(Base):
    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogSource(Base):
    __tablename__ = "catalog_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    license: Mapped[str] = mapped_column(String(100))
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    query_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CatalogImport(Base):
    __tablename__ = "catalog_imports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    source_name: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    counts: Mapped[dict] = mapped_column(JSON)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("currency", "rate_date", name="uq_exchange_rate_currency_date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    currency: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[str] = mapped_column(String(10))
    official_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    scale: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(200))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CatalogMake(Base):
    __tablename__ = "catalog_makes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    name: Mapped[str] = mapped_column(String(180))
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class CatalogModel(Base):
    __tablename__ = "catalog_models"
    __table_args__ = (
        UniqueConstraint("make_id", "slug", name="uq_catalog_model_make_slug"),
        Index("ix_catalog_models_make_name", "make_id", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    make_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_makes.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(String(180))
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class CatalogGeneration(Base):
    __tablename__ = "catalog_generations"
    __table_args__ = (UniqueConstraint("model_id", "slug", name="uq_catalog_generation_model_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_models.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(160))
    name: Mapped[str] = mapped_column(Text)
    year_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class CatalogBodyType(Base):
    __tablename__ = "catalog_body_types"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class CatalogBodyVariant(Base):
    __tablename__ = "catalog_body_variants"
    __table_args__ = (UniqueConstraint("generation_id", "slug", name="uq_body_variant_generation_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    generation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_generations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(120))
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class CatalogModification(Base):
    __tablename__ = "catalog_modifications"
    __table_args__ = (UniqueConstraint("generation_id", "slug", name="uq_modification_generation_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    generation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("catalog_generations.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(140))
    name: Mapped[str] = mapped_column(String(180))
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class LocationRegion(Base):
    __tablename__ = "location_regions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class LocationCity(Base):
    __tablename__ = "location_cities"
    __table_args__ = (UniqueConstraint("region_id", "slug", name="uq_city_region_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location_regions.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(140))
    name: Mapped[str] = mapped_column(String(160))
    external_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("year IS NULL OR year >= 1886", name="ck_listing_year_min"),
        CheckConstraint("mileage_km IS NULL OR mileage_km >= 0", name="ck_listing_mileage_nonnegative"),
        CheckConstraint("price_amount IS NULL OR price_amount > 0", name="ck_listing_price_positive"),
        CheckConstraint("color IS NULL OR color IN ('black', 'white', 'gray', 'silver', 'red', 'blue', 'green', 'yellow', 'brown', 'beige', 'orange', 'purple', 'other')", name="ck_listing_color"),
        CheckConstraint("customs_status IS NULL OR customs_status IN ('cleared_rb', 'eaeu_import', 'uncleared', 'unknown')", name="ck_listing_customs_status"),
        CheckConstraint("technical_condition IS NULL OR technical_condition IN ('good', 'needs_repair', 'non_operational')", name="ck_listing_technical_condition"),
        CheckConstraint("body_condition IS NULL OR body_condition IN ('good', 'minor_damage', 'significant_damage', 'repaired')", name="ck_listing_body_condition"),
        CheckConstraint("category_code IN ('cars', 'trucks', 'buses', 'motorcycles', 'special_equipment', 'agricultural_equipment', 'trailers', 'watercraft', 'parts', 'wheels', 'tires')", name="ck_listing_category_code"),
        UniqueConstraint("id", "category_code", name="uq_listing_id_category_code"),
        Index("ix_listing_public_search", "status", "created_at", "id"),
        Index("ix_listing_make_model_year", "make_id", "model_id", "year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True)
    slug: Mapped[str] = mapped_column(String(240), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    category_code: Mapped[str] = mapped_column(String(32), default="cars", server_default="cars", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    submitted_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moderation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    make_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_makes.id", ondelete="SET NULL"), nullable=True, index=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_models.id", ondelete="SET NULL"), nullable=True, index=True)
    generation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_generations.id", ondelete="SET NULL"), nullable=True)
    body_type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_body_types.id", ondelete="SET NULL"), nullable=True)
    body_variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_body_variants.id", ondelete="SET NULL"), nullable=True)
    modification_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("catalog_modifications.id", ondelete="SET NULL"), nullable=True)
    make_name_snapshot: Mapped[str | None] = mapped_column(String(180), nullable=True)
    model_name_snapshot: Mapped[str | None] = mapped_column(String(180), nullable=True)
    generation_name_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_make: Mapped[str | None] = mapped_column(String(180), nullable=True)
    manual_model: Mapped[str | None] = mapped_column(String(180), nullable=True)
    title: Mapped[str] = mapped_column(String(240), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mileage_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fuel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transmission: Mapped[str | None] = mapped_column(String(20), nullable=True)
    drive: Mapped[str | None] = mapped_column(String(20), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(30), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customs_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    technical_condition: Mapped[str | None] = mapped_column(String(24), nullable=True)
    body_condition: Mapped[str | None] = mapped_column(String(24), nullable=True)
    exchange: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bargaining: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    credit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    leasing: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    equipment: Mapped[list[str] | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    call_hours: Mapped[str | None] = mapped_column(String(120), nullable=True)
    damaged: Mapped[bool] = mapped_column(Boolean, default=False)
    parts_only: Mapped[bool] = mapped_column(Boolean, default=False)
    engine_volume_l: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    power_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    vin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location_regions.id", ondelete="SET NULL"), nullable=True, index=True)
    city_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("location_cities.id", ondelete="SET NULL"), nullable=True, index=True)
    manual_city: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    category_details: Mapped["ListingCategoryDetails | None"] = relationship(
        back_populates="listing", uselist=False, cascade="all, delete-orphan"
    )


class ListingCategoryDetails(Base):
    __tablename__ = "listing_category_details"
    __table_args__ = (
        CheckConstraint("category_code IN ('cars', 'trucks', 'buses', 'motorcycles', 'special_equipment', 'agricultural_equipment', 'trailers', 'watercraft', 'parts', 'wheels', 'tires')", name="ck_listing_category_details_code"),
        ForeignKeyConstraint(
            ["listing_id", "category_code"],
            ["listings.id", "listings.category_code"],
            name="fk_listing_category_details_listing_category",
            ondelete="CASCADE",
        ),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    category_code: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), default=dict, nullable=False)
    listing: Mapped[Listing] = relationship(back_populates="category_details")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("buyer_id", "listing_id", name="uq_conversation_buyer_listing"),
        CheckConstraint("buyer_id <> seller_id", name="ck_conversation_distinct_participants"),
        Index("ix_conversations_buyer_last_message", "buyer_id", "last_message_at", "id"),
        Index("ix_conversations_seller_last_message", "seller_id", "last_message_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    buyer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    seller_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_message_sequence: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_conversation_message_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ConversationParticipantState(Base):
    __tablename__ = "conversation_participant_states"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant_state"),
        Index("ix_conversation_participant_states_user", "user_id", "conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_read_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversation_messages.id", ondelete="SET NULL"), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ListingPhoto(Base):
    __tablename__ = "listing_photos"
    __table_args__ = (UniqueConstraint("listing_id", "idempotency_key", name="uq_photo_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    storage_name: Mapped[str] = mapped_column(String(80), unique=True)
    original_name: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingViewEvent(Base):
    """A public listing detail view, stored without visitor identifiers."""

    __tablename__ = "listing_view_events"
    __table_args__ = (Index("ix_listing_view_events_listing_created", "listing_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ListingStatusEvent(Base):
    __tablename__ = "listing_status_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(20), default="user")
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    revision: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_favorite_user_listing"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedSearch(Base):
    __tablename__ = "saved_searches"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused')", name="ck_saved_search_status"),
        CheckConstraint(
            "notification_channel IS NULL OR notification_channel IN ('email', 'web')",
            name="ck_saved_search_notification_channel",
        ),
        CheckConstraint(
            "notification_frequency IN ('instant', 'daily', 'weekly')",
            name="ck_saved_search_notification_frequency",
        ),
        Index("ix_saved_searches_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    search_url: Mapped[str] = mapped_column(String(2048))
    filters: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notification_frequency: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NotificationOutbox(Base):
    """Durable delivery intent created from a published listing event.

    The row is the source of truth for delivery attempts.  A worker may safely
    retry the corresponding job because ``dedupe_key`` is unique and the
    in-app notification has a one-to-one constraint on ``outbox_id``.
    """

    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe"),
        CheckConstraint("channel IN ('web', 'email')", name="ck_notification_outbox_channel"),
        CheckConstraint(
            "status IN ('queued', 'running', 'delivered', 'failed', 'unsupported')",
            name="ck_notification_outbox_status",
        ),
        CheckConstraint(
            "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
            "(saved_search_id IS NULL AND conversation_id IS NOT NULL)",
            name="ck_notification_outbox_source",
        ),
        Index("ix_notification_outbox_claim", "status", "available_at", "created_at", "id"),
        Index("ix_notification_outbox_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    dedupe_key: Mapped[str] = mapped_column(String(300))
    saved_search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("saved_searches.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserNotification(Base):
    """An in-app notification materialised from a delivered outbox row."""

    __tablename__ = "user_notifications"
    __table_args__ = (
        UniqueConstraint("outbox_id", name="uq_user_notification_outbox"),
        CheckConstraint(
            "(saved_search_id IS NOT NULL AND conversation_id IS NULL) OR "
            "(saved_search_id IS NULL AND conversation_id IS NOT NULL)",
            name="ck_user_notification_source",
        ),
        Index("ix_user_notifications_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    outbox_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("notification_outbox.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    saved_search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("saved_searches.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True, index=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(2048))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    comment: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContactReveal(Base):
    __tablename__ = "contact_reveals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("actor_id", "scope", "key", name="uq_idempotency_actor_scope_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(80))
    key: Mapped[str] = mapped_column(String(120))
    resource_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer)


class SmsOtpChallenge(Base):
    __tablename__ = "sms_otp_challenges"
    __table_args__ = (
        CheckConstraint("purpose IN ('login', 'registration')", name="ck_sms_otp_purpose"),
        CheckConstraint("attempt_count >= 0", name="ck_sms_otp_attempt_count_nonnegative"),
        UniqueConstraint("phone_hash", "idempotency_key_hash", name="uq_sms_otp_phone_idempotency"),
        Index("ix_sms_otp_phone_created", "phone_hash", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    code_digest: Mapped[str] = mapped_column(String(64))
    idempotency_key_hash: Mapped[str] = mapped_column(String(64))
    registration_display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    registration_terms_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registration_privacy_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    delivery_suppressed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    delivery_failed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserConsent(Base):
    __tablename__ = "user_consents"
    __table_args__ = (
        CheckConstraint("document_type IN ('terms', 'privacy')", name="ck_user_consent_document_type"),
        UniqueConstraint("user_id", "document_type", "version", name="uq_user_consent_user_document_version"),
        Index("ix_user_consents_user_accepted", "user_id", "accepted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_type: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(80))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source: Mapped[str] = mapped_column(String(40), default="sms_registration", server_default="sms_registration")


class WorkerJob(Base):
    __tablename__ = "worker_jobs"
    __table_args__ = (
        UniqueConstraint("job_key", name="uq_worker_job_key"),
        Index("ix_worker_jobs_claim", "status", "run_after", "lease_until"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    job_key: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BillingTariff(Base):
    """Owner-approved price and duration for a commerce service."""

    __tablename__ = "billing_tariffs"
    __table_args__ = (
        CheckConstraint(
            "service_code IN ('bump', 'highlight', 'top', 'dealer_package')",
            name="ck_billing_tariff_service_code",
        ),
        CheckConstraint("amount > 0", name="ck_billing_tariff_amount_positive"),
        CheckConstraint("currency IN ('BYN', 'USD')", name="ck_billing_tariff_currency"),
        CheckConstraint("duration_days BETWEEN 1 AND 365", name="ck_billing_tariff_duration"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_billing_tariff_status"),
        CheckConstraint("revision >= 1", name="ck_billing_tariff_revision"),
        CheckConstraint(
            "listing_quota IS NULL OR (service_code = 'dealer_package' AND listing_quota BETWEEN 1 AND 10000)",
            name="ck_billing_tariff_listing_quota",
        ),
        UniqueConstraint("code", name="uq_billing_tariff_code"),
        Index("ix_billing_tariffs_available", "status", "service_code", "code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80))
    service_code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    duration_days: Mapped[int] = mapped_column(Integer)
    listing_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="disabled", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class BillingOrder(Base):
    """Immutable commercial snapshot; status changes only through verified callbacks."""

    __tablename__ = "billing_orders"
    __table_args__ = (
        CheckConstraint(
            "(service_code = 'dealer_package' AND company_id IS NOT NULL AND listing_id IS NULL) OR "
            "(service_code <> 'dealer_package' AND listing_id IS NOT NULL AND company_id IS NULL)",
            name="ck_billing_order_target",
        ),
        CheckConstraint("service_code IN ('bump', 'highlight', 'top', 'dealer_package')", name="ck_billing_order_service_code"),
        CheckConstraint("amount > 0", name="ck_billing_order_amount_positive"),
        CheckConstraint("currency IN ('BYN', 'USD')", name="ck_billing_order_currency"),
        CheckConstraint("duration_days BETWEEN 1 AND 365", name="ck_billing_order_duration"),
        CheckConstraint(
            "listing_quota IS NULL OR (service_code = 'dealer_package' AND listing_quota BETWEEN 1 AND 10000)",
            name="ck_billing_order_listing_quota",
        ),
        CheckConstraint("status IN ('pending', 'paid', 'failed', 'cancelled', 'expired')", name="ck_billing_order_status"),
        UniqueConstraint("user_id", "idempotency_key_digest", name="uq_billing_order_user_idempotency"),
        UniqueConstraint("provider", "provider_reference", name="uq_billing_order_provider_reference"),
        Index("ix_billing_orders_user_created", "user_id", "created_at", "id"),
        Index("ix_billing_orders_target_service_status", "listing_id", "company_id", "service_code", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id", ondelete="RESTRICT"), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True)
    tariff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_tariffs.id", ondelete="RESTRICT"), index=True)
    service_code: Mapped[str] = mapped_column(String(32))
    tariff_code: Mapped[str] = mapped_column(String(80))
    tariff_revision: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    duration_days: Mapped[int] = mapped_column(Integer)
    listing_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    idempotency_key_digest: Mapped[str] = mapped_column(String(64))
    request_digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_payment_attempt_number_positive"),
        CheckConstraint("amount > 0", name="ck_payment_attempt_amount_positive"),
        CheckConstraint("currency IN ('BYN', 'USD')", name="ck_payment_attempt_currency"),
        CheckConstraint("status IN ('pending', 'succeeded', 'failed', 'cancelled')", name="ck_payment_attempt_status"),
        UniqueConstraint("order_id", "attempt_number", name="uq_payment_attempt_order_number"),
        UniqueConstraint("provider", "provider_reference", name="uq_payment_attempt_provider_reference"),
        Index("ix_payment_attempt_order_created", "order_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_orders.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    provider: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PaymentCallbackEvent(Base):
    __tablename__ = "payment_callback_events"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_callback_amount_positive"),
        CheckConstraint("currency IN ('BYN', 'USD')", name="ck_payment_callback_currency"),
        CheckConstraint("payment_status IN ('succeeded', 'failed', 'cancelled')", name="ck_payment_callback_status"),
        CheckConstraint("outcome IN ('applied', 'ignored')", name="ck_payment_callback_outcome"),
        UniqueConstraint("provider", "provider_event_id", name="uq_payment_callback_provider_event"),
        Index("ix_payment_callback_order_received", "order_id", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40))
    provider_event_id: Mapped[str] = mapped_column(String(180))
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_orders.id", ondelete="RESTRICT"), index=True)
    provider_reference: Mapped[str] = mapped_column(String(180))
    event_type: Mapped[str] = mapped_column(String(80))
    payment_status: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(16))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingPromotion(Base):
    __tablename__ = "listing_promotions"
    __table_args__ = (
        CheckConstraint(
            "(service_code = 'dealer_package' AND company_id IS NOT NULL AND listing_id IS NULL) OR "
            "(service_code <> 'dealer_package' AND listing_id IS NOT NULL AND company_id IS NULL)",
            name="ck_listing_promotion_target",
        ),
        CheckConstraint("service_code IN ('bump', 'highlight', 'top', 'dealer_package')", name="ck_listing_promotion_service_code"),
        CheckConstraint("amount > 0", name="ck_listing_promotion_amount_positive"),
        CheckConstraint("currency IN ('BYN', 'USD')", name="ck_listing_promotion_currency"),
        CheckConstraint("duration_days BETWEEN 1 AND 365", name="ck_listing_promotion_duration"),
        CheckConstraint(
            "listing_quota IS NULL OR (service_code = 'dealer_package' AND listing_quota BETWEEN 1 AND 10000)",
            name="ck_listing_promotion_listing_quota",
        ),
        CheckConstraint("status IN ('active', 'expired', 'cancelled')", name="ck_listing_promotion_status"),
        UniqueConstraint("order_id", name="uq_listing_promotion_order"),
        Index("ix_listing_promotion_listing_window", "listing_id", "service_code", "status", "ends_at"),
        Index("ix_listing_promotion_company_window", "company_id", "service_code", "status", "ends_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("billing_orders.id", ondelete="RESTRICT"), index=True)
    listing_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("listings.id", ondelete="RESTRICT"), nullable=True, index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True, index=True)
    service_code: Mapped[str] = mapped_column(String(32))
    tariff_code: Mapped[str] = mapped_column(String(80))
    tariff_revision: Mapped[int] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    duration_days: Mapped[int] = mapped_column(Integer)
    listing_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@event.listens_for(BillingOrder, "before_update")
def _keep_billing_order_snapshot_immutable(_mapper, _connection, order: BillingOrder) -> None:
    state = inspect(order)
    snapshot_fields = (
        "user_id",
        "listing_id",
        "company_id",
        "tariff_id",
        "service_code",
        "tariff_code",
        "tariff_revision",
        "amount",
        "currency",
        "duration_days",
        "listing_quota",
        "provider",
        "idempotency_key_digest",
        "request_digest",
        "expires_at",
    )
    if any(state.attrs[field].history.has_changes() for field in snapshot_fields):
        raise ValueError("Billing order commercial snapshot fields are immutable")
    reference_history = state.attrs["provider_reference"].history
    if reference_history.has_changes() and any(value is not None for value in reference_history.deleted):
        raise ValueError("Billing order provider reference is immutable once assigned")


@event.listens_for(PaymentAttempt, "before_update")
def _keep_payment_attempt_snapshot_immutable(_mapper, _connection, attempt: PaymentAttempt) -> None:
    state = inspect(attempt)
    snapshot_fields = ("order_id", "attempt_number", "provider", "amount", "currency")
    if any(state.attrs[field].history.has_changes() for field in snapshot_fields):
        raise ValueError("Payment attempt snapshot fields are immutable")
    for field in ("provider_reference", "checkout_url"):
        history = state.attrs[field].history
        if history.has_changes() and any(value is not None for value in history.deleted):
            raise ValueError("Payment attempt provider fields are immutable once assigned")


@event.listens_for(ListingPromotion, "before_update")
def _keep_listing_promotion_snapshot_immutable(_mapper, _connection, promotion: ListingPromotion) -> None:
    state = inspect(promotion)
    snapshot_fields = (
        "order_id",
        "listing_id",
        "company_id",
        "service_code",
        "tariff_code",
        "tariff_revision",
        "amount",
        "currency",
        "duration_days",
        "listing_quota",
        "starts_at",
        "ends_at",
    )
    if any(state.attrs[field].history.has_changes() for field in snapshot_fields):
        raise ValueError("Promotion commercial snapshot fields are immutable")
