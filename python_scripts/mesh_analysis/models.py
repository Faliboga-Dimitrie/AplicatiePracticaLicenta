from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import trimesh
    from trimesh.path import Path3D


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
class TissueMeshSurfaces:
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
class TissueWireframes:
    csf: Path3D
    gm: Path3D
    wm: Path3D

    def as_dict(self) -> dict[str, Path3D]:
        return {
            "csf": self.csf,
            "gm": self.gm,
            "wm": self.wm,
        }


@dataclass(frozen=True)
class MeshAnalysisResult:
    subject_id: str
    volumes: TissueVolumes
    surfaces: TissueMeshSurfaces
    def to_dict(self) -> dict[str, object]:
        return {
            "subject_id": self.subject_id,
            "volumes": self.volumes.to_dict(),
            "surfaces": self.surfaces.to_dict(),
        }


__all__ = [
    "TissueVolumes",
    "TissueMeshSurfaces",
    "TissueMeshes",
    "TissueWireframes",
    "MeshAnalysisResult",
]