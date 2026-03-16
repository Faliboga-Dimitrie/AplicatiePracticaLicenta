from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Settings
from .input_checks import OrientationStatus, check_input_orientation
from .models import MRICase, CasePaths
from .qc import maybe_save_reorientation_qc


def _copy_to_reoriented(case: MRICase, paths: CasePaths) -> Path:
    """
    Copy the raw MRI into the per-subject reoriented folder.
    Used when the image is already in the desired orientation.
    """
    paths.reoriented_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(case.raw_path, paths.reoriented_path)
    return paths.reoriented_path


def _run_reorient_script(case: MRICase, paths: CasePaths, settings: Settings) -> None:
    """
    Call the PowerShell wrapper that performs fslreorient2std inside Docker.
    """
    paths.reoriented_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
    [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(settings.reorient_script),
        "-InputPath",
        str(case.raw_path),
        "-OutputPath",
        str(paths.reoriented_path),
        "-DockerImage",
        str(settings.fsl_docker_image),
    ],
    check=True,
        
    )


def _check_output_is_standard(case: MRICase, paths: CasePaths, settings: Settings) -> None:
    """
    Re-run the orientation check on the produced output file.
    """
    post_case = MRICase(
        subject_id=case.subject_id,
        raw_path=paths.reoriented_path,
    )

    post = check_input_orientation(post_case, settings)

    if post.status != OrientationStatus.ALREADY_STANDARD:
        raise RuntimeError(
            "Reorientation finished, but the output still does not match the "
            f"template orientation. Details: {post.message}"
        )


def run_reorientation(case: MRICase, paths: CasePaths, settings: Settings) -> Path:
    """
    Reorientation policy:

    1. If the output already exists:
       - return it when skip_existing=True
       - overwrite it only when overwrite=True
       - otherwise raise an error

    2. If the input is already standard-oriented:
       - copy it into processed_mri/reoriented/<subject>/<subject>_reo.nii.gz

    3. If the input can be safely reoriented:
       - call the PowerShell/Docker/FSL wrapper
       - verify the produced output

    4. Otherwise:
       - stop and require manual review
    """
    paths.reoriented_dir.mkdir(parents=True, exist_ok=True)

    output_path = paths.reoriented_path

    # Existing output policy
    if output_path.exists():
        if settings.skip_existing:
            return output_path

        if not settings.overwrite:
            raise FileExistsError(
                f"Reoriented output already exists: {output_path}. "
                "Set overwrite=True or remove the file."
            )

        output_path.unlink()

    # Check the raw input before doing anything
    result = check_input_orientation(case, settings)

    if result.status == OrientationStatus.ALREADY_STANDARD:
        out_path = _copy_to_reoriented(case, paths)
        maybe_save_reorientation_qc(case, paths, settings)
        return out_path

    if result.status == OrientationStatus.CAN_REORIENT:
        _run_reorient_script(case, paths, settings)

        if not output_path.exists():
            raise RuntimeError(
                f"Reorientation script completed, but output file was not created: {output_path}"
            )

        _check_output_is_standard(case, paths, settings)
        maybe_save_reorientation_qc(case, paths, settings)
        return output_path

    raise RuntimeError(
        f"Automatic reorientation refused for {case.subject_id}: {result.message}"
    )