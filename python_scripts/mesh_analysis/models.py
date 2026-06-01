from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import trimesh


@dataclass(frozen=True)
class TissueMeshes:
    """
    Concrete in-memory mesh collection used by the current trimesh-based
    mesh-analysis implementation.

    This intentionally stays in mesh_analysis instead of project_core because it
    depends on the concrete mesh library representation.
    """

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
class MeshAnalysisMeshes:
    """
    Mesh collection returned by the current marching-cubes extractor.

    solid contains the meshes used for metrics and GLB export.
    """

    solid: TissueMeshes


__all__ = [
    "TissueMeshes",
    "MeshAnalysisMeshes",
]
