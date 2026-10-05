from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.api.catalog_schemas import CatalogItemsOut, CatalogModificationsOut, CategorySubtypesOut
from app.api.listings import _active_query
from app.category_search import SUBTYPE_FIELD
from app.db import get_db
from app.listing_categories import CategoryCode
from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    Listing,
    LocationCity,
    LocationRegion,
)
from app.services import catalog_item, catalog_modification_item

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def items(rows: list, **relations) -> dict:
    return {"items": [catalog_item(row, **relations.get(str(row.id), {})) for row in rows]}


@router.get("/catalog/makes", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def makes(db: Annotated[Session, Depends(get_db)], q: str | None = None, limit: Annotated[int, Query(ge=1, le=200)] = 200, category_code: CategoryCode = "cars") -> dict:
    if category_code != "cars":
        # Existing imported catalog data has car provenance only. Manual make
        # entry remains available until a licensed category catalog is added.
        return {"items": []}
    query = select(CatalogMake).order_by(CatalogMake.sort_order, CatalogMake.name).limit(limit)
    if q:
        term = f"%{q[:80]}%"
        query = query.where(CatalogMake.name.ilike(term) | CatalogMake.slug.ilike(term) | cast(CatalogMake.aliases, String).ilike(term))
    rows = db.scalars(query).all()
    if not rows:
        return {"items": []}
    # Same visibility rules as the public /listings search, so a count matches what its link shows.
    counts = dict(db.execute(
        _active_query().where(Listing.category_code == category_code, Listing.make_id.is_not(None))
        .with_only_columns(Listing.make_id, func.count(Listing.id)).group_by(Listing.make_id)
    ).all())
    payload = items(rows)
    for item, row in zip(payload["items"], rows):
        item["listing_count"] = int(counts.get(row.id, 0))
    return payload


@router.get("/catalog/models", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def models(db: Annotated[Session, Depends(get_db)], make_id: UUID | None = None, q: str | None = None, limit: Annotated[int, Query(ge=1, le=300)] = 300, category_code: CategoryCode = "cars") -> dict:
    if category_code != "cars":
        return {"items": []}
    query = select(CatalogModel).order_by(CatalogModel.name).limit(limit)
    if make_id:
        query = query.where(CatalogModel.make_id == make_id)
    if q:
        term = f"%{q[:80]}%"
        query = query.where(CatalogModel.name.ilike(term) | CatalogModel.slug.ilike(term) | cast(CatalogModel.aliases, String).ilike(term))
    rows = db.scalars(query).all()
    return items(rows, **{str(row.id): {"make_id": row.make_id} for row in rows})


@router.get("/catalog/category-subtypes", response_model=CategorySubtypesOut)
def category_subtypes(category_code: CategoryCode) -> dict:
    """Internal subtype codes; open text categories use manual entry."""
    coded = {
        "trucks": ("truck", "tractor_unit", "van", "other"),
        "buses": ("bus", "minibus", "coach", "other"),
        "motorcycles": ("motorcycle", "scooter", "atv", "snowmobile", "other"),
    }
    return {
        "category_code": category_code,
        "field": SUBTYPE_FIELD.get(category_code),
        "entry_mode": "codes" if category_code in coded else "manual" if category_code in SUBTYPE_FIELD else "none",
        "items": [{"code": code} for code in coded.get(category_code, ())],
    }


@router.get("/catalog/generations", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def generations(db: Annotated[Session, Depends(get_db)], model_id: UUID, limit: Annotated[int, Query(ge=1, le=300)] = 300) -> dict:
    query = select(CatalogGeneration).where(CatalogGeneration.model_id == model_id).order_by(CatalogGeneration.year_from, CatalogGeneration.name).limit(limit)
    rows = db.scalars(query).all()
    return items(rows, **{str(row.id): {"model_id": row.model_id} for row in rows})


@router.get("/catalog/body-types", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def body_types(db: Annotated[Session, Depends(get_db)]) -> dict:
    return items(db.scalars(select(CatalogBodyType).order_by(CatalogBodyType.name)).all())


@router.get("/catalog/body-variants", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def body_variants(db: Annotated[Session, Depends(get_db)], generation_id: UUID, limit: Annotated[int, Query(ge=1, le=200)] = 200) -> dict:
    rows = db.scalars(select(CatalogBodyVariant).where(CatalogBodyVariant.generation_id == generation_id).order_by(CatalogBodyVariant.name).limit(limit)).all()
    return items(rows)


@router.get("/catalog/modifications", response_model=CatalogModificationsOut, response_model_exclude_unset=True)
def modifications(db: Annotated[Session, Depends(get_db)], generation_id: UUID, limit: Annotated[int, Query(ge=1, le=300)] = 300) -> dict:
    rows = db.scalars(select(CatalogModification).where(CatalogModification.generation_id == generation_id).order_by(CatalogModification.name).limit(limit)).all()
    return {"items": [catalog_modification_item(row) for row in rows]}


@router.get("/locations/regions", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def regions(db: Annotated[Session, Depends(get_db)]) -> dict:
    return items(db.scalars(select(LocationRegion).order_by(LocationRegion.name)).all())


@router.get("/locations/cities", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def cities(db: Annotated[Session, Depends(get_db)], region_id: UUID, limit: Annotated[int, Query(ge=1, le=500)] = 500) -> dict:
    rows = db.scalars(select(LocationCity).where(LocationCity.region_id == region_id).order_by(LocationCity.name).limit(limit)).all()
    return items(rows)
