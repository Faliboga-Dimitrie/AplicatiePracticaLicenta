from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .models import (
    AuthSessionRecord,
    MriCaseRecord,
    SubjectAccessRecord,
    SubjectRecord,
    UserCredentialsRecord,
    UserRecord,
)


UNSET = object()
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def quote_identifier(identifier: str) -> str:
    """Validate an SQL identifier before using it in a DDL string."""
    if not _IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return identifier


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(email))


def normalize_required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    return normalized


def normalize_date(value: str | date | object) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value.strip())
    raise ValueError(f"Invalid date value: {value!r}")


def date_from_db(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Unsupported database date value: {value!r}")


def auth_session_from_row(row: dict[str, Any]) -> AuthSessionRecord:
    return AuthSessionRecord(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        refresh_token_hash=str(row["refresh_token_hash"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        revoked_at=row.get("revoked_at"),
        last_used_at=row.get("last_used_at"),
    )


def user_from_row(row: dict[str, Any]) -> UserRecord:
    return UserRecord(id=int(row["id"]), email=str(row["email"]))


def user_credentials_from_row(row: dict[str, Any]) -> UserCredentialsRecord:
    return UserCredentialsRecord(
        id=int(row["id"]),
        email=str(row["email"]),
        password_hash=str(row["password_hash"]),
    )


def subject_from_row(row: dict[str, Any]) -> SubjectRecord:
    return SubjectRecord(
        id=str(row["id"]),
        name=row.get("name"),
        age=row.get("age"),
        notes=row.get("notes"),
    )


def mri_case_from_row(row: dict[str, Any], *, workspace: Any | None = None) -> MriCaseRecord:
    return MriCaseRecord(
        id=int(row["id"]),
        subject_id=str(row["subject_id"]),
        acquisition_date=date_from_db(row["acquisition_date"]),
        notes=row.get("notes"),
        status=row.get("status"),
        workspace=workspace,
    )


def access_from_row(row: dict[str, Any]) -> SubjectAccessRecord:
    return SubjectAccessRecord(
        user_id=int(row["user_id"]),
        subject_id=str(row["subject_id"]),
    )


__all__ = [
    "auth_session_from_row",
    "UNSET",
    "access_from_row",
    "date_from_db",
    "is_valid_email",
    "mri_case_from_row",
    "normalize_date",
    "normalize_email",
    "normalize_required_text",
    "quote_identifier",
    "subject_from_row",
    "user_credentials_from_row",
    "user_from_row",
]
