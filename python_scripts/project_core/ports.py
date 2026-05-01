from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Mapping, Protocol, TypeVar

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
    """
    Result produced by a skull-stripping backend.
    """

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
# For the current implementation this will probably be mesh_analysis.models.TissueMeshes,
# but another implementation could use a different mesh object.
MeshCollectionT_co = TypeVar("MeshCollectionT_co", covariant=True)
MeshCollectionT_contra = TypeVar("MeshCollectionT_contra", contravariant=True)


# -----------------------------------------------------------------------------
# Infrastructure ports
# -----------------------------------------------------------------------------

class WorkspaceProvider(Protocol):
    """
    Creates the temporary/local working area used while processing one MRI case.

    A filesystem implementation can create folders under processed_mri/.
    A future implementation could create an isolated temporary workspace,
    a Docker-mounted workspace, etc.
    """

    def create_workspace(self, case: MRICase) -> CaseWorkspace:
        ...


class ArtifactStore(Protocol):
    """
    Publishes final outputs produced by the pipeline.

    The pipeline works inside a CaseWorkspace, then asks an ArtifactStore to
    expose/register final results. The first implementation can simply keep
    files on disk. A later implementation can store metadata in a database or
    upload files to blob storage without changing the pipeline orchestration.
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


# -----------------------------------------------------------------------------
# External processing backend ports
# -----------------------------------------------------------------------------

class ReorientationBackend(Protocol):
    """
    Reorients a raw MRI into the orientation expected by the rest of the system.

    Current implementation: FSL fslreorient2std through Docker/PowerShell.
    Future implementation: nibabel-only, ANTs-based, manual-review backend, etc.
    """

    def run(self, case: MRICase, workspace: CaseWorkspace) -> ReorientationResult:
        ...


class SkullStripBackend(Protocol):
    """
    Removes non-brain tissue from a structural MRI.

    Current implementation: HD-BET.
    Future implementation: SynthStrip, ROBEX, a mock backend for tests, etc.
    """

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SkullStripResult:
        ...


class SegmentationBackend(Protocol):
    """
    Segments a skull-stripped structural MRI into tissue probability maps.

    Current implementation: FSL FAST.
    Future implementation: SPM, ANTs Atropos, neural-network segmentation, etc.
    """

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SegmentationResult:
        ...


# -----------------------------------------------------------------------------
# Metric and mesh strategy ports
# -----------------------------------------------------------------------------

class VolumeEstimator(Protocol):
    """
    Computes tissue volumes from tissue probability/label images.

    Current implementation: sum(PVE values) * voxel volume.
    Future implementations can use label counting, atlas correction,
    uncertainty-aware estimates, etc.
    """

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
    """
    Computes tissue surface areas from a mesh collection.
    """

    def compute(self, meshes: MeshCollectionT_contra) -> TissueSurfaces:
        ...


class MeshExporter(Protocol, Generic[MeshCollectionT_contra]):
    """
    Exports a mesh collection into web-consumable assets such as GLB files.
    """

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


__all__ = [
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
]
