"""Shared locking and safety rules for administrative API and CLI changes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


class AdminChangeRejected(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def lock_active_administrators(db: Session) -> list[User]:
    return list(db.scalars(
        select(User).where(User.role == "admin", User.status == "active")
        .order_by(User.id).with_for_update().execution_options(populate_existing=True)
    ).all())


def guard_administrative_change(
    active_administrators: list[User], actor: User, target: User,
    *, role: str, status: str,
) -> None:
    removing_admin = target.role == "admin" and target.status == "active" and (role != "admin" or status != "active")
    if removing_admin and len(active_administrators) <= 1:
        raise AdminChangeRejected("last_admin_protected", "Нельзя отключить последнего администратора")
    if target.id == actor.id and (role != "admin" or status != "active"):
        raise AdminChangeRejected("self_admin_protected", "Изменить ваши права может другой администратор")
