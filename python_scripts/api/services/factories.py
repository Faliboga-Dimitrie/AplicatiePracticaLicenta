from __future__ import annotations

import os
from typing import Any

from ...project_core.config import Settings, settings as project_settings
from ...project_core.workspace import FileSystemWorkspaceProvider
from .artifacts import ArtifactService
from .auth import TokenService
from .cases import CaseService
from .jobs import JobService
from .mesh_analysis import MeshAnalysisService
from .preprocessing import PreprocessingService
from .public_processing import PublicProcessingService
from .statistics import StatisticsService


def build_default_preprocessing_service(
    *,
    cases: CaseService,
    jobs: JobService,
    settings_obj: Settings = project_settings,
) -> PreprocessingService:
    # Local imports keep lightweight API modules importable even before the
    # scientific stack is touched. The concrete backends are only needed when
    # FastAPI builds the preprocessing dependency.
    from ...mri_preprocessing.reorient import FslReorientationBackend
    from ...mri_preprocessing.segmentation import FslFastSegmentationBackend
    from ...mri_preprocessing.skull_strip import HdBetSkullStripBackend

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
    from ...mesh_analysis.exporters import GlbMeshExporter
    from ...mesh_analysis.mesh_extractors import MarchingCubesMeshExtractor
    from ...mesh_analysis.pipeline import MeshAnalysisPipeline
    from ...mesh_analysis.surface_estimators import TrimeshSurfaceEstimator
    from ...mesh_analysis.volume_estimators import PveSumVolumeEstimator

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
    "build_default_job_service",
    "build_default_mesh_analysis_service",
    "build_default_preprocessing_service",
    "build_default_statistics_service",
    "build_default_public_processing_service",
    "build_default_token_service",
]
