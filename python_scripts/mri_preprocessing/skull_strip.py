from __future__ import annotations

import os
import shutil
import sys
import subprocess
from pathlib import Path

import nibabel as nib

from ..project_core import Settings
from ..project_core import MRICase, CasePaths, strip_nii_suffix
from .qc import maybe_save_bet_qc


def _ensure_hd_bet_available(settings: Settings) -> str:
    """
    Resolve the HD-BET executable in a debugger-friendly way.
    Priority:
      1. explicit settings.hd_bet_executable
      2. same environment as sys.executable
      3. PATH lookup
    """
    candidates: list[Path] = []

    if settings.hd_bet_executable:
        candidates.append(Path(settings.hd_bet_executable))

    py_dir = Path(sys.executable).resolve().parent

    # Common layouts:
    # - conda on Windows: <env>/python.exe, scripts in <env>/Scripts/
    # - venv on Windows:  <env>/Scripts/python.exe, scripts in same folder
    # - Linux/macOS:      <env>/bin/python, scripts in same folder
    candidates.extend([
        py_dir / "hd-bet",
        py_dir / "hd-bet.exe",
        py_dir / "Scripts" / "hd-bet",
        py_dir / "Scripts" / "hd-bet.exe",
        py_dir.parent / "Scripts" / "hd-bet",
        py_dir.parent / "Scripts" / "hd-bet.exe",
    ])

    which_path = shutil.which("hd-bet")
    if which_path:
        candidates.append(Path(which_path))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())

    raise FileNotFoundError(
        "Could not find HD-BET. Checked explicit setting, the active Python "
        "environment, and PATH. "
        f"sys.executable={sys.executable}"
    )


def _validate_hd_bet_input(input_path: Path) -> None:
    """
    HD-BET expects a 3D NIfTI image.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"HD-BET input does not exist: {input_path}")

    img = nib.load(str(input_path))
    if img.ndim != 3:
        raise ValueError(
            f"HD-BET expects a 3D NIfTI image, but got ndim={img.ndim} for {input_path}"
        )


def _get_hd_bet_help_text(exe: str) -> str:
    """
    Read hd-bet help output so we can adapt to the installed version.
    This avoids hard-coding optional flags that may differ between versions.
    """
    proc = subprocess.run(
        [exe, "-h"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "") + "\n" + (proc.stderr or "")


def _supports_flag(help_text: str, flag: str) -> bool:
    return flag in help_text


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()

def _hd_bet_native_mask_path(output_path: Path) -> Path:
    """
    HD-BET derives the mask name from the output image name.

    Example:
        output_path = subject_bet.nii.gz
        native mask = subject_bet_bet.nii.gz
    """
    base = strip_nii_suffix(output_path)
    return output_path.parent / f"{base}_bet.nii.gz"

def _normalize_hd_bet_mask_output(
    output_path: Path,
    desired_mask_path: Path,
    expects_mask: bool,
) -> None:
    """
    If HD-BET saved its native mask name, rename it to the pipeline name.
    """
    if not expects_mask:
        return

    native_mask_path = _hd_bet_native_mask_path(output_path)

    # Best case: HD-BET made the native mask, we rename it.
    if native_mask_path.exists():
        if desired_mask_path.exists() and desired_mask_path != native_mask_path:
            desired_mask_path.unlink()
        native_mask_path.replace(desired_mask_path)
        return

    # Also allow the case where the desired path already exists.
    if desired_mask_path.exists():
        return

    raise RuntimeError(
        "HD-BET was asked to save a mask, but no mask file was found.\n"
        f"Expected pipeline mask: {desired_mask_path}\n"
        f"Expected HD-BET native mask: {native_mask_path}"
    )


def _build_hd_bet_command(
    exe: str,
    input_path: Path,
    output_path: Path,
    device: str,
    verbose: bool = True,
) -> tuple[list[str], bool]:
    """
    Build the hd-bet command.

    Returns:
        command, expects_mask_output
    """
    help_text = _get_hd_bet_help_text(exe)

    device = device.strip().lower()
    if device not in {"cuda", "cpu", "mps"}:
        raise ValueError(
            f"Unsupported HD-BET device '{device}'. Expected one of: cuda, cpu, mps."
        )

    cmd = [
        exe,
        "-i",
        str(input_path),
        "-o",
        str(output_path),
        "-device",
        device,
        "--verbose" if verbose else "--quiet",
    ]

    # Official README recommendation for CPU: disable TTA.
    if device == "cpu" and _supports_flag(help_text, "--disable_tta"):
        cmd.append("--disable_tta")

    # If the installed version supports explicit mask saving, request it.
    # This matches your CasePaths design nicely.
    expects_mask = False
    if _supports_flag(help_text, "--save_bet_mask"):
        cmd.append("--save_bet_mask")
        expects_mask = True

    return cmd, expects_mask


def run_skull_strip(case: MRICase, paths: CasePaths, settings: Settings) -> Path:
    """
    Run HD-BET on the reoriented MRI for one subject.

    Input:
        paths.reoriented_path

    Outputs:
        paths.skull_stripped_path
        paths.skull_stripped_mask_path (when supported/requested)

    Existing-output policy:
        - if skip_existing=True and outputs are already present, return existing output
        - if overwrite=False and output exists, raise
        - if overwrite=True, delete old outputs and rerun
    """
    exe = _ensure_hd_bet_available(settings)

    input_path = paths.reoriented_path
    output_path = paths.skull_stripped_path
    mask_path = paths.skull_stripped_mask_path
    native_mask_path = _hd_bet_native_mask_path(output_path)

    cmd, expects_mask = _build_hd_bet_command(
        exe=exe,
        input_path=input_path,
        output_path=output_path,
        device=settings.hd_bet_device,
        verbose=settings.hd_bet_verbose,
    )

    # Existing-output handling
    if output_path.exists() or mask_path.exists() or native_mask_path.exists():
        outputs_complete = output_path.exists() and (
            (mask_path.exists() or native_mask_path.exists()) if expects_mask else True
        )

        if settings.skip_existing and outputs_complete:
            _normalize_hd_bet_mask_output(
                output_path=output_path,
                desired_mask_path=mask_path,
                expects_mask=expects_mask,
            )
            return output_path

        if not settings.overwrite:
            raise FileExistsError(
                f"HD-BET output already exists in {paths.hd_bet_dir}. "
                "Set overwrite=True or remove the files manually."
            )

        _remove_if_exists(output_path)
        _remove_if_exists(mask_path)
        _remove_if_exists(native_mask_path)

    _validate_hd_bet_input(input_path)

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"HD-BET failed for {case.subject_id}\n"
            f"Command: {' '.join(cmd)}\n\n"
            f"STDOUT:\n{proc.stdout}\n\n"
            f"STDERR:\n{proc.stderr}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"HD-BET reported success, but the skull-stripped output was not created: {output_path}"
        )

    _normalize_hd_bet_mask_output(
    output_path=output_path,
    desired_mask_path=mask_path,
    expects_mask=expects_mask,)

    maybe_save_bet_qc(case, paths, settings)
    return output_path