from __future__ import annotations

from skimage.measure import mesh_surface_area

from ..project_core import TissueSurfaces
from .models import MeshAnalysisMeshes


class TrimeshSurfaceEstimator:
    """
    SurfaceEstimator implementation using triangle meshes.

    The estimator accepts the current MeshAnalysisMeshes bundle but computes the
    metric only from the solid meshes, not from the simplified wireframe source.
    """

    def compute(self, meshes: MeshAnalysisMeshes) -> TissueSurfaces:
        solid = meshes.solid

        return TissueSurfaces(
            csf_mm2=self._area_mm2(solid.csf),
            gm_mm2=self._area_mm2(solid.gm),
            wm_mm2=self._area_mm2(solid.wm),
        )

    def _area_mm2(self, mesh) -> float:
        return round(float(mesh_surface_area(mesh.vertices, mesh.faces)), 3)


__all__ = ["TrimeshSurfaceEstimator"]
