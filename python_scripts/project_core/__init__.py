from .config import Settings, build_settings, settings, ensure_main_directories

from .domain import (
    TissueName,
    TISSUE_NAMES,
    tissue_key,
    strip_nii_suffix,
    MRICase,
    TissueVolumes,
    TissueSurfaces,
    TissueMeshSurfaces,
    CaseMetrics,
    MeshAnalysisResult,
    CaseProcessingResult,
)

from .workspace import (
    CaseWorkspace,
    CasePaths,
    FileSystemWorkspaceProvider,
    build_case_workspace,
    build_case_paths,
)

from .artifacts import (
    ArtifactKind,
    ArtifactRef,
    StoredCaseResult,
    FileSystemArtifactStore,
    normalize_artifact_kind,
    guess_mime_type,
)

from .ports import (
    ReorientationResult,
    SkullStripResult,
    SegmentationResult,
    MeshExportResult,
    WorkspaceProvider,
    ArtifactStore,
    ReorientationBackend,
    SkullStripBackend,
    SegmentationBackend,
    VolumeEstimator,
    MeshExtractor,
    SurfaceEstimator,
    MeshExporter,
    QualityControlGenerator,
)

from .common import build_prepared_case_paths, run_pipeline_cli

__all__ = [
    # config
    "Settings",
    "build_settings",
    "settings",
    "ensure_main_directories",
    # domain
    "TissueName",
    "TISSUE_NAMES",
    "tissue_key",
    "strip_nii_suffix",
    "MRICase",
    "TissueVolumes",
    "TissueSurfaces",
    "TissueMeshSurfaces",
    "CaseMetrics",
    "MeshAnalysisResult",
    "CaseProcessingResult",
    # workspace
    "CaseWorkspace",
    "CasePaths",
    "FileSystemWorkspaceProvider",
    "build_case_workspace",
    "build_case_paths",
    # artifacts
    "ArtifactKind",
    "ArtifactRef",
    "StoredCaseResult",
    "FileSystemArtifactStore",
    "normalize_artifact_kind",
    "guess_mime_type",
    # ports
    "ReorientationResult",
    "SkullStripResult",
    "SegmentationResult",
    "MeshExportResult",
    "WorkspaceProvider",
    "ArtifactStore",
    "ReorientationBackend",
    "SkullStripBackend",
    "SegmentationBackend",
    "VolumeEstimator",
    "MeshExtractor",
    "SurfaceEstimator",
    "MeshExporter",
    "QualityControlGenerator",
    # CLI helpers
    "build_prepared_case_paths",
    "run_pipeline_cli",
]
