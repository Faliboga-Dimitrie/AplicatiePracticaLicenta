from __future__ import annotations

import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Callable

from ...access_control import DbResult, UserRecord


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
    
    def active_for_case_type(self, *, case_id: int, job_type: str) -> DbResult[JobRecord | None]:
        """Return the newest non-terminal job of this type for this case, regardless of user."""
        with self._lock:
            matches = [
                job
                for job in self._jobs.values()
                if job.case_id == case_id
                and job.type == job_type
                and job.status not in JobStatus.TERMINAL
            ]

        if not matches:
            return DbResult.ok(None)

        matches.sort(key=lambda job: job.created_at, reverse=True)
        return DbResult.ok(matches[0])

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


__all__ = [
    "JobContext",
    "JobHandler",
    "JobListener",
    "JobRecord",
    "JobService",
    "JobStatus",
]
