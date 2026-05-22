from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class UserRecord:
    id: int
    email: str


@dataclass(frozen=True)
class UserCredentialsRecord:
    """
    Internal user record used only during authentication.

    It is separated from UserRecord so password_hash is not accidentally returned
    in normal API-facing user responses.
    """

    id: int
    email: str
    password_hash: str


@dataclass(frozen=True)
class SubjectRecord:
    id: str
    name: str | None
    age: int | None
    notes: str | None


@dataclass(frozen=True)
class MriCaseRecord:
    id: int
    subject_id: str
    acquisition_date: date
    notes: str | None
    status: str | None
    workspace: Any | None = None

    @property
    def case_key(self) -> str:
        return f"{self.subject_id}_{self.acquisition_date.isoformat()}"


@dataclass(frozen=True)
class SubjectAccessRecord:
    user_id: int
    subject_id: str
    role: str


@dataclass(frozen=True)
class SubjectWithCases:
    subject: SubjectRecord
    cases: tuple[MriCaseRecord, ...]
    role: str


@dataclass(frozen=True)
class SubjectSummaryRecord:
    """
    Authorized subject summary used by list screens.

    Unlike SubjectWithCases, this does not carry full MRI case records. The
    case_count is computed in SQL, so GET /subjects can stay lightweight.
    """

    subject: SubjectRecord
    role: str
    case_count: int


__all__ = [
    "MriCaseRecord",
    "SubjectAccessRecord",
    "SubjectRecord",
    "SubjectSummaryRecord",
    "SubjectWithCases",
    "UserCredentialsRecord",
    "UserRecord",
]
