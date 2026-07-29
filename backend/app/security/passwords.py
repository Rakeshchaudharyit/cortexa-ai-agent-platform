"""Password hashing service (Argon2id)."""

from __future__ import annotations

from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import AppError


class PasswordValidationError(AppError):
    """Raised when a password fails policy checks before hashing."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="validation_error",
            message=message,
            status_code=422,
        )


@dataclass(frozen=True)
class PasswordService:
    """Replaceable Argon2id password hasher with policy validation."""

    hasher: PasswordHasher
    min_length: int
    max_length: int

    @classmethod
    def from_settings(cls, settings: Settings) -> PasswordService:
        # Development/test use lighter parameters; production stays memory-hard.
        if settings.app_env in {"development", "test"}:
            hasher = PasswordHasher(
                time_cost=2,
                memory_cost=19_456,
                parallelism=1,
                hash_len=32,
                salt_len=16,
            )
        else:
            hasher = PasswordHasher(
                time_cost=3,
                memory_cost=65_536,
                parallelism=2,
                hash_len=32,
                salt_len=16,
            )
        return cls(
            hasher=hasher,
            min_length=settings.password_min_length,
            max_length=settings.password_max_length,
        )

    def validate_password(self, password: str) -> None:
        if password is None or not password.strip():
            raise PasswordValidationError("Password cannot be blank")
        # Reject whitespace-only; allow passphrases with spaces otherwise.
        if len(password) < self.min_length:
            raise PasswordValidationError(f"Password must be at least {self.min_length} characters")
        if len(password) > self.max_length:
            raise PasswordValidationError(f"Password must be at most {self.max_length} characters")

    def hash_password(self, password: str) -> str:
        self.validate_password(password)
        return self.hasher.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return self.hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
