"""Versioned edits to public catalog labels with immutable record identity."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

CatalogKind = Literal["makes", "models", "generations", "body-types", "body-variants", "modifications", "regions", "cities"]


class AdminCatalogSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str | None = None
    canonical_url: str | None = None
    license_url: str | None = None
    permission_reference: str | None = None
    query_url: str | None = None
    checksum: str | None = None
    retrieved_at: str | None = None


class AdminCatalogSnapshotOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    aliases: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    source: AdminCatalogSourceOut | None = None


class AdminCatalogItemOut(BaseModel):
    id: UUID
    kind: CatalogKind
    name: str
    slug: str
    aliases: list[str]
    parent_id: UUID | None
    year_from: int | None
    year_to: int | None
    source_name: str | None
    source: AdminCatalogSourceOut | None
    manual_override: bool
    revision: int


class AdminCatalogListOut(BaseModel):
    items: list[AdminCatalogItemOut]
    total: int
    page: int
    page_size: int


class AdminCatalogChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=1024)
    aliases: list[str] | None = Field(default=None, max_length=40)
    year_from: int | None = Field(default=None, ge=1886, le=2100)
    year_to: int | None = Field(default=None, ge=1886, le=2100)
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["UPDATE_CATALOG"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("name", "reason")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A non-empty value is required")
        return value

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        result = []
        for item in value:
            cleaned = item.strip()
            if not cleaned or len(cleaned) > 180:
                raise ValueError("Aliases must contain between 1 and 180 characters")
            if cleaned not in result:
                result.append(cleaned)
        return result

    @model_validator(mode="after")
    def ordered_years(self):
        if self.year_from is not None and self.year_to is not None and self.year_from > self.year_to:
            raise ValueError("The end year must not precede the start year")
        return self


class AdminCatalogChangeOut(BaseModel):
    item: AdminCatalogItemOut
    changed: bool


class AdminCatalogVersionOut(BaseModel):
    id: UUID
    revision: int
    actor_id: UUID
    reason: str
    before: AdminCatalogSnapshotOut
    after: AdminCatalogSnapshotOut
    source: AdminCatalogSourceOut | None
    valid: bool
    created_at: datetime


class AdminCatalogVersionListOut(BaseModel):
    items: list[AdminCatalogVersionOut]
    total: int
    page: int
    page_size: int
