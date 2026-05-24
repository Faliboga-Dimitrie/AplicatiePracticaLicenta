from __future__ import annotations

from typing import Any, Callable

from ...access_control import DbResult, UserRecord
from ...project_core.config import Settings, ensure_main_directories, settings as project_settings
from ...project_core.domain import MRICase
from ...project_core.ports import WorkspaceProvider
from .artifacts import ArtifactService
from .cases import CaseService
from .common import mark_case_status_best_effort, require_not_cancelled
from .jobs import JobContext, JobRecord, JobService


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
    ACTIVE_JOB_MESSAGE = "A mesh-analysis job is already running for this case."

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

        active = self.jobs.active_for_user_case_type(
            user,
            job_type=self.JOB_TYPE,
            case_id=case_id,
        )
        if not active.success:
            return DbResult.fail(active.error or "Could not check active mesh-analysis jobs.")
        if active.data is not None:
            return DbResult.fail(self.ACTIVE_JOB_MESSAGE)

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
            require_not_cancelled(context, "Mesh-analysis job was cancelled.")
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

            require_not_cancelled(context, "Mesh-analysis job was cancelled.")
            context.checkpoint("Computing volumes, surfaces and GLB meshes...", progress=35)
            pipeline = self.pipeline_factory(workspace)
            result = pipeline.run()

            require_not_cancelled(context, "Mesh-analysis job was cancelled.")
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
                mark_case_status_best_effort(
                    cases=self.cases,
                    user=user,
                    case_id=case_id,
                    status=MeshAnalysisStatus.CANCELLED,
                )
            else:
                mark_case_status_best_effort(
                    cases=self.cases,
                    user=user,
                    case_id=case_id,
                    status=MeshAnalysisStatus.FAILED,
                )
            raise

    def _preflight_checks(self) -> None:
        ensure_main_directories(self.settings)

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


__all__ = ["MeshAnalysisService", "MeshAnalysisStatus"]
