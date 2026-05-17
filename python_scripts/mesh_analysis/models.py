from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import trimesh
    from trimesh.path import Path3D


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
class TissueWireframes:
    """
    Concrete wireframe collection used by the current trimesh exporter.
    """

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
class MeshAnalysisMeshes:
    """
    Mesh collection returned by the current marching-cubes extractor.

    solid contains the meshes used for metrics and solid GLB export.
    wireframe_source optionally contains lower-detail meshes used only for
    wireframe export. Keeping this here avoids forcing project_core to know
    about trimesh or wireframe implementation details.
    """

    solid: TissueMeshes
    wireframe_source: TissueMeshes | None = None


__all__ = [
    "TissueMeshes",
    "TissueWireframes",
    "MeshAnalysisMeshes",
]
