from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .artifacts import ArtifactRef


class TissueName(str, Enum):
    """
    Canonical tissue identifiers used across the application.

    Keeping these names centralized prevents each layer from inventing its own
    spelling for the same tissue type. Values are lowercase because they are
    convenient as dictionary keys and API/JSON values.
    """

    CSF = "csf"
    GM = "gm"
    WM = "wm"


TISSUE_NAMES: tuple[TissueName, ...] = (
    TissueName.CSF,
    TissueName.GM,
    TissueName.WM,
)


def tissue_key(tissue: TissueName | str) -> str:
    """
    Normalize a tissue identifier to the canonical lowercase string key.
    """
    if isinstance(tissue, TissueName):
        return tissue.value
    return tissue.strip().lower()


def strip_nii_suffix(path: Path) -> str:
    """
    Remove .nii or .nii.gz from a filename and return the case-like base name.
    """
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


@dataclass(frozen=True)
class MRICase:
    """
    Identity of a raw MRI case.

    This object intentionally stores only the subject/case identifier and the raw
    input path. Loaded image data belongs to processing adapters, not to the
    domain model.
    """

    subject_id: str
    raw_path: Path

    @classmethod
    def from_input_path(
        cls,
        input_path: str | Path,
        subject_id: str | None = None,
    ) -> "MRICase":
        path = Path(input_path).resolve()
        sid = subject_id or strip_nii_suffix(path)
        return cls(subject_id=sid, raw_path=path)


@dataclass(frozen=True)
class TissueVolumes:
    """
    Tissue volume metrics in cubic millimetres.
    """

    csf_mm3: float
    gm_mm3: float
    wm_mm3: float

    def to_dict(self) -> dict[str, float]:
        return {
            "csf_mm3": self.csf_mm3,
            "gm_mm3": self.gm_mm3,
            "wm_mm3": self.wm_mm3,
        }

    def as_tissue_dict(self) -> dict[str, float]:
        """
        Return values keyed by canonical tissue name rather than metric field.
        """
        return {
            TissueName.CSF.value: self.csf_mm3,
            TissueName.GM.value: self.gm_mm3,
            TissueName.WM.value: self.wm_mm3,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> "TissueVolumes":
        """
        Build volumes from either metric-style keys or tissue-style keys.

        Accepted examples:
            {"csf_mm3": 10.0, "gm_mm3": 20.0, "wm_mm3": 30.0}
            {"csf": 10.0, "gm": 20.0, "wm": 30.0}
        """
        return cls(
            csf_mm3=float(data.get("csf_mm3", data.get("csf", 0.0))),
            gm_mm3=float(data.get("gm_mm3", data.get("gm", 0.0))),
            wm_mm3=float(data.get("wm_mm3", data.get("wm", 0.0))),
        )


@dataclass(frozen=True)
class TissueSurfaces:
    """
    Tissue surface-area metrics in square millimetres.

    The name deliberately avoids saying "mesh surface" because the domain only
    cares about the final metric. The current implementation may estimate it
    from a marching-cubes mesh, but a future implementation could use another
    method without changing the domain model.
    """

    csf_mm2: float
    gm_mm2: float
    wm_mm2: float

    def to_dict(self) -> dict[str, float]:
        return {
            "csf_mm2": self.csf_mm2,
            "gm_mm2": self.gm_mm2,
            "wm_mm2": self.wm_mm2,
        }

    def as_tissue_dict(self) -> dict[str, float]:
        """
        Return values keyed by canonical tissue name rather than metric field.
        """
        return {
            TissueName.CSF.value: self.csf_mm2,
            TissueName.GM.value: self.gm_mm2,
            TissueName.WM.value: self.wm_mm2,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> "TissueSurfaces":
        """
        Build surfaces from either metric-style keys or tissue-style keys.

        Accepted examples:
            {"csf_mm2": 10.0, "gm_mm2": 20.0, "wm_mm2": 30.0}
            {"csf": 10.0, "gm": 20.0, "wm": 30.0}
        """
        return cls(
            csf_mm2=float(data.get("csf_mm2", data.get("csf", 0.0))),
            gm_mm2=float(data.get("gm_mm2", data.get("gm", 0.0))),
            wm_mm2=float(data.get("wm_mm2", data.get("wm", 0.0))),
        )

@dataclass(frozen=True)
class CaseMetrics:
    """
    Scientific/analytical metrics produced for one processed MRI case.
    """

    volumes: TissueVolumes
    surfaces: TissueSurfaces

    def to_dict(self) -> dict[str, object]:
        return {
            "volumes": self.volumes.to_dict(),
            "surfaces": self.surfaces.to_dict(),
        }


@dataclass(frozen=True)
class MeshAnalysisResult:
    """
    Current mesh-analysis result shape used by the existing CLI/pipeline.

    This class is kept in the core domain during the transition because volumes
    and surfaces are final application-level results, not trimesh-specific
    implementation details.
    """

    subject_id: str
    volumes: TissueVolumes
    surfaces: TissueSurfaces

    @property
    def metrics(self) -> CaseMetrics:
        return CaseMetrics(volumes=self.volumes, surfaces=self.surfaces)

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            **self.metrics.to_dict(),
        }


@dataclass(frozen=True)
class CaseProcessingResult:
    """
    High-level result returned by the future application pipeline/API layer.

    This is intentionally larger than MeshAnalysisResult: it can carry the final
    artifact references that a CLI/API/frontend needs to access meshes, QC
    images, metrics JSON, or other outputs.
    """

    subject_id: str
    metrics: CaseMetrics
    artifacts: tuple["ArtifactRef", ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        artifact_payloads: list[object] = []
        for artifact in self.artifacts:
            to_dict = getattr(artifact, "to_dict", None)
            artifact_payloads.append(to_dict() if callable(to_dict) else artifact)

        return {
            "subject_id": self.subject_id,
            **self.metrics.to_dict(),
            "artifacts": artifact_payloads,
        }


__all__ = [
    "TissueName",
    "TISSUE_NAMES",
    "tissue_key",
    "strip_nii_suffix",
    "MRICase",
    "TissueVolumes",
    "TissueSurfaces",
    "CaseMetrics",
    "MeshAnalysisResult",
    "CaseProcessingResult",
]
