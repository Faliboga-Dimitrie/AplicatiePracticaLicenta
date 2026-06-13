from __future__ import annotations

from typing import Any, Callable

from ...access_control import DbResult, UserRecord
from ...project_core import CaseWorkspace
from ...project_core.config import Settings, ensure_main_directories, settings as project_settings
from ...project_core.domain import MRICase
from ...project_core.ports import (
    ReorientationBackend,
    SegmentationBackend,
    SkullStripBackend,
    WorkspaceProvider,
)
from .artifacts import ArtifactService
from .cases import CaseService
from .common import mark_case_status_best_effort, require_not_cancelled
from .jobs import JobContext, JobRecord, JobService


class FullProcessingStatus:
    """Database status values for the single user-facing processing flow."""

    QUEUED = "processing_queued"
    PREPROCESSING = "preprocessing"
    MESH_ANALYSIS = "mesh_analysis"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "processing_cancelled"


class FullProcessingService:
    """
    User-facing processing service that runs the complete MRI workflow.

    It intentionally presents one job to the frontend: prepare the scan, then
    create the 3D GLB models and JSON measurements. Intermediate scientific
    steps stay inside the service instead of becoming separate UI actions.
    """

    JOB_TYPE = "full_processing"
    ACTIVE_JOB_MESSAGE = "A processing job is already running for this case."

    def __init__(
        self,
        *,
        cases: CaseService,
        jobs: JobService,
        workspace_provider: WorkspaceProvider,
        reorientation_backend: ReorientationBackend,
        skull_strip_backend: SkullStripBackend,
        segmentation_backend: SegmentationBackend,
        pipeline_factory: Callable[..., Any],
        artifacts: ArtifactService,
        settings_obj: Settings = project_settings,
    ):
        self.cases = cases
        self.jobs = jobs
        self.workspace_provider = workspace_provider
        self.reorientation_backend = reorientation_backend
        self.skull_strip_backend = skull_strip_backend
        self.segmentation_backend = segmentation_backend
        self.pipeline_factory = pipeline_factory
        self.artifacts = artifacts
        self.settings = settings_obj

    def start_for_case(self, user: UserRecord, case_id: int) -> DbResult[JobRecord]:
        case_result = self.cases.get_for_user(user, case_id)
        if not case_result.success:
            return DbResult.fail(case_result.error or "Could not load MRI case.")
        if case_result.data is None:
            return DbResult.ok(None)

        active = self.jobs.active_for_case_type(case_id=case_id, job_type=self.JOB_TYPE)
        if not active.success:
            return DbResult.fail(active.error or "Could not check active processing jobs.")
        if active.data is not None:
            return DbResult.fail(self.ACTIVE_JOB_MESSAGE)

        case = case_result.data
        workspace = case.workspace
        if workspace is None:
            return DbResult.fail("Workspace could not be resolved for MRI case.")
        if not workspace.raw_path.exists():
            return DbResult.fail("Upload an MRI file before processing this scan.")
        if workspace.has_complete_mesh_analysis_outputs:
            return DbResult.fail("This scan already has 3D models and measurements.")

        queued = self.cases.set_status_for_user(user, case_id, FullProcessingStatus.QUEUED)
        if not queued.success:
            return DbResult.fail(queued.error or "Could not mark processing as queued.")

        return self.jobs.start(
            user=user,
            job_type=self.JOB_TYPE,
            case_id=case.id,
            message="Processing queued.",
            metadata={
                "subject_id": case.subject_id,
                "acquisition_date": case.acquisition_date.isoformat(),
            },
            handler=lambda context: self._run_full_processing_job(
                user=user,
                case_id=case.id,
                context=context,
            ),
        )

    def _run_full_processing_job(
        self,
        *,
        user: UserRecord,
        case_id: int,
        context: JobContext,
    ) -> dict[str, Any]:
        try:
            require_not_cancelled(context, "Processing job was cancelled.")
            context.checkpoint("Preparing processing environment...", progress=5)
            self._preflight_checks()

            running = self.cases.set_status_for_user(user, case_id, FullProcessingStatus.PREPROCESSING)
            if not running.success:
                raise RuntimeError(running.error or "Could not mark processing as running.")
            if running.data is None:
                raise RuntimeError("MRI case disappeared before processing started.")

            case_record = running.data
            workspace = case_record.workspace
            if workspace is None:
                raise RuntimeError("Workspace could not be resolved for MRI case.")

            domain_case = MRICase(
                subject_id=case_record.subject_id,
                acquisition_date=case_record.acquisition_date.isoformat(),
                raw_path=workspace.raw_path,
            )

            workspace = self.workspace_provider.create_workspace(domain_case)

            if not workspace.has_fast_pve_outputs:
                require_not_cancelled(context, "Processing job was cancelled.")
                context.update(
                    message="Preparing the MRI scan...",
                    progress=15,
                    metadata={
                        "subject_id": case_record.subject_id,
                        "acquisition_date": case_record.acquisition_date.isoformat(),
                        "case_status": FullProcessingStatus.PREPROCESSING,
                    },
                )
                reorientation = self.reorientation_backend.run(domain_case, workspace)

                require_not_cancelled(context, "Processing job was cancelled.")
                context.checkpoint("Preparing the MRI scan...", progress=30)
                skull_strip = self.skull_strip_backend.run(reorientation.output_path, workspace)

                require_not_cancelled(context, "Processing job was cancelled.")
                context.checkpoint("Preparing tissue data...", progress=45)
                self.segmentation_backend.run(skull_strip.image_path, workspace)
            else:
                context.checkpoint("Prepared scan found. Creating results...", progress=50)

            require_not_cancelled(context, "Processing job was cancelled.")
            mesh_running = self.cases.set_status_for_user(user, case_id, FullProcessingStatus.MESH_ANALYSIS)
            if not mesh_running.success:
                raise RuntimeError(mesh_running.error or "Could not mark model creation as running.")
            if mesh_running.data is None:
                raise RuntimeError("MRI case disappeared before model creation started.")

            case_record = mesh_running.data
            workspace = case_record.workspace
            if workspace is None:
                raise RuntimeError("Workspace could not be resolved for MRI case.")

            domain_case = MRICase(
                subject_id=case_record.subject_id,
                acquisition_date=case_record.acquisition_date.isoformat(),
                raw_path=workspace.raw_path,
            )
            workspace = self.workspace_provider.get_workspace(domain_case)
            workspace.ensure_directories()

            if not workspace.has_fast_pve_outputs:
                missing = [str(path) for path in workspace.missing_fast_pve_paths]
                raise RuntimeError(f"Prepared tissue data is missing: {missing}")

            context.update(
                message="Creating the 3D model and measurements...",
                progress=70,
                metadata={
                    "subject_id": case_record.subject_id,
                    "acquisition_date": case_record.acquisition_date.isoformat(),
                    "case_status": FullProcessingStatus.MESH_ANALYSIS,
                },
            )
            pipeline = self.pipeline_factory(workspace)
            result = pipeline.run()

            require_not_cancelled(context, "Processing job was cancelled.")
            completed = self.cases.set_status_for_user(user, case_id, FullProcessingStatus.COMPLETED)
            if not completed.success:
                raise RuntimeError(completed.error or "Could not mark processing as completed.")

            payload = self._result_to_dict(
                user=user,
                case_db_id=case_id,
                workspace=workspace,
                result=result,
            )
            context.update(
                message="Processing completed.",
                progress=100,
                metadata={
                    "case_status": FullProcessingStatus.COMPLETED,
                    "artifacts_url": f"/cases/{case_id}/artifacts",
                },
            )
            return payload

        except Exception:
            if context.cancel_requested:
                mark_case_status_best_effort(
                    cases=self.cases,
                    user=user,
                    case_id=case_id,
                    status=FullProcessingStatus.CANCELLED,
                )
            else:
                mark_case_status_best_effort(
                    cases=self.cases,
                    user=user,
                    case_id=case_id,
                    status=FullProcessingStatus.FAILED,
                )
            raise

    def _preflight_checks(self) -> None:
        ensure_main_directories(self.settings)
        if not self.settings.mni_template_path.exists():
            raise FileNotFoundError(f"MNI template not found: {self.settings.mni_template_path}")

    def _result_to_dict(
        self,
        *,
        user: UserRecord,
        case_db_id: int,
        workspace: CaseWorkspace,
        result: Any,
    ) -> dict[str, Any]:
        artifact_bundle_result = self.artifacts.list_for_case(user, case_db_id)
        if not artifact_bundle_result.success:
            raise RuntimeError(
                artifact_bundle_result.error
                or "Processing completed, but result files could not be listed."
            )
        if artifact_bundle_result.data is None:
            raise RuntimeError("Processing completed, but the result files are no longer authorized.")

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


__all__ = ["FullProcessingService", "FullProcessingStatus"]
