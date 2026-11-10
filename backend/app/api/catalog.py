from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app.api.catalog_schemas import CatalogItemsOut, CatalogModificationsOut
from app.db import get_db
from app.listing_schemas import canonical_catalog_ids
from app.models import (
    CatalogBodyType,
    CatalogBodyVariant,
    CatalogGeneration,
    CatalogMake,
    CatalogModel,
    CatalogModification,
    LocationCity,
    LocationRegion,
)
from app.listing_categories import CategoryCode
from app.services import (
    LIKE_ESCAPE,
    catalog_item,
    catalog_modification_item,
    contains_pattern,
    fail,
)

# Catalog and location references change rarely; let browsers and proxies
# reuse them briefly instead of re-querying on every page render.
REFERENCE_CACHE_CONTROL = "public, max-age=300"
CATALOG_SEARCH_MAX_LENGTH = 80


def _cache_reference_response(response: Response) -> None:
    response.headers["Cache-Control"] = REFERENCE_CACHE_CONTROL


router = APIRouter(
    prefix="/api/v1",
    tags=["catalog"],
    dependencies=[Depends(_cache_reference_response)],
)


def items(rows: list, **relations) -> dict:
    return {"items": [catalog_item(row, **relations.get(str(row.id), {})) for row in rows]}


@router.get("/catalog/makes", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def makes(
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
    category_code: CategoryCode | None = None,
) -> dict:
    query = select(CatalogMake).order_by(CatalogMake.sort_order, CatalogMake.name).limit(limit)
    if category_code is not None:
        categorized_make_ids = select(CatalogModel.make_id).where(
            CatalogModel.source_metadata.contains({"category_codes": [category_code]})
        )
        query = query.where(CatalogMake.id.in_(categorized_make_ids))
    if q:
        term = contains_pattern(q, CATALOG_SEARCH_MAX_LENGTH)
        query = query.where(or_(*(
            column.ilike(term, escape=LIKE_ESCAPE)
            for column in (CatalogMake.name, CatalogMake.slug, cast(CatalogMake.aliases, String))
        )))
    return items(db.scalars(query).all())


@router.get("/catalog/models", response_model=CatalogItemsOut, response_model_exclude_unset=True)
def models(
    db: Annotated[Session, Depends(get_db)],
    make_id: UUID | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=300)] = 300,
    category_code: CategoryCode | None = None,
    model_ids: str | None = None,
) -> dict:
    query = select(CatalogModel).order_by(CatalogModel.name).limit(limit)
    if model_ids is not None:
        try:
            selected_ids = [UUID(item) for item in canonical_catalog_ids(model_ids).split(",")]
        except ValueError:
            fail(422, "validation_error", "Invalid catalog model IDs", {"model_ids": "Expected 1 to 50 comma-separated UUIDs"})
        query = query.where(CatalogModel.id.in_(selected_ids))
    if category_code is not None:
        query = query.where(CatalogModel.source_metadata.contains({"category_codes": [category_code]}))
    if make_id:
        query = query.where(CatalogModel.make_id == make_id)
    if q:
        term = contains_pattern(q, CATALOG_SEARCH_MAX_LENGTH)
        query = query.where(or_(*(
            column.ilike(term, escape=LIKE_ESCAPE)
            for column in (CatalogModel.name, CatalogModel.slug, cast(CatalogModel.aliases, String))
        )))
    rows = db.scalars(query).all()
    return items(rows, **{str(row.id): {"make_id": row.make_id} for row in rows})


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
