from __future__ import annotations

import os
from typing import Any

from ...project_core.config import Settings, settings as project_settings
from ...project_core.workspace import FileSystemWorkspaceProvider
from .artifacts import ArtifactService
from .auth import TokenService
from .cases import CaseService
from .jobs import JobService
from .full_processing import FullProcessingService
from .public_processing import PublicProcessingService
from .statistics import StatisticsService


def _build_mesh_pipeline_factory(settings_obj: Settings):
    from ...mesh_analysis.exporters import GlbMeshExporter
    from ...mesh_analysis.mesh_extractors import MarchingCubesConfig, MarchingCubesMeshExtractor
    from ...mesh_analysis.analysis import MeshAnalysisPipeline
    from ...mesh_analysis.surface_estimators import TrimeshSurfaceEstimator
    from ...mesh_analysis.volume_estimators import PveSumVolumeEstimator

    def pipeline_factory(workspace: Any) -> MeshAnalysisPipeline:
        return MeshAnalysisPipeline(
            workspace=workspace,
            settings=settings_obj,
            volume_estimator=PveSumVolumeEstimator(),
            mesh_extractor=MarchingCubesMeshExtractor(
                MarchingCubesConfig(
                    level=0.5,
                    solid_step_size=1,
                )
            ),
            surface_estimator=TrimeshSurfaceEstimator(),
            mesh_exporter=GlbMeshExporter(),
        )

    return pipeline_factory


def build_default_full_processing_service(
    *,
    cases: CaseService,
    jobs: JobService,
    settings_obj: Settings = project_settings,
) -> FullProcessingService:
    from ...mri_preprocessing.reorient import FslReorientationBackend
    from ...mri_preprocessing.segmentation import FslFastSegmentationBackend
    from ...mri_preprocessing.skull_strip import HdBetSkullStripBackend

    workspace_provider = FileSystemWorkspaceProvider(settings_obj)
    artifact_workspace_provider = FileSystemWorkspaceProvider(
        settings_obj,
        create_directories=False,
    )

    return FullProcessingService(
        cases=cases,
        jobs=jobs,
        workspace_provider=workspace_provider,
        reorientation_backend=FslReorientationBackend(settings_obj),
        skull_strip_backend=HdBetSkullStripBackend(settings_obj),
        segmentation_backend=FslFastSegmentationBackend(settings_obj),
        pipeline_factory=_build_mesh_pipeline_factory(settings_obj),
        artifacts=ArtifactService(
            cases=cases,
            workspace_provider=artifact_workspace_provider,
        ),
        settings_obj=settings_obj,
    )


def build_default_public_processing_service(
    *,
    settings_obj: Settings = project_settings,
) -> PublicProcessingService:
    return PublicProcessingService(settings_obj=settings_obj)

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


def build_default_statistics_service(
    *,
    cases: CaseService,
) -> StatisticsService:
    return StatisticsService(cases=cases)

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
    refresh_token_days = int(os.getenv("MRI_API_REFRESH_TOKEN_DAYS", "7"))

    return TokenService(
        secret_key=secret_key,
        access_token_minutes=access_token_minutes,
        refresh_token_days=refresh_token_days,
    )


__all__ = [
    "build_default_artifact_service",
    "build_default_full_processing_service",
    "build_default_job_service",
    "build_default_statistics_service",
    "build_default_public_processing_service",
    "build_default_token_service",
]
