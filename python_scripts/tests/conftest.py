from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import numpy as np
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_minimal_nibabel_stub() -> None:
    """Provide just enough nibabel API for tests when nibabel is absent."""
    if importlib.util.find_spec("nibabel") is not None:
        return

    nibabel = types.ModuleType("nibabel")
    orientations = types.ModuleType("nibabel.orientations")
    affines = types.ModuleType("nibabel.affines")
    processing = types.ModuleType("nibabel.processing")
    spatialimages = types.ModuleType("nibabel.spatialimages")

    class SpatialImage:
        pass

    class Nifti1Image(SpatialImage):
        pass

    def load(_path: str):
        raise RuntimeError(
            "nibabel is not installed in this test environment; patch nib.load "
            "or test methods that do not require actual NIfTI IO."
        )

    def aff2axcodes(_affine):
        return ("R", "A", "S")

    def apply_affine(affine, points):
        points_array = np.asarray(points)
        homogeneous = np.c_[points_array, np.ones(len(points_array))]
        return (homogeneous @ np.asarray(affine).T)[:, :3]

    def resample_from_to(img, _target, **_kwargs):
        return img

    spatialimages.SpatialImage = SpatialImage
    nibabel.Nifti1Image = Nifti1Image
    nibabel.spatialimages = spatialimages
    nibabel.load = load
    orientations.aff2axcodes = aff2axcodes
    affines.apply_affine = apply_affine
    processing.resample_from_to = resample_from_to

    sys.modules["nibabel"] = nibabel
    sys.modules["nibabel.orientations"] = orientations
    sys.modules["nibabel.affines"] = affines
    sys.modules["nibabel.processing"] = processing
    sys.modules["nibabel.spatialimages"] = spatialimages


_install_minimal_nibabel_stub()


@pytest.fixture
def settings(tmp_path):
    from python_scripts.project_core.config import Settings

    processed = tmp_path / "processed_mri"
    return Settings(
        input_mri_dir=tmp_path / "input_mri",
        processed_mri_dir=processed,
        mni_template_dir=tmp_path / "mni_template",
        reoriented_dir=processed / "reoriented",
        hd_bet_dir=processed / "hd_bet",
        fast_dir=processed / "fast",
        mesh_dir=processed / "meshes",
        mni_template_path=tmp_path / "mni_template" / "MNI152_T1_1mm.nii.gz",
        fsl_docker_image="brainlife/fsl:test",
        container_input_dir="/data/in",
        container_output_dir="/data/out",
        overwrite=True,
        skip_existing=True,
        hd_bet_device="cpu",
    )


@pytest.fixture
def mri_case(tmp_path):
    from python_scripts.project_core.domain import MRICase

    return MRICase(
        subject_id="IXI001",
        acquisition_date="2026-06-02",
        raw_path=tmp_path / "IXI001.nii.gz",
    )


@pytest.fixture
def workspace(settings, mri_case):
    from python_scripts.project_core.workspace import build_case_workspace

    return build_case_workspace(mri_case, settings)
