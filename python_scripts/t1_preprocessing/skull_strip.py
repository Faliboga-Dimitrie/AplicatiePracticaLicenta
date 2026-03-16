from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import nibabel as nib

from .config import Settings
from .models import MRICase, CasePaths
from .qc import maybe_save_bet_qc


def _ensure_hd_bet_available() -> str:
    """
    Make sure the hd-bet executable is available in PATH.
    Return its resolved executable path.
    """
    exe = shutil.which("hd-bet")
    if exe is None:
        raise FileNotFoundError(
            "Could not find 'hd-bet' in PATH. "
            "Activate the correct environment or install HD-BET first."
        )
    return exe


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
    exe = _ensure_hd_bet_available()

    input_path = paths.reoriented_path
    output_path = paths.skull_stripped_path
    mask_path = paths.skull_stripped_mask_path

    paths.hd_bet_dir.mkdir(parents=True, exist_ok=True)

    cmd, expects_mask = _build_hd_bet_command(
        exe=exe,
        input_path=input_path,
        output_path=output_path,
        device=settings.hd_bet_device,
        verbose=settings.hd_bet_verbose,
    )

    # Existing-output handling
    if output_path.exists():
        outputs_complete = output_path.exists() and (mask_path.exists() if expects_mask else True)

        if settings.skip_existing and outputs_complete:
            return output_path

        if not settings.overwrite:
            raise FileExistsError(
                f"HD-BET output already exists: {output_path}. "
                "Set overwrite=True or remove the file manually."
            )

        _remove_if_exists(output_path)
        _remove_if_exists(mask_path)

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

    if expects_mask and not mask_path.exists():
        raise RuntimeError(
            f"HD-BET was asked to save a mask, but the mask file was not created: {mask_path}"
        )

    maybe_save_bet_qc(case, paths, settings)
    return output_path