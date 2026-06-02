from __future__ import annotations

from typing import Any

from ...access_control import DbResult, UserRecord
from ...project_core.config import Settings, ensure_main_directories, settings as project_settings
from ...project_core.domain import MRICase
from ...project_core.ports import (
    ReorientationBackend,
    SegmentationBackend,
    SkullStripBackend,
    WorkspaceProvider,
)
from .cases import CaseService
from .common import mark_case_status_best_effort, require_not_cancelled
from .jobs import JobContext, JobRecord, JobService


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
    ACTIVE_JOB_MESSAGE = "A preprocessing job is already running for this case."

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
        )
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        active = self.jobs.active_for_case_type(
            case_id=case_id,
            job_type=self.JOB_TYPE,
        )
        if not active.success:
            return DbResult.fail(active.error or "Could not check active preprocessing jobs.")
        if active.data is not None:
            return DbResult.fail(self.ACTIVE_JOB_MESSAGE)

        queued = self.cases.set_status_for_user(
            user,
            case_id,
            PreprocessingStatus.QUEUED,
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
            require_not_cancelled(context, "Preprocessing job was cancelled.")
            context.checkpoint("Preparing preprocessing environment...", progress=5)
            self._preflight_checks()

            running = self.cases.set_status_for_user(
                user,
                case_id,
                PreprocessingStatus.RUNNING,
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

            require_not_cancelled(context, "Preprocessing job was cancelled.")
            context.checkpoint("Running reorientation...", progress=25)
            reorientation = self.reorientation_backend.run(domain_case, workspace)

            require_not_cancelled(context, "Preprocessing job was cancelled.")
            context.checkpoint("Running skull stripping with HD-BET...", progress=50)
            skull_strip = self.skull_strip_backend.run(
                reorientation.output_path,
                workspace,
            )

            require_not_cancelled(context, "Preprocessing job was cancelled.")
            context.checkpoint("Running FAST segmentation...", progress=75)
            segmentation = self.segmentation_backend.run(
                skull_strip.image_path,
                workspace,
            )

            require_not_cancelled(context, "Preprocessing job was cancelled.")
            completed = self.cases.set_status_for_user(
                user,
                case_id,
                PreprocessingStatus.COMPLETED,
            )
            if not completed.success:
                raise RuntimeError(completed.error or "Could not mark preprocessing as completed.")

            payload = self._result_to_dict(
                case_db_id=case_id,
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
                mark_case_status_best_effort(
                    cases=self.cases,
                    user=user,
                    case_id=case_id,
                    status=PreprocessingStatus.CANCELLED,
                )
            else:
                mark_case_status_best_effort(
                    cases=self.cases,
                    user=user,
                    case_id=case_id,
                    status=PreprocessingStatus.FAILED,
                )
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

    def _result_to_dict(
        self,
        *,
        case_db_id: int,
        subject_id: str,
        workspace: Any,
        reorientation: Any,
        skull_strip: Any,
        segmentation: Any,
    ) -> dict[str, Any]:
        return {
            "subject_id": subject_id,
            "acquisition_date": workspace.acquisition_date,
            "case_key": workspace.case_id,
            "case_id": case_db_id,
            "artifacts_url": f"/cases/{case_db_id}/artifacts",
            "outputs": {
                "raw_exists": workspace.raw_path.exists(),
                "reoriented": reorientation.output_path.exists(),
                "skull_stripped": skull_strip.image_path.exists(),
                "fast_pve_outputs": all(path.exists() for path in segmentation.pve_paths.values()),
            },
        }


__all__ = ["PreprocessingService", "PreprocessingStatus"]
