"""Shared, non-secret policy for listing submission validation and form hints."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.listing_categories import CATEGORY_CODES

MAXIMUM_LISTING_PHOTOS = 30


@dataclass(frozen=True)
class _Policy:
    current_year: int
    listing_year_min: int
    listing_future_new_years: int
    minimum_photos_new: int
    minimum_photos_used: int
    minimum_photos_damaged: int
    minimum_photos_parts: int

    @classmethod
    def from_settings(cls, settings: Any | None = None, *, current_year: int | None = None) -> "_Policy":
        settings = settings or get_settings()
        year = datetime.now(timezone.utc).year if current_year is None else current_year
        if type(year) is not int or not 1 <= year <= 9998:
            raise ValueError("current year is outside the supported range")

        listing_year_min = _bounded_int(settings, "listing_year_min", 1886, 2100)
        listing_future_new_years = _bounded_int(settings, "listing_future_new_years", 0, 1)
        if listing_year_min > year:
            raise ValueError("listing_year_min exceeds the current used-year maximum")
        minimum_photos_new = _bounded_int(settings, "minimum_photos_new", 1, MAXIMUM_LISTING_PHOTOS)
        minimum_photos_used = _bounded_int(settings, "minimum_photos_used", 1, MAXIMUM_LISTING_PHOTOS)
        minimum_photos_damaged = _bounded_int(settings, "minimum_photos_damaged", 1, MAXIMUM_LISTING_PHOTOS)
        minimum_photos_parts = _bounded_int(settings, "minimum_photos_parts", 1, MAXIMUM_LISTING_PHOTOS)

        return cls(
            current_year=year,
            listing_year_min=listing_year_min,
            listing_future_new_years=listing_future_new_years,
            minimum_photos_new=minimum_photos_new,
            minimum_photos_used=minimum_photos_used,
            minimum_photos_damaged=minimum_photos_damaged,
            minimum_photos_parts=minimum_photos_parts,
        )

    def maximum_year_for(self, listing: Any) -> int:
        return self.current_year + self.listing_future_new_years if listing.condition == "new" else self.current_year

    def minimum_photos_for(self, listing: Any) -> int:
        if bool(listing.parts_only):
            return self.minimum_photos_parts
        if bool(listing.damaged):
            return self.minimum_photos_damaged
        if listing.condition == "new":
            return self.minimum_photos_new
        return self.minimum_photos_used

    def public_dict(self) -> dict[str, Any]:
        return {
            "current_year": self.current_year,
            "listing_year_min": self.listing_year_min,
            "new_year_max": self.current_year + self.listing_future_new_years,
            "used_year_max": self.current_year,
            "minimum_photos": {
                "new": self.minimum_photos_new,
                "used": self.minimum_photos_used,
                "damaged": self.minimum_photos_damaged,
                "parts": self.minimum_photos_parts,
            },
            "maximum_photos": MAXIMUM_LISTING_PHOTOS,
            "category_codes": list(CATEGORY_CODES),
        }


def _bounded_int(settings: Any, name: str, minimum: int, maximum: int) -> int:
    value = getattr(settings, name, None)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} is outside the supported range")
    return value


def listing_validation_policy(*, settings: Any | None = None, current_year: int | None = None) -> dict[str, Any]:
    """Return the public policy consumed by the seller form."""

    return _Policy.from_settings(settings, current_year=current_year).public_dict()


def minimum_required_photos(listing: Any, *, settings: Any | None = None) -> int:
    """Return the configured photo minimum, applying exceptional types first."""

    return _Policy.from_settings(settings).minimum_photos_for(listing)


def maximum_listing_year(
    listing: Any,
    *,
    settings: Any | None = None,
    current_year: int | None = None,
) -> int:
    """Return the upper year limit for a listing's declared condition."""

    return _Policy.from_settings(settings, current_year=current_year).maximum_year_for(listing)


def is_listing_year_allowed(
    year: int | None,
    listing: Any,
    *,
    settings: Any | None = None,
    current_year: int | None = None,
) -> bool:
    """Check an exact integer year against the configured inclusive bounds."""

    policy = _Policy.from_settings(settings, current_year=current_year)
    return (
        type(year) is int
        and policy.listing_year_min <= year <= policy.maximum_year_for(listing)
    )
