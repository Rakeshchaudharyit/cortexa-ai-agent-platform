"""Development/admin CLI: plan or apply recovery from a legacy PostgreSQL source.

Defaults to dry-run. Writes require explicit --apply.

Usage:
  python -m app.cli.migrate_legacy_database \\
    --source-url postgresql://cortexa@127.0.0.1:55432/cortexa \\
    --source-database cortexa \\
    --email user@example.com

  python -m app.cli.migrate_legacy_database ... --apply

Never prints complete password hashes or secrets. Refuses production unless
LEGACY_DB_MIGRATION_ALLOW_PRODUCTION=true is explicitly set.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import clear_settings_cache, get_settings
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.schemas.auth import normalize_email
from app.services.legacy_database_migration import (
    LegacyDatabaseMigrator,
    redact_database_url,
)


async def _run(
    *,
    source_url: str,
    source_database: str,
    email: str,
    apply: bool,
) -> int:
    clear_settings_cache()
    settings = get_settings()
    if settings.is_production and not settings.legacy_db_migration_allow_production:
        print(
            "Refusing to run: legacy DB migration is disabled in production "
            "(set LEGACY_DB_MIGRATION_ALLOW_PRODUCTION=true to override).",
            file=sys.stderr,
        )
        return 2

    normalized = normalize_email(email)
    init_engine(settings)
    factory = get_session_factory()
    try:
        async with factory() as session:
            migrator = LegacyDatabaseMigrator(settings, session)
            print(f"source_url (redacted): {redact_database_url(source_url)}")
            print(f"source_database: {source_database}")
            print(f"email (normalized): {normalized}")
            print(f"mode: {'APPLY' if apply else 'DRY-RUN (default)'}")
            report = await migrator.analyze(
                source_url=source_url,
                source_database=source_database,
                email=normalized,
            )
            if apply:
                if not report.safe_to_apply:
                    print(report.format())
                    print(
                        "\nApply aborted: dry-run was not safe. "
                        "Resolve conflicts/warnings first.",
                        file=sys.stderr,
                    )
                    return 1
                report = await migrator.apply(report, source_url=source_url)
            print(report.format())
            if apply and not report.applied:
                return 1
            if not apply and not report.safe_to_apply:
                return 0  # dry-run success even when not safe — report is the product
            return 0
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or recover a user from a legacy PostgreSQL database into "
            "the current Agent Platform database. Defaults to dry-run."
        ),
    )
    parser.add_argument(
        "--source-url",
        required=True,
        help="Source PostgreSQL URL (password optional if peer/trust auth)",
    )
    parser.add_argument(
        "--source-database",
        required=True,
        help="Source database name (e.g. cortexa)",
    )
    parser.add_argument("--email", required=True, help="Account email to recover")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply writes (default is dry-run only)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(
        _run(
            source_url=args.source_url,
            source_database=args.source_database,
            email=args.email,
            apply=args.apply,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
