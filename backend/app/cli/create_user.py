"""Development/admin CLI: create a local user or reset an existing password.

Usage:
  python -m app.cli.create_user \\
    --email user@example.com \\
    --name "User Name" \\
    --role admin

  python -m app.cli.create_user \\
    --email user@example.com \\
    --reset-password

Never accepts the password as a CLI argument. Never prints password or hash.
Creating users refuses production unless ADMIN_USER_CLI_ALLOW_PRODUCTION=true.
Password reset via this CLI always refuses production (use reset_password CLI
policy: no production override). Prefer `python -m app.cli.reset_password` for
password-only updates.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import clear_settings_cache, get_settings
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.models.enums import UserRole, UserStatus
from app.models.user import User
from app.schemas.auth import normalize_email
from app.security.passwords import PasswordService, PasswordValidationError
from app.services.password_reset import PasswordResetService


def _prompt_password() -> str | None:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        return None
    return first


def _refuse_production_create(settings: object) -> int | None:
    is_production = bool(getattr(settings, "is_production", False))
    allow = bool(getattr(settings, "admin_user_cli_allow_production", False))
    if is_production and not allow:
        print(
            "Refusing to run: create_user CLI is disabled in production "
            "(set ADMIN_USER_CLI_ALLOW_PRODUCTION=true to override).",
            file=sys.stderr,
        )
        return 2
    return None


def _refuse_production_reset(settings: object) -> int | None:
    """Password reset never allows a production override (matches reset_password CLI)."""
    if bool(getattr(settings, "is_production", False)):
        print(
            "Refusing to run: password reset via create_user is disabled in production. "
            "Use a non-production environment or a controlled ops process.",
            file=sys.stderr,
        )
        return 2
    return None


async def create_user(
    *,
    email: str,
    full_name: str,
    role: UserRole,
    password: str,
) -> int:
    """Create a new local user. Caller owns engine lifecycle."""
    clear_settings_cache()
    settings = get_settings()
    refused = _refuse_production_create(settings)
    if refused is not None:
        return refused

    normalized = normalize_email(email)
    name = full_name.strip()
    if not name:
        print("Name cannot be blank.", file=sys.stderr)
        return 1

    passwords = PasswordService.from_settings(settings)
    try:
        password_hash = passwords.hash_password(password)
    except PasswordValidationError as exc:
        print(str(exc.message), file=sys.stderr)
        return 1

    init_engine(settings)
    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == normalized))
        ).scalar_one_or_none()
        if existing is not None:
            print(
                "Account already exists for that email. "
                "Use --reset-password to update the password only "
                "(role and status are not changed).",
                file=sys.stderr,
            )
            return 1

        now = datetime.now(UTC)
        user = User(
            email=normalized,
            password_hash=password_hash,
            full_name=name,
            role=role,
            status=UserStatus.active,
            is_email_verified=False,
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            print(
                "Account already exists for that email. "
                "Use --reset-password to update the password only "
                "(role and status are not changed).",
                file=sys.stderr,
            )
            return 1

        await session.refresh(user)
        print(
            f"Created user id={user.id} email={user.email} "
            f"role={user.role.value} status={user.status.value}"
        )
        return 0


async def reset_existing_password(*, email: str, password: str) -> int:
    """Reset password for an existing user. Never changes role or status."""
    clear_settings_cache()
    settings = get_settings()
    refused = _refuse_production_reset(settings)
    if refused is not None:
        return refused

    normalized = normalize_email(email)
    init_engine(settings)
    # admin_set_password only touches PostgreSQL; delivery/redis unused here.
    service = PasswordResetService.from_settings(settings)

    factory = get_session_factory()
    async with factory() as session:
        existing = (
            await session.execute(select(User).where(User.email == normalized))
        ).scalar_one_or_none()
        if existing is None:
            print("No account found for that email.", file=sys.stderr)
            return 1
        prior_role = existing.role
        prior_status = existing.status
        try:
            user = await service.admin_set_password(
                session,
                email=normalized,
                new_password=password,
            )
        except PasswordValidationError as exc:
            print(str(exc.message), file=sys.stderr)
            return 1
        if user.role != prior_role or user.status != prior_status:
            print(
                "Refusing to continue: role or status changed unexpectedly.",
                file=sys.stderr,
            )
            return 1
        print(
            f"Password updated for id={user.id} email={user.email} "
            f"role={user.role.value} status={user.status.value}. "
            "Refresh sessions and reset tokens were revoked."
        )
        return 0


# Back-compat aliases for tests / internal callers
_create_user = create_user
_reset_password = reset_existing_password


async def _run_create(
    *,
    email: str,
    full_name: str,
    role: UserRole,
    password: str,
) -> int:
    try:
        return await create_user(
            email=email,
            full_name=full_name,
            role=role,
            password=password,
        )
    finally:
        await dispose_engine()


async def _run_reset(*, email: str, password: str) -> int:
    try:
        return await reset_existing_password(email=email, password=password)
    finally:
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a local development user, or reset an existing user's password. "
            "Prompts twice via getpass. Never accepts the password as a CLI argument."
        ),
    )
    parser.add_argument("--email", required=True, help="Account email address")
    parser.add_argument("--name", default=None, help="Full name (required when creating)")
    parser.add_argument(
        "--role",
        default=None,
        choices=[role.value for role in UserRole],
        help="Role for a new user (required when creating). Not used with --reset-password.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help=(
            "Reset password for an existing user only. "
            "Does not create accounts and never changes role or status. "
            "Always refuses production (no override). Prefer app.cli.reset_password."
        ),
    )
    args = parser.parse_args(argv)

    clear_settings_cache()
    settings = get_settings()

    if args.reset_password:
        refused = _refuse_production_reset(settings)
        if refused is not None:
            return refused
        if args.name is not None or args.role is not None:
            print(
                "With --reset-password, do not pass --name or --role "
                "(role and status are never changed).",
                file=sys.stderr,
            )
            return 1
        password = _prompt_password()
        if password is None:
            return 1
        return asyncio.run(_run_reset(email=args.email, password=password))

    refused = _refuse_production_create(settings)
    if refused is not None:
        return refused

    if not args.name or not args.role:
        print("Creating a user requires --name and --role.", file=sys.stderr)
        return 1

    password = _prompt_password()
    if password is None:
        return 1
    return asyncio.run(
        _run_create(
            email=args.email,
            full_name=args.name,
            role=UserRole(args.role),
            password=password,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
