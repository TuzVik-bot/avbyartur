from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PhotoBadge = Literal["verified", "free_history", "best_price"]
PHOTO_BADGE_ORDER: tuple[PhotoBadge, ...] = ("verified", "free_history", "best_price")


class ListingPhotoBadgesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    photo_badges: list[PhotoBadge] = Field(max_length=len(PHOTO_BADGE_ORDER))

    @field_validator("photo_badges")
    @classmethod
    def unique_badges(cls, values: list[PhotoBadge]) -> list[PhotoBadge]:
        if len(set(values)) != len(values):
            raise ValueError("Each photo badge may occur only once")
        return [badge for badge in PHOTO_BADGE_ORDER if badge in values]
