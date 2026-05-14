from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class DbResult(Generic[T]):
    """
    Generic database/service result returned to the API layer.

    success=False means an operation failed because of validation, database, or
    infrastructure errors. success=True with data=None can simply mean "not found".
    """

    success: bool
    data: T | None = None
    error: str | None = None

    @classmethod
    def ok(cls, data: T | None = None) -> "DbResult[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, error: str) -> "DbResult[T]":
        return cls(success=False, data=None, error=error)


@dataclass(frozen=True)
class AuthResult:
    """
    Authentication result.

    The API layer can use this to decide whether to create a session/cookie/token.
    This module intentionally does not create sessions by itself.
    """

    authenticated: bool
    user_id: int | None = None
    email: str | None = None


__all__ = ["AuthResult", "DbResult"]
