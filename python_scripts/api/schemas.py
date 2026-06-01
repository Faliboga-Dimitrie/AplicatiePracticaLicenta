from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from typing import Any

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# auth
# -----------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class CurrentUserResponse(BaseModel):
    user: UserResponse


class AccountDeletionResponse(BaseModel):
    deleted: bool
    deleted_subject_ids: list[str] = Field(default_factory=list)
    kept_subject_ids: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# shared
# -----------------------------------------------------------------------------

class ApiMessage(BaseModel):
    message: str


# -----------------------------------------------------------------------------
# subjects
# -----------------------------------------------------------------------------

class CreateSubjectRequest(BaseModel):
    subject_id: str
    name: str | None = None
    age: int | None = None
    notes: str | None = None


class UpdateSubjectRequest(BaseModel):
    name: str | None = None
    age: int | None = None
    notes: str | None = None


class SubjectResponse(BaseModel):
    id: str
    name: str | None = None
    age: int | None = None
    notes: str | None = None


class MriCaseResponse(BaseModel):
    id: int
    subject_id: str
    acquisition_date: date
    notes: str | None = None
    status: str | None = None
    case_key: str | None = None
    workspace: dict[str, Any] | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)


class AuthorizedSubjectResponse(BaseModel):
    id: str
    name: str | None = None
    age: int | None = None
    notes: str | None = None
    role: str
    case_count: int
    cases: list[MriCaseResponse] | None = None


# -----------------------------------------------------------------------------
# MRI cases
# -----------------------------------------------------------------------------

class CreateMriCaseRequest(BaseModel):
    subject_id: str
    acquisition_date: date
    notes: str | None = None
    status: str | None = "registered"
    source_raw_path: Path | None = None


class UpdateMriCaseRequest(BaseModel):
    acquisition_date: date | None = None
    notes: str | None = None
    status: str | None = None


# -----------------------------------------------------------------------------
# jobs
# -----------------------------------------------------------------------------



class JobResponse(BaseModel):
    id: str
    type: str
    status: str
    user_id: int
    case_id: int | None = None
    message: str | None = None
    progress: float | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any | None = None
    error: str | None = None
    metadata: dict[str, Any]
    cancel_requested: bool = False


# -----------------------------------------------------------------------------
# artifacts
# -----------------------------------------------------------------------------

class ArtifactResponse(BaseModel):
    name: str
    kind: str
    url: str
    mime_type: str | None = None
    size_bytes: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaseArtifactsResponse(BaseModel):
    case_id: int
    case_key: str
    subject_id: str
    acquisition_date: date
    artifacts: list[ArtifactResponse]
