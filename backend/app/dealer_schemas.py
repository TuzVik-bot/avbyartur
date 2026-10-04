from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


TeamRole = Literal["owner", "admin", "seller", "viewer"]
MemberRole = Literal["admin", "seller", "viewer"]
MemberStatus = Literal["active", "revoked"]


class DealerTeamMemberOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str | None
    display_name: str
    role: TeamRole
    status: MemberStatus
    revision: int
    created_at: datetime


class DealerTeamListOut(BaseModel):
    items: list[DealerTeamMemberOut]


class DealerTeamCreate(BaseModel):
    user_id: UUID
    role: MemberRole


class DealerTeamPatch(BaseModel):
    expected_revision: int = Field(ge=1)
    role: MemberRole | None = None
    status: MemberStatus | None = None

    @model_validator(mode="after")
    def has_changes(self):
        if self.role is None and self.status is None:
            raise ValueError("At least one of role or status is required")
        return self


class DealerTeamMutationOut(BaseModel):
    member: DealerTeamMemberOut


class DealerAnalyticsPeriodOut(BaseModel):
    start: str | None
    end: str | None


class DealerAnalyticsTotalsOut(BaseModel):
    listings: int
    active_listings: int
    contact_reveals: int
    chats: int
    views: int


class DealerAnalyticsItemOut(BaseModel):
    listing_id: UUID
    title: str
    status: str
    contact_reveals: int
    chats: int
    views: int


class DealerAnalyticsOut(BaseModel):
    period: DealerAnalyticsPeriodOut
    totals: DealerAnalyticsTotalsOut
    items: list[DealerAnalyticsItemOut]
