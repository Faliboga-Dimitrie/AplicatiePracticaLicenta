from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import nibabel as nib
from nibabel.affines import apply_affine
import numpy as np
import trimesh
from skimage.measure import marching_cubes

from ..project_core import TissueName
from .models import MeshAnalysisMeshes, TissueMeshes


@dataclass(frozen=True)
class MarchingCubesConfig:
    """
    Configuration for the current skimage marching-cubes implementation.

    level is the probability threshold used on the PVE maps.
    solid_step_size controls the exported/metric mesh detail.
    wireframe_step_size can be larger to produce lighter wireframe GLBs.
    Set wireframe_step_size=None to disable the separate wireframe source meshes.
    """

    level: float = 0.5
    solid_step_size: int = 1
    wireframe_step_size: int | None = 3
    create_wireframe_source: bool = True


class MarchingCubesMeshExtractor:
    """
    MeshExtractor implementation based on skimage.measure.marching_cubes.

    The pipeline depends on the MeshExtractor protocol, not on this concrete
    class. Replacing marching cubes later means adding another extractor class,
    not rewriting the pipeline orchestration.
    """

    def __init__(self, config: MarchingCubesConfig | None = None):
        self.config = config or MarchingCubesConfig()

    def extract_all(self, pve_paths: Mapping[str, Path]) -> MeshAnalysisMeshes:
        solid = self._extract_tissue_meshes(
            pve_paths=pve_paths,
            step_size=self.config.solid_step_size,
            label_suffix="",
        )

        wireframe_source: TissueMeshes | None = None
        if self.config.wireframe_step_size is not None and self.config.create_wireframe_source:
            wireframe_source = self._extract_tissue_meshes(
                pve_paths=pve_paths,
                step_size=self.config.wireframe_step_size,
                label_suffix=" wireframe",
            )

        return MeshAnalysisMeshes(
            solid=solid,
            wireframe_source=wireframe_source,
        )

    def _extract_tissue_meshes(
        self,
        *,
        pve_paths: Mapping[str, Path],
        step_size: int,
        label_suffix: str,
    ) -> TissueMeshes:
        return TissueMeshes(
            csf=self._pve_path_to_mesh(
                pve_paths[TissueName.CSF.value],
                "CSF" + label_suffix,
                step_size=step_size,
            ),
            gm=self._pve_path_to_mesh(
                pve_paths[TissueName.GM.value],
                "GM" + label_suffix,
                step_size=step_size,
            ),
            wm=self._pve_path_to_mesh(
                pve_paths[TissueName.WM.value],
                "WM" + label_suffix,
                step_size=step_size,
            ),
        )

    def _pve_path_to_mesh(
        self,
        pve_path: Path,
        tissue_name: str,
        *,
        step_size: int,
    ) -> trimesh.Trimesh:
        pve_img = nib.load(str(pve_path))
        return self._pve_image_to_mesh(
            pve_img=pve_img,
            tissue_name=tissue_name,
            step_size=step_size,
        )

    def _pve_image_to_mesh(
        self,
        *,
        pve_img: nib.Nifti1Image,
        tissue_name: str,
        step_size: int,
    ) -> trimesh.Trimesh:
        pve_data = np.asarray(pve_img.get_fdata(), dtype=np.float32)

        if pve_data.ndim != 3:
            raise ValueError(
                f"Expected 3D PVE image for mesh analysis, got ndim={pve_data.ndim}"
            )

        pve_data = np.nan_to_num(pve_data, nan=0.0, posinf=0.0, neginf=0.0)
        pve_data = np.clip(pve_data, 0.0, 1.0)

        data_min = float(pve_data.min())
        data_max = float(pve_data.max())
        level = self.config.level

        if not (data_min < level < data_max):
            raise ValueError(
                f"{tissue_name} PVE image cannot be meshed at level {level}. "
                f"Data range is [{data_min}, {data_max}]."
            )

        verts_voxel, faces, _, _ = marching_cubes(
            pve_data,
            level=level,
            step_size=step_size,
        )
        verts_world = apply_affine(pve_img.affine, verts_voxel)

        return trimesh.Trimesh(
            vertices=verts_world,
            faces=faces,
            process=False,
        )


__all__ = [
    "MarchingCubesConfig",
    "MarchingCubesMeshExtractor",
]
