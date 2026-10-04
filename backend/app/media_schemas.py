from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

PhotoStatus = Literal["processing", "ready", "failed"]


class PhotoUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: PhotoStatus
    url: str


class ListingPhotoStatusOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: PhotoStatus
    position: int
    is_cover: bool
    url: str | None


class ListingPhotoStatusesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ListingPhotoStatusOut]


class PhotoMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]
