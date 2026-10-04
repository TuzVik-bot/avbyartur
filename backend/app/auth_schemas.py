from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    is_current: bool


class UserSessionListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UserSessionOut]


class UserSessionRevokedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]


class UserSessionsRevokedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revoked_count: int
