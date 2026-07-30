"""Unit tests for legacy database migration planning helpers."""

from __future__ import annotations

from app.services.legacy_database_migration import (
    LegacyDatabaseMigrator,
    SourceSchemaProfile,
    _is_argon2_compatible,
    redact_database_url,
)


def test_redact_database_url_strips_password() -> None:
    redacted = redact_database_url("postgresql://cortexa:super-secret@127.0.0.1:5432/cortexa")
    assert "super-secret" not in redacted
    assert "cortexa:***@" in redacted


def test_argon2_incompatible_non_argon_hashes() -> None:
    assert not _is_argon2_compatible("plaintext")
    assert not _is_argon2_compatible("$2b$12$notargon2atall")


def test_detect_saas_vs_agent_profile() -> None:
    helper = LegacyDatabaseMigrator.__new__(LegacyDatabaseMigrator)
    saas = helper._detect_profile(
        ["users", "tenants", "projects", "memberships"],
        {"email", "normalized_email", "password_hash"},
    )
    assert saas == SourceSchemaProfile.multi_tenant_saas

    agent = helper._detect_profile(
        ["users", "documents", "conversations"],
        {
            "id",
            "email",
            "password_hash",
            "full_name",
            "role",
            "status",
        },
    )
    assert agent == SourceSchemaProfile.agent_platform


def test_incompatible_hash_recovery_does_not_use_guessable_password() -> None:
    """Apply path must hash a discarded random secret, never a user-id-derived string."""
    import inspect

    import app.services.legacy_database_migration as mod

    source = inspect.getsource(mod.LegacyDatabaseMigrator)
    assert "legacy-recovery-require-reset-" not in source
    assert "secrets.token_urlsafe" in source
