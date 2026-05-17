from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    authenticated: bool
    user_id: int | None = None
    email: str | None = None


# -----------------------------------------------------------------------------
# shared
# -----------------------------------------------------------------------------

class ApiMessage(BaseModel):
    message: str


# -----------------------------------------------------------------------------
# users
# -----------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: str
    password: str


class UpdateUserRequest(BaseModel):
    email: str | None = None
    password: str | None = None


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