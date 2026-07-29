"""Password hashing and policy tests."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.security.passwords import PasswordService, PasswordValidationError


@pytest.fixture
def passwords(settings: Settings) -> PasswordService:
    return PasswordService.from_settings(settings)


def test_hash_and_verify_password(passwords: PasswordService) -> None:
    raw = "StrongDemoPassword123!"
    digest = passwords.hash_password(raw)
    assert digest != raw
    assert digest.startswith("$argon2")
    assert passwords.verify_password(raw, digest) is True


def test_incorrect_password_rejected(passwords: PasswordService) -> None:
    digest = passwords.hash_password("StrongDemoPassword123!")
    assert passwords.verify_password("WrongPassword!!!", digest) is False


def test_password_minimum_length(passwords: PasswordService) -> None:
    with pytest.raises(PasswordValidationError):
        passwords.hash_password("short")


def test_password_maximum_length(passwords: PasswordService) -> None:
    too_long = "x" * (passwords.max_length + 1)
    with pytest.raises(PasswordValidationError):
        passwords.hash_password(too_long)


def test_blank_password_rejected(passwords: PasswordService) -> None:
    with pytest.raises(PasswordValidationError):
        passwords.hash_password("   ")


def test_passphrase_allowed(passwords: PasswordService) -> None:
    phrase = "correct horse battery staple"
    digest = passwords.hash_password(phrase)
    assert passwords.verify_password(phrase, digest) is True
