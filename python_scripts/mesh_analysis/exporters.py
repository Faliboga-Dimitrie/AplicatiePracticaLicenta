from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import numpy as np
import trimesh

from ..project_core import CaseWorkspace, MeshExportResult
from .models import MeshAnalysisMeshes, TissueMeshes, TissueWireframes


RGBA = tuple[int, int, int, int]


@dataclass(frozen=True)
class GlbExportConfig:
    """
    Configuration for the current trimesh GLB exporter.

    rotate_x_degrees is visual-only and matches the orientation correction you
    were already applying before export.
    scale_factor is also export-only; keep it at 1.0 if you want metric values
    to remain directly comparable to the displayed mesh dimensions.
    """

    rotate_x_degrees: float | None = -90.0
    scale_factor: float = 1.0
    export_wireframes: bool = True
    solid_materials: Mapping[str, RGBA] = field(default_factory=lambda: {
        "csf": (80, 140, 255, 60),
        "gm": (80, 140, 255, 90),
        "wm": (80, 140, 255, 180),
    })
    wireframe_materials: Mapping[str, RGBA] = field(default_factory=lambda: {
        "csf": (80, 140, 255, 60),
        "gm": (80, 140, 255, 60),
        "wm": (80, 140, 255, 60),
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
    ) -> MeshExportResult:

        solid_meshes = meshes.solid
        mesh_paths = self._export_solid_meshes(solid_meshes, workspace)

        wireframe_paths: dict[str, Path] | None = None
        if self.config.export_wireframes:
            wireframe_source = meshes.wireframe_source
            wireframes = self._build_wireframes(wireframe_source)
            wireframe_paths = self._export_wireframes(wireframes, workspace)

        return MeshExportResult(
            mesh_paths=mesh_paths,
            wireframe_paths=wireframe_paths,
        )

    def _export_solid_meshes(
        self,
        meshes: TissueMeshes,
        workspace: CaseWorkspace,
    ) -> dict[str, Path]:
        exported: dict[str, Path] = {}

        for tissue, mesh in meshes.as_dict().items():
            out_path = workspace.mesh_paths[tissue]
            export_mesh = mesh.copy()

            self._apply_view_transform(export_mesh)
            self._apply_transparent_material(
                export_mesh,
                self.config.solid_materials[tissue],
            )

            export_mesh.export(str(out_path), file_type="glb")
            exported[tissue] = out_path

        return exported

    def _build_wireframes(self, meshes: TissueMeshes) -> TissueWireframes:
        prepared: dict[str, object] = {}

        for tissue, mesh in meshes.as_dict().items():
            export_mesh = mesh.copy()
            self._apply_view_transform(export_mesh)
            prepared[tissue] = self._mesh_to_wireframe(export_mesh)

        return TissueWireframes(
            csf=prepared["csf"],
            gm=prepared["gm"],
            wm=prepared["wm"],
        )

    def _export_wireframes(
        self,
        wireframes: TissueWireframes,
        workspace: CaseWorkspace,
    ) -> dict[str, Path]:
        exported: dict[str, Path] = {}

        for tissue, wireframe in wireframes.as_dict().items():
            out_path = workspace.wireframe_paths[tissue]
            self._set_wireframe_color(wireframe, self.config.wireframe_materials[tissue])

            scene = trimesh.Scene(wireframe)
            scene.export(str(out_path), file_type="glb")
            exported[tissue] = out_path

        return exported

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

    def _mesh_to_wireframe(self, mesh: trimesh.Trimesh):
        edges = mesh.edges_unique
        segments = mesh.vertices[edges]
        return trimesh.load_path(segments)

    def _set_wireframe_color(self, wireframe, rgba: RGBA) -> None:
        color = np.array(rgba, dtype=np.uint8)
        wireframe.colors = np.tile(color, (len(wireframe.entities), 1))


__all__ = [
    "GlbExportConfig",
    "GlbMeshExporter",
]
