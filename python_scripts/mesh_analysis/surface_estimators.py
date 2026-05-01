from __future__ import annotations

from typing import overload

from skimage.measure import mesh_surface_area

from ..project_core import TissueSurfaces
from .models import MeshAnalysisMeshes, TissueMeshes


def _solid_meshes(meshes: MeshAnalysisMeshes | TissueMeshes) -> TissueMeshes:
    if isinstance(meshes, MeshAnalysisMeshes):
        return meshes.solid
    return meshes


class TrimeshSurfaceEstimator:
    """
    SurfaceEstimator implementation using triangle meshes.

    The estimator accepts the current MeshAnalysisMeshes bundle but computes the
    metric only from the solid meshes, not from the simplified wireframe source.
    """

    def compute(self, meshes: MeshAnalysisMeshes | TissueMeshes) -> TissueSurfaces:
        solid = _solid_meshes(meshes)

        return TissueSurfaces(
            csf_mm2=self._area_mm2(solid.csf),
            gm_mm2=self._area_mm2(solid.gm),
            wm_mm2=self._area_mm2(solid.wm),
        )

    def _area_mm2(self, mesh) -> float:
        return round(float(mesh_surface_area(mesh.vertices, mesh.faces)), 3)


__all__ = ["TrimeshSurfaceEstimator"]
