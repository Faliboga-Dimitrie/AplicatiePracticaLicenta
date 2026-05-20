from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import RLock
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

from ..project_core.config import Settings, ensure_main_directories, settings as project_settings
from ..project_core.domain import MRICase
from ..project_core.ports import (
    ReorientationBackend,
    SegmentationBackend,
    SkullStripBackend,
    WorkspaceProvider,
)
from ..project_core.workspace import FileSystemWorkspaceProvider

from ..project_core.artifacts import (
    ArtifactKind,
    ArtifactRef,
    StoredCaseResult,
    guess_mime_type,
)

from ..access_control import (
    AccessControlService,
    DbResult,
    MriCaseRecord,
    SubjectWithCases,
    UserRecord,
)
from ..access_control.utils import UNSET


class AuthError(RuntimeError):
    """Raised when a bearer token is missing, malformed, expired, or invalid."""


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    email: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    access_token: str
    token_type: str
    expires_at: datetime
    user: UserRecord


class TokenService:
    """
    Small HS256 bearer-token service.

    This intentionally uses only the Python standard library, so the project does
    not need PyJWT/python-jose yet. The token format is JWT-compatible enough for
    our own backend: header.payload.signature, signed with HMAC-SHA256.

    React does not need to understand the token contents. It only stores the
    string and sends it back as:

        Authorization: Bearer <token>
    """

    def __init__(
        self,
        *,
        secret_key: str,
        issuer: str = "brain-mri-api",
        access_token_minutes: int = 8 * 60,
    ):
        if not secret_key:
            raise ValueError("secret_key must not be empty.")
        if access_token_minutes <= 0:
            raise ValueError("access_token_minutes must be positive.")

        self.secret_key = secret_key.encode("utf-8")
        self.issuer = issuer
        self.access_token_minutes = access_token_minutes

    def create_access_token(self, user: UserRecord) -> tuple[str, datetime]:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.access_token_minutes)

        header = {
            "alg": "HS256",
            "typ": "JWT",
        }
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": self.issuer,
        }

        header_part = self._encode_json(header)
        payload_part = self._encode_json(payload)
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        signature_part = self._sign(signing_input)

        return f"{header_part}.{payload_part}.{signature_part}", expires_at

    def verify_access_token(self, token: str) -> TokenPayload:
        try:
            header_part, payload_part, signature_part = token.split(".", 2)
        except ValueError as exc:
            raise AuthError("Invalid token format.") from exc

        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected_signature = self._sign(signing_input)

        if not hmac.compare_digest(signature_part, expected_signature):
            raise AuthError("Invalid token signature.")

        header = self._decode_json(header_part)
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise AuthError("Unsupported token header.")

        payload = self._decode_json(payload_part)

        if payload.get("iss") != self.issuer:
            raise AuthError("Invalid token issuer.")

        try:
            user_id = int(payload["sub"])
            email = str(payload["email"])
            exp = int(payload["exp"])
        except Exception as exc:
            raise AuthError("Invalid token payload.") from exc

        expires_at = datetime.fromtimestamp(exp, timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            raise AuthError("Token expired.")

        return TokenPayload(
            user_id=user_id,
            email=email,
            expires_at=expires_at,
        )

    def _sign(self, signing_input: bytes) -> str:
        digest = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        return self._b64url_encode(digest)

    def _encode_json(self, value: dict[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._b64url_encode(raw)

    def _decode_json(self, value: str) -> dict[str, Any]:
        try:
            raw = self._b64url_decode(value)
            decoded = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise AuthError("Invalid token JSON.") from exc

        if not isinstance(decoded, dict):
            raise AuthError("Invalid token JSON payload.")
        return decoded

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class AuthService:
    """
    Web-facing authentication service.

    AccessControlService remains responsible for checking email/password.
    AuthService is responsible for web concerns: login response, bearer-token
    creation, bearer-token verification, and loading the current user.
    """

    def __init__(
        self,
        access: AccessControlService,
        token_service: TokenService,
    ):
        self.access = access
        self.token_service = token_service

    def login(self, email: str, password: str) -> DbResult[AuthenticatedSession]:
        auth_result = self.access.authenticate(email, password)
        if not auth_result.success:
            return DbResult.fail(auth_result.error or "Authentication failed.")

        auth = auth_result.data
        if auth is None or not auth.authenticated or auth.user_id is None:
            return DbResult.ok(None)

        user_result = self.access.get_user_by_id(auth.user_id)
        if not user_result.success:
            return DbResult.fail(user_result.error or "Could not load authenticated user.")
        if user_result.data is None:
            return DbResult.fail("Authenticated user no longer exists.")

        token, expires_at = self.token_service.create_access_token(user_result.data)
        return DbResult.ok(
            AuthenticatedSession(
                access_token=token,
                token_type="bearer",
                expires_at=expires_at,
                user=user_result.data,
            )
        )

    def get_current_user(self, token: str) -> DbResult[UserRecord]:
        try:
            payload = self.token_service.verify_access_token(token)
        except AuthError as exc:
            return DbResult.fail(str(exc))

        user_result = self.access.get_user_by_id(payload.user_id)
        if not user_result.success:
            return DbResult.fail(user_result.error or "Could not load current user.")
        if user_result.data is None:
            return DbResult.fail("User no longer exists.")

        # Optional sanity check: a token for an old email should stop working
        # after the user email changes.
        if user_result.data.email != payload.email:
            return DbResult.fail("Token user data is stale.")

        return DbResult.ok(user_result.data)


class SubjectService:
    """
    Web-facing subject service.

    The API should not list every subject from the database. For the React UI,
    subjects are always loaded through the authenticated user, so authorization
    stays in one place instead of being repeated in every router function.
    """

    def __init__(self, access: AccessControlService):
        self.access = access

    def list_for_user(
        self,
        user: UserRecord,
        *,
        include_cases: bool = True,
    ) -> DbResult[list[SubjectWithCases]]:
        return self.access.list_accessible_subjects(
            user.id,
            include_cases=include_cases,
        )

    def get_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        include_cases: bool = True,
    ) -> DbResult[SubjectWithCases]:
        result = self.access.search_by_subject_id(
            user.id,
            subject_id,
            include_cases=include_cases,
        )

        if not result.success:
            return DbResult.fail(result.error or "Could not load authorized subject.")

        subjects = result.data or []
        if not subjects:
            return DbResult.ok(None)

        return DbResult.ok(subjects[0])

    def list_cases_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[list[MriCaseRecord]]:
        result = self.get_for_user(
            user,
            subject_id,
            include_cases=True,
        )

        if not result.success:
            return DbResult.fail(result.error or "Could not load subject cases.")
        if result.data is None:
            return DbResult.ok(None)

        return DbResult.ok(list(result.data.cases))

    def create_for_user(
        self,
        user: UserRecord,
        *,
        subject_id: str,
        name: str | None = None,
        age: int | None = None,
        notes: str | None = None,
        owner_role: str = "owner",
    ) -> DbResult[SubjectWithCases]:
        """
        Create a subject from the normal web UI and give the creator access.

        This is the user-facing alternative to the old admin/test CRUD route. The
        important rule is that the same operation creates the subject row and the
        subject_access row, otherwise the creator would not see the subject when
        React calls GET /subjects.
        """
        existing = self.access.get_subject(subject_id)
        if not existing.success:
            return DbResult.fail(existing.error or "Could not check whether subject exists.")

        if existing.data is not None:
            access = self.access.get_subject_access(user.id, subject_id)
            if not access.success:
                return DbResult.fail(access.error or "Could not check existing subject access.")
            if access.data is not None:
                return DbResult.fail("Subject already exists and is already visible to this user.")
            return DbResult.fail("Subject already exists. Ask an administrator to grant access instead of claiming it from the UI.")

        created = self.access.create_subject(
            subject_id,
            name=name,
            age=age,
            notes=notes,
        )
        if not created.success:
            return DbResult.fail(created.error or "Could not create subject.")
        if created.data is None:
            return DbResult.fail("Could not create subject.")

        granted = self.access.grant_subject_access(
            user.id,
            created.data.id,
            role=owner_role,
        )
        if not granted.success:
            # Best-effort rollback: the subject has no cases yet because it was
            # just created through this endpoint. If rollback fails, keep the
            # original error because that is what broke the user flow.
            self.access.delete_subject(created.data.id)
            return DbResult.fail(granted.error or "Subject was created, but access could not be granted.")

        return self.get_for_user(user, created.data.id, include_cases=True)



class CaseService:
    """
    Web-facing MRI case service.

    Case routes should not read MRI cases directly from the database, because a
    case belongs to a subject and subject access is what authorizes the user.
    This service keeps that rule in one place:

    - reading a case requires at least viewer access;
    - creating/updating/deleting a case requires at least editor access.

    Later, the preprocessing and mesh job services can also depend on this class
    before starting expensive work.
    """

    def __init__(self, access: AccessControlService):
        self.access = access

    def list_for_user(self, user: UserRecord) -> DbResult[list[MriCaseRecord]]:
        """Return all MRI cases belonging to subjects visible to this user."""
        result = self.access.list_accessible_subjects(
            user.id,
            include_cases=True,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not load authorized cases.")

        cases: list[MriCaseRecord] = []
        for subject_with_cases in result.data or []:
            cases.extend(subject_with_cases.cases)

        return DbResult.ok(cases)

    def list_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[list[MriCaseRecord]]:
        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role="viewer",
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.list_cases_for_subject(subject_id)

    def get_for_user(
        self,
        user: UserRecord,
        case_id: int,
        *,
        minimum_role: str = "viewer",
    ) -> DbResult[MriCaseRecord]:
        allowed = self._user_has_case_access(
            user,
            case_id,
            minimum_role=minimum_role,
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check case access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.get_mri_case(case_id)

    def get_first_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[MriCaseRecord]:
        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role="viewer",
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.get_first_mri_case_for_subject(subject_id)

    def get_by_subject_date(
        self,
        user: UserRecord,
        subject_id: str,
        acquisition_date: str | date,
        *,
        minimum_role: str = "viewer",
    ) -> DbResult[MriCaseRecord]:
        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role=minimum_role,
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.get_mri_case_by_subject_date(subject_id, acquisition_date)

    def create_for_user(
        self,
        user: UserRecord,
        *,
        subject_id: str,
        acquisition_date: str | date,
        notes: str | None = None,
        status: str | None = "registered",
        source_raw_path: Path | None = None,
    ) -> DbResult[MriCaseRecord]:
        if source_raw_path is None:
            return DbResult.fail("source_raw_path is required until the upload endpoint is implemented.")

        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role="editor",
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        duplicate = self.access.get_mri_case_by_subject_date(subject_id, acquisition_date)
        if not duplicate.success:
            return DbResult.fail(duplicate.error or "Could not check duplicate MRI case.")
        if duplicate.data is not None:
            return DbResult.fail("MRI case with this subject ID and acquisition date already exists.")

        return self.access.create_mri_case(
            subject_id=subject_id,
            acquisition_date=acquisition_date,
            notes=notes,
            status=status,
            source_raw_path=source_raw_path,
        )

    def update_for_user(
        self,
        user: UserRecord,
        case_id: int,
        *,
        new_acquisition_date: str | date | object = UNSET,
        notes: str | None | object = UNSET,
        status: str | None | object = UNSET,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_for_user(user, case_id, minimum_role="editor")
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before update.")
        if current.data is None:
            return DbResult.ok(None)

        result = self.access.update_mri_case_by_subject_date(
            current.data.subject_id,
            current.data.acquisition_date,
            new_acquisition_date=new_acquisition_date,
            notes=notes,
            status=status,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not update MRI case.")
        if not result.data:
            return DbResult.fail("No MRI case fields were changed.")

        refreshed_date = (
            new_acquisition_date
            if new_acquisition_date is not UNSET
            else current.data.acquisition_date
        )
        return self.access.get_mri_case_by_subject_date(
            current.data.subject_id,
            refreshed_date,
        )

    def update_by_subject_date_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        acquisition_date: str | date,
        *,
        new_acquisition_date: str | date | object = UNSET,
        notes: str | None | object = UNSET,
        status: str | None | object = UNSET,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_by_subject_date(
            user,
            subject_id,
            acquisition_date,
            minimum_role="editor",
        )
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before update.")
        if current.data is None:
            return DbResult.ok(None)

        return self.update_for_user(
            user,
            current.data.id,
            new_acquisition_date=new_acquisition_date,
            notes=notes,
            status=status,
        )

    def delete_for_user(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_for_user(user, case_id, minimum_role="editor")
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before delete.")
        if current.data is None:
            return DbResult.ok(None)

        result = self.access.delete_mri_case_by_subject_date(
            current.data.subject_id,
            current.data.acquisition_date,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not delete MRI case.")
        if not result.data:
            return DbResult.ok(None)

        return DbResult.ok(current.data)

    def delete_by_subject_date_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        acquisition_date: str | date,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_by_subject_date(
            user,
            subject_id,
            acquisition_date,
            minimum_role="editor",
        )
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before delete.")
        if current.data is None:
            return DbResult.ok(None)

        return self.delete_for_user(user, current.data.id)

    def set_status_for_user(
        self,
        user: UserRecord,
        case_id: int,
        status: str,
        *,
        minimum_role: str = "editor",
    ) -> DbResult[MriCaseRecord]:
        """
        Update only the status of a case the user may edit.

        This is intentionally tolerant of setting the same status twice, because
        background jobs may retry a transition or restart after a previous run.
        """
        current = self.get_for_user(user, case_id, minimum_role=minimum_role)
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before status update.")
        if current.data is None:
            return DbResult.ok(None)

        if current.data.status == status:
            return DbResult.ok(current.data)

        result = self.access.update_mri_case_by_subject_date(
            current.data.subject_id,
            current.data.acquisition_date,
            status=status,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not update MRI case status.")

        refreshed = self.access.get_mri_case(current.data.id)
        if not refreshed.success:
            return DbResult.fail(refreshed.error or "Could not reload MRI case after status update.")

        return refreshed

    def _user_has_subject_access(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        minimum_role: str,
    ) -> DbResult[bool]:
        return self.access.user_has_subject_access(
            user.id,
            subject_id,
            minimum_role=minimum_role,
        )

    def _user_has_case_access(
        self,
        user: UserRecord,
        case_id: int,
        *,
        minimum_role: str,
    ) -> DbResult[bool]:
        return self.access.user_has_case_access(
            user.id,
            case_id,
            minimum_role=minimum_role,
        )


class JobStatus:
    """Small string constants used by the in-memory job registry."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"

    TERMINAL = {COMPLETED, FAILED, CANCELLED}


@dataclass(frozen=True)
class JobRecord:
    """Public job state returned to the React UI."""

    id: str
    type: str
    status: str
    user_id: int
    case_id: int | None = None
    message: str | None = None
    progress: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    cancel_requested: bool = False


class JobContext:
    """Object passed to long-running services so they can report progress."""

    def __init__(self, service: "JobService", job_id: str):
        self._service = service
        self.job_id = job_id

    @property
    def cancel_requested(self) -> bool:
        job = self._service.get(self.job_id)
        return bool(job and job.cancel_requested)

    def update(
        self,
        *,
        message: str | None = None,
        progress: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        return self._service.update_progress(
            self.job_id,
            message=message,
            progress=progress,
            metadata=metadata,
        )

    def checkpoint(self, message: str, *, progress: float | None = None) -> None:
        """Convenience method for readable pipeline steps."""
        self.update(message=message, progress=progress)


JobHandler = Callable[[JobContext], Any]
JobListener = Callable[[JobRecord], None]


class JobService:
    """
    In-memory background job service for React-friendly long tasks.

    The service is intentionally generic. It does not know what preprocessing or
    mesh analysis means. Domain services will create jobs like this:

        jobs.start(
            user=user,
            job_type="preprocessing",
            case_id=case.id,
            handler=lambda ctx: preprocessing_runner.run(case, ctx),
        )

    React receives the returned job id immediately and polls GET /jobs/{job_id}.

    This first version is in-memory because it is simple and enough for a local
    licenta backend. Later, the same public methods can be backed by MySQL.
    """

    def __init__(self, *, max_workers: int = 1):
        if max_workers <= 0:
            raise ValueError("max_workers must be positive.")

        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = RLock()
        self._jobs: dict[str, JobRecord] = {}
        self._futures: dict[str, Future[Any]] = {}
        self._listeners: list[JobListener] = []

    def subscribe(self, listener: JobListener) -> None:
        """Register a status/progress listener used by higher-level services."""
        with self._lock:
            self._listeners.append(listener)

    def start(
        self,
        *,
        user: UserRecord,
        job_type: str,
        handler: JobHandler,
        case_id: int | None = None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DbResult[JobRecord]:
        if not job_type.strip():
            return DbResult.fail("job_type must not be empty.")

        job_id = uuid.uuid4().hex
        record = JobRecord(
            id=job_id,
            type=job_type,
            status=JobStatus.QUEUED,
            user_id=user.id,
            case_id=case_id,
            message=message or "Job queued.",
            metadata=dict(metadata or {}),
        )

        with self._lock:
            self._jobs[job_id] = record

        self._notify(record)

        future = self._executor.submit(self._run_job, job_id, handler)
        with self._lock:
            self._futures[job_id] = future

        return DbResult.ok(record)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_for_user(self, user: UserRecord, job_id: str) -> DbResult[JobRecord]:
        job = self.get(job_id)
        if job is None or job.user_id != user.id:
            return DbResult.ok(None)
        return DbResult.ok(job)

    def list_for_user(
        self,
        user: UserRecord,
        *,
        case_id: int | None = None,
    ) -> DbResult[list[JobRecord]]:
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if job.user_id == user.id and (case_id is None or job.case_id == case_id)
            ]

        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return DbResult.ok(jobs)

    def cancel_for_user(self, user: UserRecord, job_id: str) -> DbResult[JobRecord]:
        job = self.get(job_id)
        if job is None or job.user_id != user.id:
            return DbResult.ok(None)

        if job.status in JobStatus.TERMINAL:
            return DbResult.ok(job)

        updated = self._replace_job(
            job_id,
            status=JobStatus.CANCELLATION_REQUESTED,
            message="Cancellation requested.",
            cancel_requested=True,
        )
        return DbResult.ok(updated)

    def update_progress(
        self,
        job_id: str,
        *,
        message: str | None = None,
        progress: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        if progress is not None:
            progress = max(0.0, min(100.0, float(progress)))

        with self._lock:
            current = self._require_job(job_id)
            merged_metadata = dict(current.metadata)
            if metadata:
                merged_metadata.update(metadata)

        return self._replace_job(
            job_id,
            message=message if message is not None else current.message,
            progress=progress if progress is not None else current.progress,
            metadata=merged_metadata,
        )

    def _run_job(self, job_id: str, handler: JobHandler) -> None:
        self._replace_job(
            job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            message="Job running.",
        )

        context = JobContext(self, job_id)

        try:
            if context.cancel_requested:
                self._replace_job(
                    job_id,
                    status=JobStatus.CANCELLED,
                    finished_at=datetime.now(timezone.utc),
                    message="Job cancelled before start.",
                )
                return

            result = handler(context)

            current = self._require_job(job_id)
            if current.cancel_requested:
                self._replace_job(
                    job_id,
                    status=JobStatus.CANCELLED,
                    finished_at=datetime.now(timezone.utc),
                    message="Job cancelled.",
                )
                return

            self._replace_job(
                job_id,
                status=JobStatus.COMPLETED,
                finished_at=datetime.now(timezone.utc),
                progress=100.0,
                message=current.message or "Job completed.",
                result=result,
            )
        except Exception as exc:
            current = self._require_job(job_id)
            if current.cancel_requested:
                self._replace_job(
                    job_id,
                    status=JobStatus.CANCELLED,
                    finished_at=datetime.now(timezone.utc),
                    message="Job cancelled.",
                    error=str(exc),
                )
                return

            self._replace_job(
                job_id,
                status=JobStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                message="Job failed.",
                error=str(exc),
            )

    def _replace_job(self, job_id: str, **changes: Any) -> JobRecord:
        with self._lock:
            current = self._require_job(job_id)
            updated = replace(current, **changes)
            self._jobs[job_id] = updated

        self._notify(updated)
        return updated

    def _require_job(self, job_id: str) -> JobRecord:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job id: {job_id}")
        return job

    def _notify(self, job: JobRecord) -> None:
        with self._lock:
            listeners = list(self._listeners)

        for listener in listeners:
            try:
                listener(job)
            except Exception:
                # Job state should not break because a later notification hook fails.
                pass




class PreprocessingStatus:
    """Database status values used around the preprocessing job lifecycle."""

    QUEUED = "preprocessing_queued"
    RUNNING = "preprocessing"
    COMPLETED = "preprocessed"
    FAILED = "failed"
    CANCELLED = "preprocessing_cancelled"


class PreprocessingService:
    """
    Web-facing preprocessing service.

    It adapts the existing preprocessing pipeline to React-friendly behavior:

    - checks the logged-in user's case permission through CaseService;
    - creates a background job through JobService;
    - updates the MRI case status before, during, and after the run;
    - reports progress messages that React can poll through /jobs/{job_id};
    - still depends on protocols for the real processing backends.
    """

    JOB_TYPE = "preprocessing"

    def __init__(
        self,
        *,
        cases: CaseService,
        jobs: JobService,
        workspace_provider: WorkspaceProvider,
        reorientation_backend: ReorientationBackend,
        skull_strip_backend: SkullStripBackend,
        segmentation_backend: SegmentationBackend,
        settings_obj: Settings = project_settings,
    ):
        self.cases = cases
        self.jobs = jobs
        self.workspace_provider = workspace_provider
        self.reorientation_backend = reorientation_backend
        self.skull_strip_backend = skull_strip_backend
        self.segmentation_backend = segmentation_backend
        self.settings = settings_obj

    def start_for_case(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[JobRecord]:
        """
        Authorize and enqueue preprocessing for one MRI case.

        The returned JobRecord is immediate. The actual HD-BET/FAST work runs
        in JobService's worker thread. React should poll /jobs/{job_id}.
        """
        case_result = self.cases.get_for_user(
            user,
            case_id,
            minimum_role="editor",
        )
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        queued = self.cases.set_status_for_user(
            user,
            case_id,
            PreprocessingStatus.QUEUED,
            minimum_role="editor",
        )
        if not queued.success:
            return DbResult.fail(queued.error or "Could not mark preprocessing as queued.")

        case = case_result.data
        return self.jobs.start(
            user=user,
            job_type=self.JOB_TYPE,
            case_id=case.id,
            message="Preprocessing queued.",
            metadata={
                "subject_id": case.subject_id,
                "acquisition_date": case.acquisition_date.isoformat(),
            },
            handler=lambda context: self._run_preprocessing_job(
                user=user,
                case_id=case.id,
                context=context,
            ),
        )

    def _run_preprocessing_job(
        self,
        *,
        user: UserRecord,
        case_id: int,
        context: JobContext,
    ) -> dict[str, Any]:
        try:
            self._require_not_cancelled(context)
            context.checkpoint("Preparing preprocessing environment...", progress=5)
            self._preflight_checks()

            running = self.cases.set_status_for_user(
                user,
                case_id,
                PreprocessingStatus.RUNNING,
                minimum_role="editor",
            )
            if not running.success:
                raise RuntimeError(running.error or "Could not mark preprocessing as running.")
            if running.data is None:
                raise RuntimeError("MRI case disappeared before preprocessing started.")

            case_record = running.data
            workspace = case_record.workspace
            if workspace is None:
                raise RuntimeError("Workspace could not be resolved for MRI case.")

            domain_case = MRICase(
                subject_id=case_record.subject_id,
                acquisition_date=case_record.acquisition_date.isoformat(),
                raw_path=workspace.raw_path,
            )

            context.update(
                message="Creating preprocessing workspace...",
                progress=10,
                metadata={
                    "subject_id": case_record.subject_id,
                    "acquisition_date": case_record.acquisition_date.isoformat(),
                    "case_status": PreprocessingStatus.RUNNING,
                },
            )
            workspace = self.workspace_provider.create_workspace(domain_case)

            self._require_not_cancelled(context)
            context.checkpoint("Running reorientation...", progress=25)
            reorientation = self.reorientation_backend.run(domain_case, workspace)

            self._require_not_cancelled(context)
            context.checkpoint("Running skull stripping with HD-BET...", progress=50)
            skull_strip = self.skull_strip_backend.run(
                reorientation.output_path,
                workspace,
            )

            self._require_not_cancelled(context)
            context.checkpoint("Running FAST segmentation...", progress=75)
            segmentation = self.segmentation_backend.run(
                skull_strip.image_path,
                workspace,
            )

            completed = self.cases.set_status_for_user(
                user,
                case_id,
                PreprocessingStatus.COMPLETED,
                minimum_role="editor",
            )
            if not completed.success:
                raise RuntimeError(completed.error or "Could not mark preprocessing as completed.")

            payload = self._result_to_dict(
                subject_id=domain_case.subject_id,
                workspace=workspace,
                reorientation=reorientation,
                skull_strip=skull_strip,
                segmentation=segmentation,
            )
            context.update(
                message="Preprocessing completed.",
                progress=100,
                metadata={"case_status": PreprocessingStatus.COMPLETED},
            )
            return payload

        except Exception:
            if context.cancel_requested:
                self._mark_status_best_effort(user, case_id, PreprocessingStatus.CANCELLED)
            else:
                self._mark_status_best_effort(user, case_id, PreprocessingStatus.FAILED)
            raise

    def _preflight_checks(self) -> None:
        ensure_main_directories(self.settings)

        if not self.settings.mni_template_path.exists():
            raise FileNotFoundError(
                f"MNI template not found: {self.settings.mni_template_path}"
            )
        if not self.settings.reorient_script.exists():
            raise FileNotFoundError(
                f"Reorientation script not found: {self.settings.reorient_script}"
            )
        if not self.settings.fast_script.exists():
            raise FileNotFoundError(
                f"FAST script not found: {self.settings.fast_script}"
            )

    def _require_not_cancelled(self, context: JobContext) -> None:
        if context.cancel_requested:
            raise RuntimeError("Preprocessing job was cancelled.")

    def _mark_status_best_effort(
        self,
        user: UserRecord,
        case_id: int,
        status: str,
    ) -> None:
        try:
            self.cases.set_status_for_user(
                user,
                case_id,
                status,
                minimum_role="editor",
            )
        except Exception:
            pass

    def _result_to_dict(
        self,
        *,
        subject_id: str,
        workspace: Any,
        reorientation: Any,
        skull_strip: Any,
        segmentation: Any,
    ) -> dict[str, Any]:
        return {
            "subject_id": subject_id,
            "acquisition_date": workspace.acquisition_date,
            "case_id": workspace.case_id,
            "raw_path": workspace.raw_path,
            "reoriented_path": reorientation.output_path,
            "skull_stripped_path": skull_strip.image_path,
            "segmentation_path": segmentation.seg_path,
            "pve_paths": dict(segmentation.pve_paths),
            "qc_paths": workspace.existing_qc_paths,
        }



@dataclass(frozen=True)
class ArtifactFile:
    """
    Internal API artifact representation.

    ArtifactRef is the public/domain object returned to React. This wrapper also
    keeps the local path needed by FileResponse, but serialization deliberately
    does not expose that filesystem path.
    """

    ref: ArtifactRef
    path: Path
    size_bytes: int


@dataclass(frozen=True)
class CaseArtifactBundle:
    """Artifacts discovered for one authorized MRI case."""

    case_db_id: int
    subject_id: str
    acquisition_date: date
    case_key: str
    artifacts: tuple[ArtifactFile, ...]

    @property
    def stored_result(self) -> StoredCaseResult:
        return StoredCaseResult(
            subject_id=self.subject_id,
            acquisition_date=self.acquisition_date.isoformat(),
            artifacts=tuple(artifact.ref for artifact in self.artifacts),
        )


class ArtifactService:
    """
    Web-facing artifact service.

    This service turns the files known by CaseWorkspace into frontend-safe
    ArtifactRef objects and FileResponse-ready paths. React sees stable URLs like:

        /cases/12/artifacts/csf_mesh.glb

    It never receives raw local filesystem paths. File serving is also safe
    because get_file_for_case only returns files from the known workspace artifact
    manifest, not an arbitrary path provided by the client.
    """

    def __init__(
        self,
        *,
        cases: CaseService,
        workspace_provider: WorkspaceProvider,
    ):
        self.cases = cases
        self.workspace_provider = workspace_provider

    def list_for_case(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[CaseArtifactBundle]:
        case_result = self.cases.get_for_user(
            user,
            case_id,
            minimum_role="viewer",
        )
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        try:
            bundle = self._build_bundle(case_result.data)
            return DbResult.ok(bundle)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_file_for_case(
        self,
        user: UserRecord,
        case_id: int,
        artifact_name: str,
    ) -> DbResult[ArtifactFile]:
        bundle_result = self.list_for_case(user, case_id)
        if not bundle_result.success:
            return DbResult.fail(bundle_result.error or "Could not load case artifacts.")
        if bundle_result.data is None:
            return DbResult.ok(None)

        normalized_name = artifact_name.strip()
        for artifact in bundle_result.data.artifacts:
            if artifact.ref.name == normalized_name:
                return DbResult.ok(artifact)

        return DbResult.ok(None)

    def _build_bundle(self, case: MriCaseRecord) -> CaseArtifactBundle:
        workspace = case.workspace
        if workspace is None:
            domain_case = MRICase(
                subject_id=case.subject_id,
                acquisition_date=case.acquisition_date.isoformat(),
                raw_path=Path(f"{case.subject_id}.nii.gz"),
            )
            workspace = self.workspace_provider.get_workspace(domain_case)

        artifacts: list[ArtifactFile] = []

        # Main 3D display outputs.
        for tissue, path in workspace.mesh_paths.items():
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=f"{tissue}_mesh.glb",
                    kind=ArtifactKind.MESH,
                    path=path,
                    metadata={"tissue": tissue},
                )
            )

        for tissue, path in workspace.wireframe_paths.items():
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=f"{tissue}_wireframe.glb",
                    kind=ArtifactKind.WIREFRAME,
                    path=path,
                    metadata={"tissue": tissue},
                )
            )

        artifacts.append(
            self._known_file(
                case_id=case.id,
                name="metrics.json",
                kind=ArtifactKind.METRICS,
                path=workspace.mesh_metrics_json_path,
            )
        )

        # QC images are useful for a React results/debug page when generated.
        for qc_name, path in workspace.qc_paths.items():
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=f"qc_{qc_name}.png",
                    kind=ArtifactKind.QC_IMAGE,
                    path=path,
                    metadata={"stage": qc_name},
                )
            )

        # Preprocessing outputs are not the main browser display target, but they
        # are useful for debugging/downloads and make the artifact list complete.
        preprocessing_outputs: list[tuple[str, Path, dict[str, Any]]] = [
            ("reoriented.nii.gz", workspace.reoriented_path, {"stage": "reorientation"}),
            ("skull_stripped.nii.gz", workspace.skull_stripped_path, {"stage": "hd_bet"}),
            ("skull_stripped_mask.nii.gz", workspace.skull_stripped_mask_path, {"stage": "hd_bet", "mask": True}),
            ("fast_seg.nii.gz", workspace.fast_seg_path, {"stage": "fast"}),
            ("fast_pveseg.nii.gz", workspace.fast_pve_seg_path, {"stage": "fast"}),
        ]
        for tissue, path in workspace.fast_pve_paths.items():
            preprocessing_outputs.append(
                (f"fast_pve_{tissue}.nii.gz", path, {"stage": "fast", "tissue": tissue})
            )

        for name, path, metadata in preprocessing_outputs:
            artifacts.append(
                self._known_file(
                    case_id=case.id,
                    name=name,
                    kind=ArtifactKind.NIFTI,
                    path=path,
                    metadata=metadata,
                )
            )

        existing_artifacts = tuple(artifact for artifact in artifacts if artifact is not None)
        return CaseArtifactBundle(
            case_db_id=case.id,
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
            case_key=case.case_key,
            artifacts=existing_artifacts,
        )

    def _known_file(
        self,
        *,
        case_id: int,
        name: str,
        kind: ArtifactKind,
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactFile | None:
        path = Path(path)
        if not path.exists() or not path.is_file():
            return None

        stat = path.stat()
        public_metadata: dict[str, Any] = {
            "size_bytes": stat.st_size,
        }
        if metadata:
            public_metadata.update(metadata)

        ref = ArtifactRef(
            name=name,
            kind=kind,
            uri=self._artifact_url(case_id, name),
            mime_type=guess_mime_type(path, kind),
            metadata=public_metadata,
        )
        return ArtifactFile(
            ref=ref,
            path=path.resolve(),
            size_bytes=stat.st_size,
        )

    def public_bundle_dict(self, bundle: CaseArtifactBundle) -> dict[str, Any]:
        """Return the frontend-safe artifact payload used by job results.

        This intentionally mirrors the /cases/{case_id}/artifacts response, but
        avoids importing API serializers into the service layer. No local
        filesystem paths are exposed.
        """
        return {
            "case_id": bundle.case_db_id,
            "case_key": bundle.case_key,
            "subject_id": bundle.subject_id,
            "acquisition_date": bundle.acquisition_date.isoformat(),
            "artifacts": [
                self.public_artifact_dict(artifact)
                for artifact in bundle.artifacts
            ],
        }

    def public_artifact_dict(self, artifact: ArtifactFile) -> dict[str, Any]:
        ref = artifact.ref
        return {
            "name": ref.name,
            "kind": ref.kind.value,
            "url": ref.uri,
            "mime_type": ref.mime_type,
            "size_bytes": artifact.size_bytes,
            "metadata": dict(ref.metadata or {}),
        }

    def _artifact_url(self, case_id: int, artifact_name: str) -> str:
        return f"/cases/{case_id}/artifacts/{quote(artifact_name, safe='')}"



class MeshAnalysisStatus:
    """Database status values used around the mesh-analysis job lifecycle."""

    QUEUED = "mesh_queued"
    RUNNING = "mesh_analysis"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "mesh_cancelled"


class MeshAnalysisService:
    """
    Web-facing mesh-analysis service.

    It adapts the existing mesh-analysis pipeline to React-friendly behavior:

    - checks the logged-in user's case permission through CaseService;
    - verifies that preprocessing/FAST PVE outputs exist before starting;
    - creates a background job through JobService;
    - updates the MRI case status before, during, and after the run;
    - reports progress messages that React can poll through /jobs/{job_id};
    - adds frontend-safe artifact URLs to the completed job result;
    - keeps the concrete mesh pipeline behind an injected factory.
    """

    JOB_TYPE = "mesh_analysis"

    def __init__(
        self,
        *,
        cases: CaseService,
        jobs: JobService,
        workspace_provider: WorkspaceProvider,
        pipeline_factory: Callable[[Any], Any],
        artifacts: ArtifactService,
        settings_obj: Settings = project_settings,
    ):
        self.cases = cases
        self.jobs = jobs
        self.workspace_provider = workspace_provider
        self.pipeline_factory = pipeline_factory
        self.artifacts = artifacts
        self.settings = settings_obj

    def start_for_case(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[JobRecord]:
        """
        Authorize and enqueue mesh analysis for one MRI case.

        The returned JobRecord is immediate. The actual volume/surface/GLB work
        runs in JobService's worker thread. React should poll /jobs/{job_id}.
        """
        case_result = self.cases.get_for_user(
            user,
            case_id,
            minimum_role="editor",
        )
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        case = case_result.data
        workspace = case.workspace
        if workspace is None:
            return DbResult.fail("Workspace could not be resolved for MRI case.")

        if not workspace.has_fast_pve_outputs:
            missing = [str(path) for path in workspace.missing_fast_pve_paths]
            return DbResult.fail(
                "Mesh analysis requires preprocessing/FAST PVE outputs first. "
                f"Missing files: {missing}"
            )

        queued = self.cases.set_status_for_user(
            user,
            case_id,
            MeshAnalysisStatus.QUEUED,
            minimum_role="editor",
        )
        if not queued.success:
            return DbResult.fail(queued.error or "Could not mark mesh analysis as queued.")

        return self.jobs.start(
            user=user,
            job_type=self.JOB_TYPE,
            case_id=case.id,
            message="Mesh analysis queued.",
            metadata={
                "subject_id": case.subject_id,
                "acquisition_date": case.acquisition_date.isoformat(),
            },
            handler=lambda context: self._run_mesh_analysis_job(
                user=user,
                case_id=case.id,
                context=context,
            ),
        )

    def _run_mesh_analysis_job(
        self,
        *,
        user: UserRecord,
        case_id: int,
        context: JobContext,
    ) -> dict[str, Any]:
        try:
            self._require_not_cancelled(context)
            context.checkpoint("Preparing mesh-analysis environment...", progress=5)
            self._preflight_checks()

            running = self.cases.set_status_for_user(
                user,
                case_id,
                MeshAnalysisStatus.RUNNING,
                minimum_role="editor",
            )
            if not running.success:
                raise RuntimeError(running.error or "Could not mark mesh analysis as running.")
            if running.data is None:
                raise RuntimeError("MRI case disappeared before mesh analysis started.")

            case_record = running.data
            workspace = case_record.workspace
            if workspace is None:
                raise RuntimeError("Workspace could not be resolved for MRI case.")

            domain_case = MRICase(
                subject_id=case_record.subject_id,
                acquisition_date=case_record.acquisition_date.isoformat(),
                raw_path=workspace.raw_path,
            )

            context.update(
                message="Loading prepared FAST outputs...",
                progress=10,
                metadata={
                    "subject_id": case_record.subject_id,
                    "acquisition_date": case_record.acquisition_date.isoformat(),
                    "case_status": MeshAnalysisStatus.RUNNING,
                },
            )
            workspace = self.workspace_provider.get_workspace(domain_case)
            workspace.ensure_directories()

            missing = workspace.missing_fast_pve_paths
            if missing:
                missing_str = ", ".join(str(path) for path in missing)
                raise FileNotFoundError(
                    "Mesh analysis requires FAST PVE outputs, but some files are missing: "
                    f"{missing_str}"
                )

            self._require_not_cancelled(context)
            context.checkpoint("Computing volumes, surfaces and GLB meshes...", progress=35)
            pipeline = self.pipeline_factory(workspace)
            result = pipeline.run()

            self._require_not_cancelled(context)
            completed = self.cases.set_status_for_user(
                user,
                case_id,
                MeshAnalysisStatus.COMPLETED,
                minimum_role="editor",
            )
            if not completed.success:
                raise RuntimeError(completed.error or "Could not mark mesh analysis as completed.")

            payload = self._result_to_dict(
                user=user,
                case_db_id=case_id,
                workspace=workspace,
                result=result,
            )
            context.update(
                message="Mesh analysis completed.",
                progress=100,
                metadata={
                    "case_status": MeshAnalysisStatus.COMPLETED,
                    "artifacts_url": f"/cases/{case_id}/artifacts",
                },
            )
            return payload

        except Exception:
            if context.cancel_requested:
                self._mark_status_best_effort(user, case_id, MeshAnalysisStatus.CANCELLED)
            else:
                self._mark_status_best_effort(user, case_id, MeshAnalysisStatus.FAILED)
            raise

    def _preflight_checks(self) -> None:
        ensure_main_directories(self.settings)

    def _require_not_cancelled(self, context: JobContext) -> None:
        if context.cancel_requested:
            raise RuntimeError("Mesh-analysis job was cancelled.")

    def _mark_status_best_effort(
        self,
        user: UserRecord,
        case_id: int,
        status: str,
    ) -> None:
        try:
            self.cases.set_status_for_user(
                user,
                case_id,
                status,
                minimum_role="editor",
            )
        except Exception:
            pass

    def _result_to_dict(
        self,
        *,
        user: UserRecord,
        case_db_id: int,
        workspace: Any,
        result: Any,
    ) -> dict[str, Any]:
        artifact_bundle_result = self.artifacts.list_for_case(user, case_db_id)
        if not artifact_bundle_result.success:
            raise RuntimeError(
                artifact_bundle_result.error
                or "Mesh analysis completed, but artifacts could not be listed."
            )
        if artifact_bundle_result.data is None:
            raise RuntimeError(
                "Mesh analysis completed, but the case artifacts are no longer authorized."
            )

        return {
            "subject_id": result.subject_id,
            "acquisition_date": workspace.acquisition_date,
            "case_key": workspace.case_id,
            "case_id": case_db_id,
            "volumes": result.volumes.to_dict(),
            "surfaces": result.surfaces.to_dict(),
            "artifacts_url": f"/cases/{case_db_id}/artifacts",
            "artifacts": self.artifacts.public_bundle_dict(artifact_bundle_result.data),
        }

def build_default_preprocessing_service(
    *,
    cases: CaseService,
    jobs: JobService,
    settings_obj: Settings = project_settings,
) -> PreprocessingService:
    # Local imports keep lightweight API modules importable even before the
    # scientific stack is touched. The concrete backends are only needed when
    # FastAPI builds the preprocessing dependency.
    from ..mri_preprocessing.reorient import FslReorientationBackend
    from ..mri_preprocessing.segmentation import FslFastSegmentationBackend
    from ..mri_preprocessing.skull_strip import HdBetSkullStripBackend

    return PreprocessingService(
        cases=cases,
        jobs=jobs,
        workspace_provider=FileSystemWorkspaceProvider(settings_obj),
        reorientation_backend=FslReorientationBackend(settings_obj),
        skull_strip_backend=HdBetSkullStripBackend(settings_obj),
        segmentation_backend=FslFastSegmentationBackend(settings_obj),
        settings_obj=settings_obj,
    )



def build_default_mesh_analysis_service(
    *,
    cases: CaseService,
    jobs: JobService,
    settings_obj: Settings = project_settings,
) -> MeshAnalysisService:
    # Local imports keep lightweight API modules importable even before the
    # scientific mesh stack is touched. The concrete pipeline is only needed
    # when FastAPI builds the mesh-analysis dependency.
    from ..mesh_analysis.exporters import GlbMeshExporter
    from ..mesh_analysis.mesh_extractors import MarchingCubesMeshExtractor
    from ..mesh_analysis.pipeline import MeshAnalysisPipeline
    from ..mesh_analysis.surface_estimators import TrimeshSurfaceEstimator
    from ..mesh_analysis.volume_estimators import PveSumVolumeEstimator

    def pipeline_factory(workspace: Any) -> MeshAnalysisPipeline:
        return MeshAnalysisPipeline(
            workspace=workspace,
            settings=settings_obj,
            volume_estimator=PveSumVolumeEstimator(),
            mesh_extractor=MarchingCubesMeshExtractor(),
            surface_estimator=TrimeshSurfaceEstimator(),
            mesh_exporter=GlbMeshExporter(),
            log_timings=False,
        )

    workspace_provider = FileSystemWorkspaceProvider(
        settings_obj,
        create_directories=False,
    )

    return MeshAnalysisService(
        cases=cases,
        jobs=jobs,
        workspace_provider=workspace_provider,
        pipeline_factory=pipeline_factory,
        artifacts=ArtifactService(
            cases=cases,
            workspace_provider=workspace_provider,
        ),
        settings_obj=settings_obj,
    )


def build_default_artifact_service(
    *,
    cases: CaseService,
    settings_obj: Settings = project_settings,
) -> ArtifactService:
    return ArtifactService(
        cases=cases,
        workspace_provider=FileSystemWorkspaceProvider(
            settings_obj,
            create_directories=False,
        ),
    )

def build_default_job_service() -> JobService:
    max_workers = int(os.getenv("MRI_API_JOB_WORKERS", "1"))
    return JobService(max_workers=max_workers)


def build_default_token_service() -> TokenService:
    """
    Build the token service used by FastAPI dependencies.

    For local development this has a fallback key. Before deployment, set:
        MRI_API_SECRET_KEY=<long random secret>
    """

    secret_key = os.getenv(
        "MRI_API_SECRET_KEY",
        "dev-only-change-this-secret-before-deployment",
    )
    access_token_minutes = int(os.getenv("MRI_API_ACCESS_TOKEN_MINUTES", "480"))

    return TokenService(
        secret_key=secret_key,
        access_token_minutes=access_token_minutes,
    )


__all__ = [
    "AuthError",
    "AuthenticatedSession",
    "AuthService",
    "TokenPayload",
    "SubjectService",
    "CaseService",
    "TokenService",
    "JobContext",
    "JobRecord",
    "JobService",
    "JobStatus",
    "PreprocessingService",
    "PreprocessingStatus",
    "MeshAnalysisService",
    "MeshAnalysisStatus",
    "ArtifactFile",
    "CaseArtifactBundle",
    "ArtifactService",
    "build_default_job_service",
    "build_default_mesh_analysis_service",
    "build_default_artifact_service",
    "build_default_preprocessing_service",
    "build_default_token_service",
]
