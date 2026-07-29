"""Development/admin CLI: set a user password securely via getpass.

Usage:
  python -m app.cli.reset_password --email user@example.com

Never accepts the password as a CLI argument. Never prints password or hash.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from app.core.config import clear_settings_cache, get_settings
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.notifications.password_reset import create_password_reset_delivery
from app.providers.redis import close_redis, init_redis
from app.schemas.auth import normalize_email
from app.security.passwords import PasswordValidationError
from app.services.password_reset import PasswordResetService


async def _run(email: str, new_password: str) -> int:
    clear_settings_cache()
    settings = get_settings()
    if settings.is_production:
        print("Refusing to run: reset_password CLI is disabled in production.", file=sys.stderr)
        return 2

    normalized = normalize_email(email)
    init_engine(settings)
    redis = await init_redis(settings)
    delivery = create_password_reset_delivery(settings, redis=redis)
    service = PasswordResetService.from_settings(settings, delivery=delivery, redis=redis)

    factory = get_session_factory()
    try:
        async with factory() as session:
            await service.admin_set_password(
                session,
                email=normalized,
                new_password=new_password,
            )
    except LookupError:
        print("No account found for that email.", file=sys.stderr)
        await close_redis()
        await dispose_engine()
        return 1
    except PasswordValidationError as exc:
        print(str(exc.message), file=sys.stderr)
        await close_redis()
        await dispose_engine()
        return 1

    print("Password updated. All refresh sessions and reset tokens were revoked.")
    await close_redis()
    await dispose_engine()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set a user password (development/admin). Prompts twice via getpass.",
    )
    parser.add_argument("--email", required=True, help="Account email address")
    args = parser.parse_args(argv)

    first = getpass.getpass("New password: ")
    second = getpass.getpass("Confirm new password: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    return asyncio.run(_run(args.email, first))


if __name__ == "__main__":
    raise SystemExit(main())
