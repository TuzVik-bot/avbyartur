#!/usr/bin/env python3
"""Import used-car listings from ab.onliner.by (автобарахолка Onlíner).

Operates under the operator's written permission from Onliner (October 2026):
ten used cars per manufacturer, all Belarusian cities, with photos,
descriptions, and seller contacts.  The source API is only reachable from
Belarusian IP addresses, so run ``collect``/``sync`` on the VPS (or through
a tunnel); ``import`` additionally downloads photos from the source CDN.

Subcommands::

    collect  – fetch fresh used cars per manufacturer into a JSONL snapshot
    import   – publish a snapshot as active listings (idempotent by slug)
    sync     – refresh existing mirror listings, then import new adverts
    refresh  – only refresh existing mirror listings (prices, closures)

Typical use inside the API container on the VPS::

    python scripts/import_onliner_listings.py collect \
        --output data/onliner_snapshot_20261024.jsonl
    python scripts/import_onliner_listings.py import \
        --snapshot data/onliner_snapshot_20261024.jsonl --owner-email admin@example.invalid
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# A checkout keeps the package under backend/; the runtime image places app/
# and scripts/ side by side in /app.
if (ROOT / "app").is_dir():
    sys.path.insert(0, str(ROOT))
else:
    sys.path.insert(0, str(ROOT / "backend"))


def _owner(db, owner_email: str | None, owner_id: uuid.UUID | None):
    from app.models import User
    from sqlalchemy import select

    if owner_id is not None:
        owner = db.get(User, owner_id)
    elif owner_email:
        owner = db.scalar(
            select(User).where(User.email == owner_email.strip().casefold())
        )
    else:
        owner = None
    if owner is None or owner.status != "active":
        raise LookupError(
            "owner must be an existing active user (use --owner-email or --owner-id)"
        )
    return owner


def _company(db, owner, unp: str | None):
    from app.models import Company
    from sqlalchemy import select

    if not unp:
        return None
    company = db.scalar(select(Company).where(Company.unp == unp.strip()))
    if company is None or company.status != "approved":
        raise LookupError(f"company with UNP {unp!r} not found or not approved")
    return company


def _client_factory():
    from app.ingest_onliner import OnlinerClient

    return OnlinerClient()


def _add_owner_args(parser: argparse.ArgumentParser) -> None:
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument("--owner-email")
    owner.add_argument("--owner-id", type=uuid.UUID)


def _command_collect(args: argparse.Namespace) -> int:
    from app.ingest_onliner import OnlinerFetchError, collect_snapshot

    try:
        client = _client_factory()
        with client:
            report = collect_snapshot(
                client,
                args.output,
                per_make_limit=args.per_make,
                manufacturers=args.manufacturers,
            )
    except OnlinerFetchError as exc:
        print(f"collect failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def _command_import(args: argparse.Namespace) -> int:
    from app.db import SessionLocal
    from app.ingest_onliner import OnlinerFetchError, import_snapshot

    if not args.snapshot.is_file():
        print(f"snapshot not found: {args.snapshot}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        owner = _owner(db, args.owner_email, args.owner_id)
        company = _company(db, owner, args.company_unp)
        client = None
        if not args.no_photos:
            client = _client_factory()
        try:
            report = import_snapshot(
                db,
                args.snapshot,
                owner,
                company_id=company.id if company else None,
                client=client,
                max_photos=args.max_photos,
                limit=args.limit,
                dry_run=args.dry_run,
            )
        except OnlinerFetchError as exc:
            print(f"import failed: {exc}", file=sys.stderr)
            return 2
        finally:
            if client is not None:
                client.close()
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def _command_sync(args: argparse.Namespace, *, include_discovery: bool) -> int:
    from app.db import SessionLocal
    from app.ingest_onliner import (
        OnlinerFetchError,
        discover_new,
        sync_existing,
    )

    with SessionLocal() as db:
        owner = _owner(db, args.owner_email, args.owner_id)
        client = _client_factory()
        report: dict = {}
        try:
            with client:
                report["refresh"] = sync_existing(db, client)
                db.commit()
                if include_discovery:
                    report["discover"] = discover_new(
                        db,
                        client,
                        owner,
                        per_make_limit=args.per_make,
                        manufacturers=args.manufacturers,
                        max_photos=args.max_photos,
                    )
                    db.commit()
        except OnlinerFetchError as exc:
            print(f"sync failed: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    collect_p = sub.add_parser(
        "collect", help="collect a JSONL snapshot from the source API"
    )
    collect_p.add_argument("--output", type=Path, required=True)
    collect_p.add_argument("--per-make", type=int, default=10)
    collect_p.add_argument("--manufacturers", default="all", help="all, top, or top:N")
    collect_p.add_argument(
        "--no-photos", action="store_true", help="unused for collect; kept for symmetry"
    )
    collect_p.set_defaults(handler=_command_collect)

    import_p = sub.add_parser("import", help="import a collected snapshot")
    import_p.add_argument("--snapshot", type=Path, required=True)
    _add_owner_args(import_p)
    import_p.add_argument(
        "--company-unp", help="attach listings to an approved company by UNP"
    )
    import_p.add_argument("--max-photos", type=int, default=30)
    import_p.add_argument("--limit", type=int)
    import_p.add_argument("--dry-run", action="store_true")
    import_p.add_argument(
        "--no-photos", action="store_true", help="skip photo download (metadata only)"
    )
    import_p.set_defaults(handler=_command_import)

    sync_p = sub.add_parser(
        "sync", help="refresh existing mirror listings and import new adverts"
    )
    _add_owner_args(sync_p)
    sync_p.add_argument("--per-make", type=int, default=10)
    sync_p.add_argument("--manufacturers", default="all")
    sync_p.add_argument("--max-photos", type=int, default=30)
    sync_p.set_defaults(
        handler=lambda args: _command_sync(args, include_discovery=True)
    )

    refresh_p = sub.add_parser("refresh", help="only refresh existing mirror listings")
    _add_owner_args(refresh_p)
    refresh_p.add_argument("--per-make", type=int, default=10)
    refresh_p.add_argument("--manufacturers", default="all")
    refresh_p.add_argument("--max-photos", type=int, default=30)
    refresh_p.set_defaults(
        handler=lambda args: _command_sync(args, include_discovery=False)
    )

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (OSError, ValueError, LookupError, json.JSONDecodeError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
