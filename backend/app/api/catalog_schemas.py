from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas import CatalogItemOut
from app.listing_categories import CategoryCode


class CatalogItemsOut(BaseModel):
    items: list[CatalogItemOut]


class CategorySubtypeItemOut(BaseModel):
    code: str


class CategorySubtypesOut(BaseModel):
    category_code: CategoryCode
    field: str | None
    entry_mode: Literal["codes", "manual", "none"]
    items: list[CategorySubtypeItemOut]


class CatalogModificationSourceOut(BaseModel):
    name: Literal["Drom"]
    id: str | None
    url: str | None


class CatalogModificationSpecsOut(BaseModel):
    engine_code: str | None
    frame_code: str | None
    engine_l: float | None
    power_hp: int | None
    fuel: str | None
    transmission: str | None
    drive: str | None
    production_period_raw: str | None
    summary_raw: str | None


class CatalogModificationOut(BaseModel):
    id: UUID
    slug: str
    name: str
    aliases: list[str]
    source: CatalogModificationSourceOut | None = None
    specs: CatalogModificationSpecsOut | None = None


class CatalogModificationsOut(BaseModel):
    items: list[CatalogModificationOut]
