from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import nibabel as nib

from ..project_core.config import Settings
from ..project_core.domain import MRICase, strip_nii_suffix
from ..project_core.ports import SkullStripResult
from ..project_core.workspace import CaseWorkspace


class HdBetSkullStripBackend:
    """
    SkullStripBackend implementation using HD-BET.

    The backend writes its outputs into the provided CaseWorkspace and returns a
    SkullStripResult. It does not publish final artifacts; that remains the job
    of an ArtifactStore at a higher layer.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._help_text: str | None = None

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SkullStripResult:
        exe = self._ensure_hd_bet_available()
        input_path = Path(input_path)
        output_path = workspace.skull_stripped_path
        mask_path = workspace.skull_stripped_mask_path
        native_mask_path = self._native_mask_path(output_path)

        cmd, expects_mask = self._build_command(
            exe=exe,
            input_path=input_path,
            output_path=output_path,
        )

        existing = self._handle_existing_outputs(
            workspace=workspace,
            output_path=output_path,
            mask_path=mask_path,
            native_mask_path=native_mask_path,
            expects_mask=expects_mask,
        )
        if existing is not None:
            return existing

        self._validate_input(input_path)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"HD-BET failed for {workspace.subject_id}\n"
                f"Command: {' '.join(cmd)}\n\n"
                f"STDOUT:\n{proc.stdout}\n\n"
                f"STDERR:\n{proc.stderr}"
            )

        if not output_path.exists():
            raise RuntimeError(
                "HD-BET reported success, but the skull-stripped output was not "
                f"created: {output_path}"
            )

        self._normalize_mask_output(
            output_path=output_path,
            desired_mask_path=mask_path,
            expects_mask=expects_mask,
        )

        return SkullStripResult(
            image_path=output_path,
            mask_path=mask_path if mask_path.exists() else None,
        )

    def _ensure_hd_bet_available(self) -> str:
        """
        Resolve the HD-BET executable in a debugger-friendly way.

        Priority:
          1. explicit settings.hd_bet_executable
          2. same environment as sys.executable
          3. PATH lookup
        """
        candidates: list[Path] = []

        if self.settings.hd_bet_executable:
            candidates.append(Path(self.settings.hd_bet_executable))

        py_dir = Path(sys.executable).resolve().parent

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

    def _get_help_text(self, exe: str) -> str:
        if self._help_text is None:
            proc = subprocess.run(
                [exe, "-h"],
                capture_output=True,
                text=True,
                check=False,
            )
            self._help_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return self._help_text

    def _supports_flag(self, exe: str, flag: str) -> bool:
        return flag in self._get_help_text(exe)

    def _build_command(
        self,
        *,
        exe: str,
        input_path: Path,
        output_path: Path,
    ) -> tuple[list[str], bool]:
        device = self.settings.hd_bet_device.strip().lower()
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
            "--verbose" if self.settings.hd_bet_verbose else "--quiet",
        ]

        # Official README recommendation for CPU: disable TTA when available.
        if device == "cpu" and self._supports_flag(exe, "--disable_tta"):
            cmd.append("--disable_tta")

        expects_mask = False
        if self._supports_flag(exe, "--save_bet_mask"):
            cmd.append("--save_bet_mask")
            expects_mask = True

        return cmd, expects_mask

    def _validate_input(self, input_path: Path) -> None:
        if not input_path.exists():
            raise FileNotFoundError(f"HD-BET input does not exist: {input_path}")

        img = nib.load(str(input_path))
        if img.ndim != 3:
            raise ValueError(
                f"HD-BET expects a 3D NIfTI image, but got ndim={img.ndim} for {input_path}"
            )

    def _handle_existing_outputs(
        self,
        *,
        workspace: CaseWorkspace,
        output_path: Path,
        mask_path: Path,
        native_mask_path: Path,
        expects_mask: bool,
    ) -> SkullStripResult | None:
        any_output_exists = (
            output_path.exists()
            or mask_path.exists()
            or native_mask_path.exists()
        )

        if not any_output_exists:
            return None

        outputs_complete = output_path.exists() and (
            (mask_path.exists() or native_mask_path.exists()) if expects_mask else True
        )

        if self.settings.skip_existing and outputs_complete:
            self._normalize_mask_output(
                output_path=output_path,
                desired_mask_path=mask_path,
                expects_mask=expects_mask,
            )
            return SkullStripResult(
                image_path=output_path,
                mask_path=mask_path if mask_path.exists() else None,
            )

        if not self.settings.overwrite:
            raise FileExistsError(
                f"HD-BET output already exists in {workspace.hd_bet_dir}. "
                "Set overwrite=True or remove the files manually."
            )

        self._remove_if_exists(output_path)
        self._remove_if_exists(mask_path)
        self._remove_if_exists(native_mask_path)
        return None

    def _remove_if_exists(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def _native_mask_path(self, output_path: Path) -> Path:
        """
        HD-BET derives the mask name from the output image name.

        Example:
            output_path = subject_bet.nii.gz
            native mask = subject_bet_bet.nii.gz
        """
        base = strip_nii_suffix(output_path)
        return output_path.parent / f"{base}_bet.nii.gz"

    def _normalize_mask_output(
        self,
        *,
        output_path: Path,
        desired_mask_path: Path,
        expects_mask: bool,
    ) -> None:
        if not expects_mask:
            return

        native_mask_path = self._native_mask_path(output_path)

        if native_mask_path.exists():
            if desired_mask_path.exists() and desired_mask_path != native_mask_path:
                desired_mask_path.unlink()
            native_mask_path.replace(desired_mask_path)
            return

        if desired_mask_path.exists():
            return

        raise RuntimeError(
            "HD-BET was asked to save a mask, but no mask file was found.\n"
            f"Expected pipeline mask: {desired_mask_path}\n"
            f"Expected HD-BET native mask: {native_mask_path}"
        )

__all__ = [
    "HdBetSkullStripBackend",
]
