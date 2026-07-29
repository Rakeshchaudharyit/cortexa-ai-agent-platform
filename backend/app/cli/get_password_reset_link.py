"""Development-only CLI: print the latest password-reset link for an email.

Usage:
  python -m app.cli.get_password_reset_link --email user@example.com

Retrieves the URL stored by a prior forgot-password request (Redis development
sink). Refuses to run in production. Never prints passwords.
Deletes the Redis value after successful retrieval.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import clear_settings_cache, get_settings
from app.notifications.password_reset import create_password_reset_delivery
from app.providers.redis import close_redis, init_redis
from app.schemas.auth import normalize_email


async def _run(email: str) -> int:
    clear_settings_cache()
    settings = get_settings()
    if settings.is_production or settings.app_env == "production":
        print(
            "Refusing to run: password-reset link CLI is disabled in production.",
            file=sys.stderr,
        )
        return 2
    if settings.app_env not in {"development", "test"}:
        print(
            f"Refusing to run: APP_ENV={settings.app_env!r} is not development/test.",
            file=sys.stderr,
        )
        return 2

    normalized = normalize_email(email)
    redis = await init_redis(settings)
    delivery = create_password_reset_delivery(settings, redis=redis)

    try:
        url = await delivery.consume_latest_reset_url(normalized)
    except Exception:
        print(
            "No reset link available. If an account exists, request forgot-password first.",
            file=sys.stderr,
        )
        await close_redis()
        return 1

    if not url:
        print(
            "No reset link available. If an account exists, request forgot-password first.",
            file=sys.stderr,
        )
        await close_redis()
        return 1

    print(url)
    await close_redis()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Print a development password-reset URL for an email "
            "(retrieves Redis delivery sink; no real email sent)."
        ),
    )
    parser.add_argument("--email", required=True, help="Account email address")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.email))


if __name__ == "__main__":
    raise SystemExit(main())
