"""CLI entry point for federation maintenance (the Docker / bouy realization).

Usage:
    python -m app.federation prune   # archive over-SLA leaves, then trim the live log

The AWS realization is an EventBridge-scheduled Lambda; both drivers call the same
:func:`app.federation.retention.prune_to_horizon`, so the prune logic is identical
across environments (Principle XV).
"""

from __future__ import annotations

import argparse
import sys

import structlog

logger = structlog.get_logger(__name__)


def _session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings

    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return sessionmaker(bind=create_engine(url))()


def _prune() -> int:
    from app.core.config import settings
    from app.federation.retention import prune_to_horizon, resolve_archive_backend

    backend = resolve_archive_backend()
    if backend is None:
        # Refuse to prune without an archive tier — trimming the live window without
        # archiving the leaves first would destroy tree state (§6.2g). Fail loudly.
        logger.error(
            "federation_prune_no_archive_backend",
            hint="set FEDERATION_ARCHIVE_PATH (file) or FEDERATION_ARCHIVE_S3_BUCKET (s3)",
        )
        print(
            "refusing to prune: no archive tier configured (set FEDERATION_ARCHIVE_PATH"
            " or FEDERATION_ARCHIVE_S3_BUCKET) — trimming without archiving destroys"
            " tree state",
            file=sys.stderr,
        )
        return 1

    session = _session()
    try:
        result = prune_to_horizon(
            session,
            backend=backend,
            retention_days=settings.FEDERATION_RETENTION_DAYS,
        )
    finally:
        session.close()
    print(
        f"pruned: archived {result.archived_count} leaves, "
        f"retention_horizon_sequence={result.retention_horizon_sequence}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Federation maintenance commands")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser(
        "prune",
        help="Archive over-SLA leaves to the archive tier, then trim the live log window",
    )
    args = parser.parse_args()
    if args.command == "prune":
        return _prune()
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
