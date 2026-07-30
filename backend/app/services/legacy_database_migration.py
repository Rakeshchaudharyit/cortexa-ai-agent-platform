"""Controlled legacy-database recovery planning and apply helpers.

Defaults to analysis/dry-run. Never prints complete password hashes or secrets.
Never migrates refresh sessions or password-reset tokens.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from argon2.exceptions import InvalidHashError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import normalize_email
from app.security.passwords import PasswordService

logger = logging.getLogger("cortexa.legacy_db_migration")

_AGENT_USER_COLUMNS = frozenset({"id", "email", "password_hash", "full_name", "role", "status"})
_SAAS_MARKER_TABLES = frozenset({"tenants", "projects", "memberships"})
_AGENT_MARKER_TABLES = frozenset({"documents", "conversations", "document_chunks"})


class SourceSchemaProfile(StrEnum):
    agent_platform = "agent_platform"
    multi_tenant_saas = "multi_tenant_saas"
    unknown = "unknown"


@dataclass
class LegacyMigrationReport:
    """Human-readable dry-run / apply summary (no secrets)."""

    source_database: str
    source_schema_profile: SourceSchemaProfile
    alembic_revision: str | None
    source_tables: list[str] = field(default_factory=list)
    original_user_found: bool = False
    source_user_id: str | None = None
    source_email_normalized: str | None = None
    source_created_at: str | None = None
    source_active: bool | None = None
    password_hash_prefix: str | None = None
    password_hash_length: int | None = None
    password_hash_compatible: bool | None = None
    destination_user_exists: bool = False
    destination_user_id: str | None = None
    uuid_conflict: bool = False
    related_data_counts: dict[str, int] = field(default_factory=dict)
    proposed_mappings: list[str] = field(default_factory=list)
    proposed_inserts: list[str] = field(default_factory=list)
    proposed_skips: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    safe_to_apply: bool = False
    applied: bool = False
    require_password_reset: bool = False

    def format(self) -> str:
        lines = [
            "=== Legacy database migration report ===",
            f"source_database: {self.source_database}",
            f"source_schema_profile: {self.source_schema_profile.value}",
            f"alembic_revision: {self.alembic_revision or '(none)'}",
            f"source_tables: {', '.join(self.source_tables) or '(none)'}",
            f"original_user_found: {'yes' if self.original_user_found else 'no'}",
            f"source_user_id: {self.source_user_id or '(n/a)'}",
            f"source_email_normalized: {self.source_email_normalized or '(n/a)'}",
            f"source_created_at: {self.source_created_at or '(n/a)'}",
            f"source_active: {self.source_active}",
            f"password_hash_prefix: {self.password_hash_prefix or '(n/a)'}",
            f"password_hash_length: {self.password_hash_length}",
            f"password_hash_compatible: {self.password_hash_compatible}",
            f"destination_user_exists: {self.destination_user_exists}",
            f"destination_user_id: {self.destination_user_id or '(n/a)'}",
            f"uuid_conflict: {self.uuid_conflict}",
            f"require_password_reset: {self.require_password_reset}",
            f"safe_to_apply: {self.safe_to_apply}",
            f"applied: {self.applied}",
            "related_data_counts:",
        ]
        if self.related_data_counts:
            for name, count in sorted(self.related_data_counts.items()):
                lines.append(f"  - {name}: {count}")
        else:
            lines.append("  (none)")
        for label, items in (
            ("proposed_mappings", self.proposed_mappings),
            ("proposed_inserts", self.proposed_inserts),
            ("proposed_skips", self.proposed_skips),
            ("conflicts", self.conflicts),
            ("warnings", self.warnings),
        ):
            lines.append(f"{label}:")
            if items:
                lines.extend(f"  - {item}" for item in items)
            else:
                lines.append("  (none)")
        return "\n".join(lines)


def redact_database_url(url: str) -> str:
    """Strip credentials from a database URL for logging."""
    parsed = urlparse(url)
    if parsed.password is None and "@" not in (parsed.netloc or ""):
        return url
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or ""
    netloc = f"{user}:***@{host}{port}" if user else f"{host}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def _to_async_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    return url


def _hash_prefix(password_hash: str, length: int = 15) -> str:
    return password_hash[:length] if password_hash else ""


def _is_argon2_compatible(password_hash: str) -> bool:
    if not re.match(r"^\$argon2(id|i|d)\$v=\d+\$", password_hash):
        return False
    try:
        from argon2 import PasswordHasher

        # Parse-only validation — never verify against a real password here.
        PasswordHasher().check_needs_rehash(password_hash)
        return True
    except (InvalidHashError, ValueError, TypeError):
        return False


class LegacyDatabaseMigrator:
    """Inspect a source database and optionally recover a user into destination."""

    def __init__(self, settings: Settings, destination_session: AsyncSession) -> None:
        self.settings = settings
        self.destination = destination_session
        self.passwords = PasswordService.from_settings(settings)

    async def analyze(
        self,
        *,
        source_url: str,
        source_database: str,
        email: str,
    ) -> LegacyMigrationReport:
        normalized = normalize_email(email)
        async_url = _to_async_url(source_url)
        # Ensure path targets the requested database name when provided.
        parsed = urlparse(async_url)
        path = f"/{source_database}" if source_database else parsed.path
        async_url = urlunparse(
            (parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment)
        )

        engine = create_async_engine(async_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                tables = await self._list_tables(connection)
                columns = await self._user_columns(connection) if "users" in tables else set()
                profile = self._detect_profile(tables, columns)
                revision = await self._alembic_revision(connection)
                report = LegacyMigrationReport(
                    source_database=source_database,
                    source_schema_profile=profile,
                    alembic_revision=revision,
                    source_tables=tables,
                )
                report.proposed_skips.extend(
                    [
                        "refresh_sessions / refresh_tokens (never migrated)",
                        "password_reset_tokens (never migrated)",
                    ]
                )

                if profile != SourceSchemaProfile.agent_platform:
                    report.warnings.append(
                        "Source schema is not the Cortexa AI Agent Platform schema."
                    )
                    report.conflicts.append(
                        "Refusing automatic recovery from incompatible product schema."
                    )
                    if profile == SourceSchemaProfile.multi_tenant_saas:
                        report.warnings.append(
                            "Source looks like a multi-tenant SaaS database "
                            "(tenants/projects/memberships)."
                        )
                    await self._load_user_any_schema(connection, report, normalized, profile)
                    report.safe_to_apply = False
                    return report

                await self._analyze_agent_user(connection, report, normalized)
                return report
        finally:
            await engine.dispose()

    async def apply(self, report: LegacyMigrationReport, source_url: str) -> LegacyMigrationReport:
        if not report.safe_to_apply:
            report.conflicts.append("Apply refused: dry-run was not marked safe_to_apply.")
            return report
        if report.destination_user_exists:
            report.proposed_skips.append("destination user already exists — no insert")
            report.applied = False
            return report

        # Re-read source user and insert atomically into destination.
        async_url = _to_async_url(source_url)
        parsed = urlparse(async_url)
        path = f"/{report.source_database}"
        async_url = urlunparse(
            (parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment)
        )
        engine = create_async_engine(async_url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                row = await self._fetch_agent_user(connection, report.source_email_normalized or "")
                if row is None:
                    report.conflicts.append("Source user disappeared before apply.")
                    report.safe_to_apply = False
                    return report
                user = User(
                    id=UUID(str(row["id"])),
                    email=str(row["email"]),
                    password_hash=str(row["password_hash"]),
                    full_name=str(row["full_name"]),
                    role=UserRole(str(row["role"])),
                    status=UserStatus(str(row["status"])),
                    is_email_verified=bool(row["is_email_verified"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    last_login_at=row.get("last_login_at"),
                )
                if report.require_password_reset:
                    # Unusable placeholder: random secret is hashed then discarded so
                    # the password cannot be derived from the user id or any report field.
                    discarded = secrets.token_urlsafe(48)
                    user.password_hash = self.passwords.hash_password(discarded)
                    del discarded
                    report.warnings.append(
                        "Password hash was incompatible; temporary unusable hash set — "
                        "user must reset password (CLI or forgot-password) before login."
                    )

                self.destination.add(user)
                await self.destination.flush()

                # Related agent data (documents/conversations/…) only when counts allow
                # and tables are compatible — currently user-only if related counts are 0.
                for category, count in report.related_data_counts.items():
                    if count > 0:
                        report.conflicts.append(
                            f"Related data category '{category}' has {count} rows; "
                            "automatic related-data migration is not applied in this "
                            "recovery path. Stop and map manually."
                        )
                        await self.destination.rollback()
                        report.applied = False
                        report.safe_to_apply = False
                        return report

                # Revoke any destination sessions for this user (none expected for new user).
                await self.destination.execute(
                    text("DELETE FROM refresh_sessions WHERE user_id = :uid"),
                    {"uid": str(user.id)},
                )
                await self.destination.execute(
                    text("DELETE FROM password_reset_tokens WHERE user_id = :uid"),
                    {"uid": str(user.id)},
                )
                await self.destination.commit()
                report.applied = True
                report.destination_user_id = str(user.id)
                report.destination_user_exists = True
                return report
        finally:
            await engine.dispose()

    async def _list_tables(self, connection: Any) -> list[str]:
        result = await connection.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY 1
                """
            )
        )
        return [row[0] for row in result.fetchall()]

    def _detect_profile(
        self,
        tables: list[str],
        columns: set[str],
    ) -> SourceSchemaProfile:
        table_set = set(tables)
        if _SAAS_MARKER_TABLES & table_set:
            return SourceSchemaProfile.multi_tenant_saas
        if "users" not in table_set:
            return SourceSchemaProfile.unknown
        if _AGENT_USER_COLUMNS <= columns:
            return SourceSchemaProfile.agent_platform
        if _AGENT_MARKER_TABLES & table_set:
            return SourceSchemaProfile.agent_platform
        return SourceSchemaProfile.unknown

    async def _alembic_revision(self, connection: Any) -> str | None:
        exists = await connection.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema = 'public' AND table_name = 'alembic_version'
                )
                """
            )
        )
        if not bool(exists.scalar_one()):
            return None
        result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
        return str(row[0]) if row else None

    async def _user_columns(self, connection: Any) -> set[str]:
        result = await connection.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'users'
                """
            )
        )
        return {row[0] for row in result.fetchall()}

    async def _load_user_any_schema(
        self,
        connection: Any,
        report: LegacyMigrationReport,
        normalized: str,
        profile: SourceSchemaProfile,
    ) -> None:
        columns = await self._user_columns(connection)
        if "email" not in columns and "normalized_email" not in columns:
            report.warnings.append("users table missing email columns")
            return

        if "normalized_email" in columns:
            result = await connection.execute(
                text(
                    """
                    SELECT id, email, full_name, password_hash, is_active,
                           created_at, updated_at
                    FROM users
                    WHERE normalized_email = :email
                    """
                ),
                {"email": normalized},
            )
        else:
            result = await connection.execute(
                text(
                    """
                    SELECT id, email, full_name, password_hash,
                           created_at, updated_at
                    FROM users
                    WHERE lower(trim(email)) = :email
                    """
                ),
                {"email": normalized},
            )
        row = result.mappings().first()
        if row is None:
            report.proposed_skips.append("source user not found for email")
            return

        report.original_user_found = True
        report.source_user_id = str(row["id"])
        report.source_email_normalized = normalize_email(str(row["email"]))
        report.source_created_at = str(row["created_at"])
        report.source_active = bool(row["is_active"]) if "is_active" in row else None
        password_hash = str(row["password_hash"])
        report.password_hash_prefix = _hash_prefix(password_hash)
        report.password_hash_length = len(password_hash)
        report.password_hash_compatible = _is_argon2_compatible(password_hash)
        report.proposed_mappings.append(
            f"Would map SaaS/legacy user fields → Agent Platform User "
            f"(profile={profile.value}) — blocked without compatible agent schema"
        )
        await self._count_related_generic(connection, report, str(row["id"]), profile)
        await self._check_destination(report, UUID(str(row["id"])), normalized)

    async def _analyze_agent_user(
        self,
        connection: Any,
        report: LegacyMigrationReport,
        normalized: str,
    ) -> None:
        columns = await self._user_columns(connection)
        if not _AGENT_USER_COLUMNS <= columns:
            report.source_schema_profile = SourceSchemaProfile.unknown
            report.conflicts.append(
                "users table missing required Agent Platform columns " f"(have={sorted(columns)})"
            )
            report.safe_to_apply = False
            return

        # Refine profile now that columns are confirmed.
        report.source_schema_profile = SourceSchemaProfile.agent_platform
        row = await self._fetch_agent_user(connection, normalized)
        if row is None:
            report.proposed_skips.append("source user not found for email")
            report.safe_to_apply = False
            return

        report.original_user_found = True
        report.source_user_id = str(row["id"])
        report.source_email_normalized = normalize_email(str(row["email"]))
        report.source_created_at = str(row["created_at"])
        report.source_active = str(row["status"]) == UserStatus.active.value
        password_hash = str(row["password_hash"])
        report.password_hash_prefix = _hash_prefix(password_hash)
        report.password_hash_length = len(password_hash)
        report.password_hash_compatible = _is_argon2_compatible(password_hash)
        report.require_password_reset = not bool(report.password_hash_compatible)

        report.proposed_mappings.append(
            "users.id, email, full_name, role, status, timestamps → destination users"
        )
        if report.password_hash_compatible:
            report.proposed_mappings.append("preserve Argon2 password_hash")
            report.proposed_inserts.append("users row with preserved password hash")
        else:
            report.proposed_mappings.append(
                "password_hash incompatible — create user requiring password reset"
            )
            report.proposed_inserts.append("users row with temporary hash + require reset")

        await self._count_related_agent(connection, report, str(row["id"]))
        await self._check_destination(report, UUID(str(row["id"])), normalized)

        if report.conflicts:
            report.safe_to_apply = False
            return
        if report.destination_user_exists:
            report.proposed_skips.append("email already exists in destination — no duplicate")
            report.safe_to_apply = False
            return
        if any(count > 0 for count in report.related_data_counts.values()):
            report.warnings.append(
                "Related agent data exists; this CLI migrates the user account only when "
                "related counts are zero. Stop for manual mapping if data must move."
            )
            report.safe_to_apply = False
            report.conflicts.append("Related data present — refusing automatic apply")
            return

        report.safe_to_apply = True

    async def _fetch_agent_user(
        self,
        connection: Any,
        normalized: str,
    ) -> dict[str, Any] | None:
        result = await connection.execute(
            text(
                """
                SELECT id, email, password_hash, full_name, role::text AS role,
                       status::text AS status, is_email_verified,
                       last_login_at, created_at, updated_at
                FROM users
                WHERE lower(trim(email)) = :email
                """
            ),
            {"email": normalized},
        )
        row = result.mappings().first()
        return dict(row) if row is not None else None

    async def _count_related_agent(
        self,
        connection: Any,
        report: LegacyMigrationReport,
        user_id: str,
    ) -> None:
        for table in (
            "documents",
            "document_chunks",
            "conversations",
            "messages",
            "message_citations",
            "refresh_sessions",
            "password_reset_tokens",
        ):
            if table not in report.source_tables:
                continue
            if table in {"refresh_sessions", "password_reset_tokens"}:
                result = await connection.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"),
                    {"uid": user_id},
                )
                count = int(result.scalar_one())
                report.related_data_counts[table] = count
                report.proposed_skips.append(f"{table}: {count} row(s) will not be migrated")
                continue
            result = await connection.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"),
                {"uid": user_id},
            )
            report.related_data_counts[table] = int(result.scalar_one())

    async def _count_related_generic(
        self,
        connection: Any,
        report: LegacyMigrationReport,
        user_id: str,
        profile: SourceSchemaProfile,
    ) -> None:
        if profile != SourceSchemaProfile.multi_tenant_saas:
            return
        for table, column in (
            ("memberships", "user_id"),
            ("projects", "created_by_user_id"),
            ("refresh_tokens", "user_id"),
            ("background_jobs", "requested_by_user_id"),
        ):
            if table not in report.source_tables:
                continue
            result = await connection.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :uid"),
                {"uid": user_id},
            )
            count = int(result.scalar_one())
            report.related_data_counts[table] = count
            report.proposed_skips.append(
                f"{table}: {count} row(s) not migratable into Agent Platform"
            )

    async def _check_destination(
        self,
        report: LegacyMigrationReport,
        source_id: UUID,
        normalized: str,
    ) -> None:
        by_email = await self.destination.execute(
            text("SELECT id, email FROM users WHERE lower(trim(email)) = :email"),
            {"email": normalized},
        )
        email_row = by_email.first()
        if email_row is not None:
            report.destination_user_exists = True
            report.destination_user_id = str(email_row[0])
            if UUID(str(email_row[0])) != source_id:
                report.warnings.append("Destination email exists with a different user id")

        by_id = await self.destination.execute(
            text("SELECT id, email FROM users WHERE id = :uid"),
            {"uid": str(source_id)},
        )
        id_row = by_id.first()
        if id_row is not None and normalize_email(str(id_row[1])) != normalized:
            report.uuid_conflict = True
            report.conflicts.append(
                "Source user UUID already belongs to a different destination email"
            )
