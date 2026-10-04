"""Administrator-only management of owner-defined, immutable-order tariffs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.admin_tariff_schemas import (
    AdminTariffChangeOut,
    AdminTariffCreateInput,
    AdminTariffDeleteInput,
    AdminTariffDeleteOut,
    AdminTariffListOut,
    AdminTariffUpdateInput,
)
from app.admin_tariff_service import create_tariff, delete_tariff, list_tariffs, update_tariff
from app.api.dependencies import require_csrf
from app.api.moderation import require_admin
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/api/v1/admin/tariffs", tags=["administration"])


@router.get("", response_model=AdminTariffListOut)
def admin_tariff_list(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict:
    del admin
    response.headers["Cache-Control"] = "no-store"
    return list_tariffs(db, page=page, page_size=page_size)


@router.post("", response_model=AdminTariffChangeOut, status_code=status.HTTP_201_CREATED)
def admin_tariff_create(
    payload: AdminTariffCreateInput,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    del _csrf
    response.headers["Cache-Control"] = "no-store"
    return {"tariff": create_tariff(db, admin, payload), "changed": True}


@router.patch("/{tariff_id}", response_model=AdminTariffChangeOut)
def admin_tariff_update(
    tariff_id: Annotated[UUID, Path()],
    payload: AdminTariffUpdateInput,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    del _csrf
    response.headers["Cache-Control"] = "no-store"
    tariff, changed = update_tariff(db, admin, tariff_id, payload)
    return {"tariff": tariff, "changed": changed}


@router.delete("/{tariff_id}", response_model=AdminTariffDeleteOut)
def admin_tariff_delete(
    tariff_id: Annotated[UUID, Path()],
    payload: AdminTariffDeleteInput,
    admin: Annotated[User, Depends(require_admin)],
    _csrf: Annotated[object, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> dict:
    del _csrf
    response.headers["Cache-Control"] = "no-store"
    delete_tariff(db, admin, tariff_id, payload)
    return {"deleted": True}
