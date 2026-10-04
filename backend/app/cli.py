import argparse
import getpass
import json
import re
import sys
import uuid
from pathlib import Path

from sqlalchemy import func, select, update

from app.catalog_import import CatalogInputError, import_catalog
from app.admin_service import guard_administrative_change, lock_active_administrators
from app.config import get_settings
from app.db import SessionLocal
from app.drom_import import DromInputError, import_drom_csv
from app.models import AuditEvent, User, UserSession
from app.security import hash_password, normalize_email


def create_user(args: argparse.Namespace) -> int:
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("Password: ")
    if len(password) < 12:
        print("Password must be at least 12 characters", file=sys.stderr)
        return 2
    email = normalize_email(args.email)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("Invalid email", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            print("Account already exists", file=sys.stderr)
            return 2
        user = User(email=email, display_name=args.display_name.strip(), password_hash=hash_password(password), role=args.role, status="active")
        db.add(user)
        db.commit()
        print(json.dumps({"id": str(user.id), "email": user.email, "display_name": user.display_name, "role": user.role}))
    return 0


def validate_user_status_change(status: str, reason: str) -> str:
    if status not in {"active", "blocked"}:
        raise ValueError("Status must be active or blocked")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("A non-empty reason is required")
    return normalized_reason


def change_user_status(db, user_id: uuid.UUID, status: str, actor_id: uuid.UUID, reason: str) -> dict:
    active_admins = lock_active_administrators(db)
    actor = next((user for user in active_admins if user.id == actor_id), None)
    if actor is None or actor.role != "admin" or actor.status != "active":
        raise PermissionError("Actor must be an active admin")

    user = db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))
    if user is None:
        raise LookupError("User not found")
    if user.status == status:
        return {"user_id": str(user.id), "status": user.status, "changed": False}

    guard_administrative_change(active_admins, actor, user, role=user.role, status=status)

    user.status = status
    if status == "blocked":
        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
    db.add(
        AuditEvent(
            actor_id=actor.id,
            entity_type="user",
            entity_id=user.id,
            action="blocked" if status == "blocked" else "unblocked",
            details={"reason": reason},
        )
    )
    db.commit()
    return {"user_id": str(user.id), "status": user.status, "changed": True}


def set_user_status(args: argparse.Namespace) -> int:
    try:
        reason = validate_user_status_change(args.status, args.reason)
        with SessionLocal() as db:
            result = change_user_status(db, args.user_id, args.status, args.actor_id, reason)
        print(json.dumps(result))
        return 0
    except (ValueError, PermissionError, LookupError) as exc:
        print(f"User status change failed: {exc}", file=sys.stderr)
        return 2


def main() -> int:
    parser = argparse.ArgumentParser(prog="avtorinok-admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    user_parser = subparsers.add_parser("create-user", help="Create a closed-pilot account")
    user_parser.add_argument("--email", required=True)
    user_parser.add_argument("--display-name", required=True)
    user_parser.add_argument("--role", choices=("user", "moderator", "admin"), default="user")
    user_parser.add_argument("--password-stdin", action="store_true")
    status_parser = subparsers.add_parser("set-user-status", help="Block or reactivate a pilot account")
    status_parser.add_argument("--user-id", required=True, type=uuid.UUID)
    status_parser.add_argument("--status", required=True, choices=("active", "blocked"))
    status_parser.add_argument("--actor-id", required=True, type=uuid.UUID)
    status_parser.add_argument("--reason", required=True)
    catalog_parser = subparsers.add_parser("import-catalog", help="Validate and atomically import catalog.json")
    catalog_parser.add_argument("--path", default=str(get_settings().catalog_path))
    catalog_parser.add_argument("--dry-run", action="store_true")
    drom_parser = subparsers.add_parser("import-drom", help="Inspect or import a Drom catalog CSV")
    drom_parser.add_argument("--path", required=True)
    drom_parser.add_argument("--apply", action="store_true", help="Apply the import; default is a read-only dry run")
    args = parser.parse_args()
    if args.command == "create-user":
        return create_user(args)
    if args.command == "set-user-status":
        return set_user_status(args)
    if args.command == "import-catalog":
        try:
            with SessionLocal() as db:
                result = import_catalog(db, Path(args.path), dry_run=args.dry_run)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except (CatalogInputError, OSError, json.JSONDecodeError) as exc:
            print(f"Catalog import failed: {exc}", file=sys.stderr)
            return 2
    if args.command == "import-drom":
        try:
            with SessionLocal() as db:
                result = import_drom_csv(db, Path(args.path), dry_run=not args.apply)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except (DromInputError, OSError, UnicodeDecodeError) as exc:
            print(f"Drom import failed: {exc}", file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
