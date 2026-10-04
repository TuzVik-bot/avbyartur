from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ContentKind = Literal["notification_template", "seo_page", "legal_document", "article"]
ContentStatus = Literal["draft", "published"]
ArticleTopic = Literal["vehicle_selection", "inspection", "vin", "transaction", "credit_leasing", "tires_wheels"]


class ManagedContentChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict
    status: ContentStatus = "draft"
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)
    confirmation: Literal["UPDATE_CONTENT"]
    current_password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("reason")
    @classmethod
    def reason_nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("A non-empty reason is required")
        return value


class ManagedContentOut(BaseModel):
    id: UUID
    kind: ContentKind
    key: str
    payload: dict
    status: ContentStatus
    revision: int
    updated_at: datetime


class ManagedContentEnvelope(BaseModel):
    content: ManagedContentOut


class ManagedContentPublicEnvelope(ManagedContentEnvelope):
    indexable: bool = False


class ManagedContentListOut(BaseModel):
    items: list[ManagedContentOut]
    total: int
    page: int
    page_size: int


class ManagedContentVersionOut(BaseModel):
    revision: int
    payload: dict
    status: ContentStatus
    actor_id: UUID
    reason: str
    created_at: datetime


class ManagedContentVersionsOut(BaseModel):
    items: list[ManagedContentVersionOut]


class ManagedArticleSummaryOut(BaseModel):
    slug: str
    title: str
    summary: str
    topic: ArticleTopic
    published_at: date
    updated_at: datetime


class ManagedArticleListOut(BaseModel):
    items: list[ManagedArticleSummaryOut]
    total: int
    page: int
    page_size: int
