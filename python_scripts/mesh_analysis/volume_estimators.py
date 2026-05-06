from __future__ import annotations

from pathlib import Path
from typing import Mapping

import nibabel as nib
import numpy as np

from ..project_core import TissueName, TissueVolumes

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
        return TissueVolumes(
            csf_mm3=self._volume_for_path(pve_paths[TissueName.CSF.value]),
            gm_mm3=self._volume_for_path(pve_paths[TissueName.GM.value]),
            wm_mm3=self._volume_for_path(pve_paths[TissueName.WM.value]),
        )
    
    def _voxel_volume_mm3(self,img: nib.Nifti1Image) -> float:
        """
        Compute voxel volume from the affine.

        This is more robust than multiplying header zooms when the affine contains
        rotations or shears.
        """
        return float(abs(np.linalg.det(img.affine[:3, :3])))


    def _clean_probability_data(self, img: nib.Nifti1Image) -> np.ndarray:
        data = np.asarray(img.get_fdata(), dtype=np.float32)
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        return np.clip(data, 0.0, 1.0)

    def _volume_for_path(self, pve_path: Path) -> float:
        pve_img = nib.load(str(pve_path))
        return self._volume_for_image(pve_img)

    def _volume_for_image(self, pve_img: nib.Nifti1Image) -> float:
        data = self._clean_probability_data(pve_img)
        voxel_volume_mm3 = self._voxel_volume_mm3(pve_img)
        return round(float(data.sum() * voxel_volume_mm3), 3)


__all__ = ["PveSumVolumeEstimator"]
