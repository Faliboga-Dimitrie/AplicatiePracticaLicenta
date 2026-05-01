from __future__ import annotations

from pathlib import Path
from typing import Mapping

import nibabel as nib
import numpy as np

from ..project_core import TISSUE_NAMES, TissueName, TissueVolumes


def _path_for_tissue(pve_paths: Mapping[str, Path], tissue: TissueName) -> Path:
    try:
        return Path(pve_paths[tissue.value])
    except KeyError as exc:
        raise KeyError(
            f"Missing PVE path for tissue '{tissue.value}'. "
            f"Available keys: {list(pve_paths.keys())}"
        ) from exc


def _voxel_volume_mm3(img: nib.Nifti1Image) -> float:
    """
    Compute voxel volume from the affine.

    This is more robust than multiplying header zooms when the affine contains
    rotations or shears.
    """
    return float(abs(np.linalg.det(img.affine[:3, :3])))


def _clean_probability_data(img: nib.Nifti1Image) -> np.ndarray:
    data = np.asarray(img.get_fdata(), dtype=np.float32)
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(data, 0.0, 1.0)


class PveSumVolumeEstimator:
    """
    Volume estimator based on FAST PVE probability maps.

    Formula:
        tissue volume = sum(PVE values) * voxel volume

    This is the current default strategy. A future strategy can implement the
    same VolumeEstimator protocol and be injected into MeshAnalysisPipeline
    without modifying the pipeline itself.
    """

    def compute(self, pve_paths: Mapping[str, Path]) -> TissueVolumes:
        volumes_by_tissue: dict[str, float] = {}

        for tissue in TISSUE_NAMES:
            pve_path = _path_for_tissue(pve_paths, tissue)
            pve_img = nib.load(str(pve_path))
            volume = self._volume_for_image(pve_img)
            volumes_by_tissue[tissue.value] = volume

        return TissueVolumes(
            csf_mm3=volumes_by_tissue[TissueName.CSF.value],
            gm_mm3=volumes_by_tissue[TissueName.GM.value],
            wm_mm3=volumes_by_tissue[TissueName.WM.value],
        )

    def _volume_for_image(self, pve_img: nib.Nifti1Image) -> float:
        data = _clean_probability_data(pve_img)
        voxel_volume_mm3 = _voxel_volume_mm3(pve_img)
        return round(float(data.sum() * voxel_volume_mm3), 3)


__all__ = ["PveSumVolumeEstimator"]
