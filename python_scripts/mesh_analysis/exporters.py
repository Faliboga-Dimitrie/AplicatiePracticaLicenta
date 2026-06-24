from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import trimesh
import trimesh.visual.material

from ..project_core import CaseWorkspace
from .models import MeshAnalysisMeshes, TissueMeshes


RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class GlbExportConfig:
    """
    Configuration for the current trimesh GLB exporter.

    rotate_x_degrees is visual-only;
    scale_factor is also export-only; keep it at 1.0 if you want metric values
    to remain directly comparable to the displayed mesh dimensions.
    """

    rotate_x_degrees: float | None = -90.0
    scale_factor: float = 1.0
    solid_materials: Mapping[str, RGBA] = field(default_factory=lambda: {
        "csf": (80, 140, 255, 60),
        "gm": (80, 140, 255, 90),
        "wm": (80, 140, 255, 180),
    })


class GlbMeshExporter:
    """
    MeshExporter implementation that writes web-friendly GLB files with trimesh.

    The exporter works with the mesh bundle returned by the current extractor,
    but the pipeline sees it only through the MeshExporter protocol.
    """

    def __init__(self, config: GlbExportConfig | None = None):
        self.config = config or GlbExportConfig()

    def export(
        self,
        meshes: MeshAnalysisMeshes,
        workspace: CaseWorkspace,
    ) -> None:
        solid_meshes = meshes.solid
        self._export_solid_meshes(solid_meshes, workspace)

    def _export_solid_meshes(
        self,
        meshes: TissueMeshes,
        workspace: CaseWorkspace,
    ) -> None:
        for tissue, mesh in meshes.as_dict().items():
            out_path = workspace.mesh_paths[tissue]
            export_mesh = mesh.copy()

            self._apply_view_transform(export_mesh)
            self._apply_transparent_material(
                export_mesh,
                self.config.solid_materials[tissue],
            )

            export_mesh.export(str(out_path), file_type="glb")


    def _apply_view_transform(self, mesh: trimesh.Trimesh) -> None:
        if self.config.rotate_x_degrees is not None:
            transform = trimesh.transformations.rotation_matrix(
                angle=np.deg2rad(self.config.rotate_x_degrees),
                direction=[1, 0, 0],
                point=mesh.centroid,
            )
            mesh.apply_transform(transform)

        if self.config.scale_factor != 1.0:
            transform = trimesh.transformations.scale_matrix(
                factor=self.config.scale_factor,
                origin=mesh.centroid,
            )
            mesh.apply_transform(transform)

    def _apply_transparent_material(
        self,
        mesh: trimesh.Trimesh,
        rgba: RGBA,
    ) -> None:
        material = trimesh.visual.material.PBRMaterial(
            baseColorFactor=list(rgba),
            alphaMode="BLEND",
            doubleSided=True,
        )

        mesh.visual = trimesh.visual.TextureVisuals(material=material)



__all__ = [
    "GlbExportConfig",
    "GlbMeshExporter",
]
