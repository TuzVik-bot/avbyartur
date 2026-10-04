"""Public validation constraints for the listing form, without runtime secrets."""

from pydantic import BaseModel, ConfigDict, Field


class MinimumListingPhotosOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new: int = Field(ge=1, le=30)
    used: int = Field(ge=1, le=30)
    damaged: int = Field(ge=1, le=30)
    parts: int = Field(ge=1, le=30)


class ListingValidationPolicyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_year: int
    listing_year_min: int
    new_year_max: int
    used_year_max: int
    minimum_photos: MinimumListingPhotosOut
    maximum_photos: int = Field(ge=1, le=30)
    category_codes: list[str] = Field(min_length=1)
