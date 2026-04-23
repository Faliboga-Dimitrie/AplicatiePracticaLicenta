from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import nibabel as nib
    import trimesh


@dataclass(frozen=True)
class TissueVolumes:
    csf_mm3: float
    gm_mm3: float
    wm_mm3: float

    def to_dict(self) -> dict[str, float]:
        return {
            "csf_mm3": self.csf_mm3,
            "gm_mm3": self.gm_mm3,
            "wm_mm3": self.wm_mm3,
        }


@dataclass(frozen=True)
class TissueSurfaces:
    csf_mm2: float
    gm_mm2: float
    wm_mm2: float

    def to_dict(self) -> dict[str, float]:
        return {
            "csf_mm2": self.csf_mm2,
            "gm_mm2": self.gm_mm2,
            "wm_mm2": self.wm_mm2,
        }


@dataclass(frozen=True)
class TissueMasks:
    csf_img: nib.Nifti1Image
    gm_img: nib.Nifti1Image
    wm_img: nib.Nifti1Image

    def as_dict(self) -> dict[str, nib.Nifti1Image]:
        return {
            "csf": self.csf_img,
            "gm": self.gm_img,
            "wm": self.wm_img,
        }


@dataclass(frozen=True)
class TissueMeshes:
    csf: trimesh.Trimesh
    gm: trimesh.Trimesh
    wm: trimesh.Trimesh

    def as_dict(self) -> dict[str, trimesh.Trimesh]:
        return {
            "csf": self.csf,
            "gm": self.gm,
            "wm": self.wm,
        }


@dataclass(frozen=True)
class MeshAnalysisResult:
    subject_id: str
    volumes: TissueVolumes
    surfaces: TissueSurfaces

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "volumes": self.volumes.to_dict(),
            "surfaces": self.surfaces.to_dict(),
        }


__all__ = [
    "TissueVolumes",
    "TissueSurfaces",
    "TissueMasks",
    "TissueMeshes",
    "MeshAnalysisResult",
]