from __future__ import annotations

import subprocess
from pathlib import Path

import nibabel as nib

from .config import Settings
from .input_checks import OrientationStatus, check_input_orientation
from .models import MRICase, CasePaths
from .qc import maybe_save_fast_qc


def _validate_fast_input(case: MRICase, paths: CasePaths, settings: Settings) -> None:
    """
    Validate the input that will be passed to FAST.

    FAST itself expects a brain-extracted 3D structural image.
    In this pipeline we also keep the stricter invariant that the input
    should still be in the chosen standard MNI orientation.
    """
    input_path = paths.fast_input_path

    if not input_path.exists():
        raise FileNotFoundError(f"FAST input does not exist: {input_path}")

    try:
        img = nib.load(str(input_path))
    except Exception as exc:
        raise RuntimeError(f"Failed to load FAST input with nibabel: {input_path}\n{exc}") from exc

    if img.ndim != 3:
        raise ValueError(
            f"FAST expects a 3D image in this pipeline, but got ndim={img.ndim} for {input_path}"
        )

    # Reuse the orientation checker on the FAST input itself.
    # Since skull stripping should preserve orientation, this should still be ALREADY_STANDARD.
    temp_case = MRICase(
        subject_id=case.subject_id,
        raw_path=input_path,
    )
    orient = check_input_orientation(temp_case, settings)

    if orient.status != OrientationStatus.ALREADY_STANDARD:
        raise RuntimeError(
            "FAST input is expected to already be in the chosen standard orientation, "
            f"but the check returned {orient.status.name}: {orient.message}"
        )


def _remove_existing_fast_outputs(paths: CasePaths) -> None:
    """
    Remove all existing FAST outputs for this subject from the subject-specific FAST folder.
    """
    if not paths.fast_dir.exists():
        return

    for p in paths.fast_dir.glob(f"{paths.subject_id}*"):
        if p.is_file():
            p.unlink()


def _list_missing_fast_outputs(paths: CasePaths) -> list[Path]:
    expected = [
        paths.fast_mixeltype_path,
        paths.fast_pve_csf_path,
        paths.fast_pve_gm_path,
        paths.fast_pve_wm_path,
        paths.fast_pve_seg_path,
        paths.fast_seg_path,
    ]
    return [p for p in expected if not p.exists()]


def run_segmentation(case: MRICase, paths: CasePaths, settings: Settings) -> Path:
    """
    Run FSL FAST on the skull-stripped T1 image for one subject.

    Input:
        paths.fast_input_path   -> skull-stripped T1

    Outputs:
        paths.fast_prefix + FAST-derived outputs in processed_mri/fast/<subject>/

    Existing-output policy:
        - if skip_existing=True and all expected outputs exist, return the main segmentation
        - if partial outputs exist and overwrite=False, raise
        - if overwrite=True, remove old outputs and rerun
    """
    input_path = paths.fast_input_path
    output_prefix = paths.fast_prefix

    paths.fast_dir.mkdir(parents=True, exist_ok=True)

    full_outputs_exist = paths.has_fast_outputs
    partial_outputs_exist = any(paths.fast_dir.glob(f"{paths.subject_id}*"))

    if full_outputs_exist:
        if settings.skip_existing:
            return paths.fast_seg_path

        if not settings.overwrite:
            raise FileExistsError(
                f"FAST outputs already exist for {case.subject_id} in {paths.fast_dir}. "
                "Set overwrite=True to rerun."
            )

        _remove_existing_fast_outputs(paths)

    elif partial_outputs_exist:
        if not settings.overwrite:
            raise FileExistsError(
                f"Partial FAST outputs already exist for {case.subject_id} in {paths.fast_dir}. "
                "Set overwrite=True to clean and rerun."
            )

        _remove_existing_fast_outputs(paths)

    _validate_fast_input(case, paths, settings)

    cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(settings.fast_script),
        "-InputPath",
        str(input_path),
        "-OutputPrefix",
        str(output_prefix),
        "-DockerImage",
        str(settings.fsl_docker_image),
        "-Classes",
        str(settings.fast_classes),
        "-ImageType",
        "1",  # T1 pipeline
        "-ContainerInputDir",
        str(settings.container_input_dir),
        "-ContainerOutputDir",
        str(settings.container_output_dir),
        "-VerboseMode",
        str(settings.fast_verbose),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"FAST failed for {case.subject_id}\n"
            f"Command: {' '.join(cmd)}\n\n"
            f"STDOUT:\n{proc.stdout}\n\n"
            f"STDERR:\n{proc.stderr}"
        )

    missing = _list_missing_fast_outputs(paths)
    if missing:
        missing_str = "\n".join(str(p) for p in missing)
        raise RuntimeError(
            "FAST reported success, but some expected output files were not created:\n"
            f"{missing_str}"
        )

    maybe_save_fast_qc(case, paths, settings)
    return paths.fast_seg_path