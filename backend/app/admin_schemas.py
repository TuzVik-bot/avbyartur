"""Bounded administrative contracts without credential fields."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

UserRole = Literal["user", "moderator", "admin"]
UserStatus = Literal["active", "blocked"]


class AdminUserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: str | None
    display_name: str
    role: UserRole
    status: str
    created_at: datetime


class AdminUserListOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class AdminUserChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole
    status: UserStatus
    expected_role: UserRole
    expected_status: str = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["UPDATE_USER"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A non-empty reason is required")
        return value


class AdminUserChangeOut(BaseModel):
    user: AdminUserOut
    changed: bool


class TariffAuditSnapshotOut(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str = Field(min_length=1, max_length=80)
    service_code: Literal["bump", "highlight", "top", "dealer_package"]
    name: str = Field(min_length=1, max_length=120)
    amount: str = Field(pattern=r"^\d{1,10}\.\d{2}$")
    currency: Literal["BYN", "USD"]
    duration_days: int = Field(ge=1, le=3650)
    listing_quota: int | None = Field(default=None, ge=1, le=10000)
    status: Literal["active", "disabled"]


class AdminAuditEventOut(BaseModel):
    id: UUID
    actor_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    details: dict[str, str | int | bool | None | TariffAuditSnapshotOut]
    created_at: datetime


class AdminAuditListOut(BaseModel):
    items: list[AdminAuditEventOut]
    total: int
    page: int
    page_size: int


class AdminOperationsOut(BaseModel):
    users_by_status: dict[str, int]
    listings_by_status: dict[str, int]
    jobs_by_status: dict[str, int]
    capabilities: dict[str, bool]
