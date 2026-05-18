from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Mapping, Protocol, TypeVar, Any

from datetime import date

if TYPE_CHECKING:
    from .artifacts import ArtifactKind, ArtifactRef
    from .domain import MRICase, TissueSurfaces, TissueVolumes
    from .workspace import CaseWorkspace


# -----------------------------------------------------------------------------
# Shared stage result DTOs
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ReorientationResult:
    """
    Result produced by a reorientation backend.

    The backend may either copy the input unchanged when it is already in the
    expected orientation, or produce a new reoriented file.
    """

    output_path: Path
    already_standard: bool = False


@dataclass(frozen=True)
class SkullStripResult:
    """Result produced by a skull-stripping backend."""

    image_path: Path
    mask_path: Path | None = None


@dataclass(frozen=True)
class SegmentationResult:
    """
    Result produced by a tissue-segmentation backend.

    pve_paths maps tissue names such as "csf", "gm", and "wm" to their
    probability-volume-estimation images.
    """

    pve_paths: Mapping[str, Path]
    seg_path: Path | None = None
    pveseg_path: Path | None = None


@dataclass(frozen=True)
class MeshExportResult:
    """
    Result produced by a mesh exporter.

    mesh_paths contains the final exported solid mesh files.
    wireframe_paths is optional because not every exporter/strategy needs to
    generate wireframes.
    """

    mesh_paths: Mapping[str, Path]
    wireframe_paths: Mapping[str, Path] | None = None


# The concrete mesh representation is intentionally not defined in project_core.
MeshCollectionT_co = TypeVar("MeshCollectionT_co", covariant=True)
MeshCollectionT_contra = TypeVar("MeshCollectionT_contra", contravariant=True)


# -----------------------------------------------------------------------------
# Workspace lifecycle helper
# -----------------------------------------------------------------------------

class WorkspaceProvider(Protocol):
    """
    Small workspace lifecycle protocol used by existing preprocessing code.

    This is not a separate storage abstraction. The current implementation is
    FileSystemWorkspaceProvider, and CaseWorkspace owns the real file creation
    and deletion logic.
    """

    def create_workspace(self, case: MRICase) -> CaseWorkspace:
        ...

    def get_workspace(self, case: MRICase) -> CaseWorkspace:
        ...

    def delete_workspace(
        self,
        case: MRICase,
        *,
        include_input: bool = True,
        prune_empty_subject_dirs: bool = True,
    ) -> list[Path]:
        ...


# -----------------------------------------------------------------------------
# External processing backend ports
# -----------------------------------------------------------------------------

class ReorientationBackend(Protocol):
    """Reorients a raw MRI into the orientation expected by the rest of the system."""

    def run(self, case: MRICase, workspace: CaseWorkspace) -> ReorientationResult:
        ...


class SkullStripBackend(Protocol):
    """Removes non-brain tissue from a structural MRI."""

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SkullStripResult:
        ...


class SegmentationBackend(Protocol):
    """Segments a skull-stripped structural MRI into tissue probability maps."""

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SegmentationResult:
        ...


# -----------------------------------------------------------------------------
# Metric and mesh strategy ports
# -----------------------------------------------------------------------------

class VolumeEstimator(Protocol):
    """Computes tissue volumes from tissue probability/label images."""

    def compute(self, pve_paths: Mapping[str, Path]) -> TissueVolumes:
        ...


class MeshExtractor(Protocol, Generic[MeshCollectionT_co]):
    """
    Builds an in-memory mesh collection from tissue probability/label images.

    The mesh representation is generic so project_core does not depend on
    trimesh or any other concrete mesh library.
    """

    def extract_all(self, pve_paths: Mapping[str, Path]) -> MeshCollectionT_co:
        ...


class SurfaceEstimator(Protocol, Generic[MeshCollectionT_contra]):
    """Computes tissue surface areas from a mesh collection."""

    def compute(self, meshes: MeshCollectionT_contra) -> TissueSurfaces:
        ...


class MeshExporter(Protocol, Generic[MeshCollectionT_contra]):
    """Exports a mesh collection into web-consumable assets such as GLB files."""

    def export(
        self,
        meshes: MeshCollectionT_contra,
        workspace: CaseWorkspace,
    ) -> MeshExportResult:
        ...


class QualityControlGenerator(Protocol):
    """
    Generates optional QC artifacts for a processed case.

    This is intentionally separate from the main processing stages so QC can be
    disabled, replaced, or allowed to fail without changing scientific metrics.
    """

    def generate(self, case: MRICase, workspace: CaseWorkspace) -> Mapping[str, Path]:
        ...


# -----------------------------------------------------------------------------
# Optional API/static artifact helper
# -----------------------------------------------------------------------------

class ArtifactStore(Protocol):
    """
    Optional helper for a FastAPI/static-file layer.

    Do not build the core pipeline around this for now. CaseWorkspace already
    knows where outputs are written. ArtifactStore is only useful if an API wants
    to copy/register those files under a public static root and return ArtifactRef
    objects to the frontend.
    """

    def save_file(
        self,
        *,
        case: MRICase,
        source_path: Path,
        artifact_name: str,
        artifact_kind: ArtifactKind | str,
        mime_type: str | None = None,
    ) -> ArtifactRef:
        ...

    def save_metrics(
        self,
        *,
        case: MRICase,
        metrics: Mapping[str, object],
        artifact_name: str = "metrics",
    ) -> ArtifactRef:
        ...

class WorkspaceGateway(Protocol):
    """
    Optional adapter used when the service should also touch the filesystem.

    The API/database layer should not know the internal folder layout. It asks
    this gateway to create, delete, lookup, or rename workspaces.
    """

    def create_case_workspace(
        self,
        *,
        subject_id: str,
        acquisition_date: date,
        source_raw_path: Path | None = None,
    ) -> Any:
        ...

    def delete_case_workspace(self, *, subject_id: str, acquisition_date: date) -> None:
        ...

    def delete_subject_workspaces(self, *, subject_id: str) -> None:
        ...

    def rename_case_workspace(
        self,
        *,
        subject_id: str,
        old_acquisition_date: date,
        new_acquisition_date: date,
        overwrite: bool = False,
    ) -> Any:
        ...

    def get_case_workspace(self, *, subject_id: str, acquisition_date: date) -> Any:
        ...


__all__ = [
    "ReorientationResult",
    "SkullStripResult",
    "SegmentationResult",
    "MeshExportResult",
    "WorkspaceProvider",
    "ReorientationBackend",
    "SkullStripBackend",
    "SegmentationBackend",
    "VolumeEstimator",
    "MeshExtractor",
    "SurfaceEstimator",
    "MeshExporter",
    "QualityControlGenerator",
    "ArtifactStore",
    "WorkspaceGateway",
]
