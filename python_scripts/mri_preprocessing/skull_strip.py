from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import nibabel as nib

from ..project_core.config import Settings
from ..project_core.ports import SkullStripResult
from ..project_core.workspace import CaseWorkspace
from .input_checks import OrientationStatus, check_input_orientation
from ..project_core import MRICase

class HdBetSkullStripBackend:
    """
    SkullStripBackend implementation using HD-BET.

    The backend writes the skull-stripped image into the provided CaseWorkspace
    and returns its path. It does not publish final artifacts; that remains the
    job of an ArtifactStore at a higher layer.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._help_text: str | None = None

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SkullStripResult:
        exe = self._ensure_hd_bet_available()
        input_path = Path(input_path)
        output_path = workspace.skull_stripped_path

        cmd = self._build_command(
            exe=exe,
            input_path=input_path,
            output_path=output_path,
        )

        existing = self._handle_existing_outputs(
            workspace=workspace,
            output_path=output_path,
        )
        if existing is not None:
            return existing

        self._validate_input(input_path, workspace)

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

        return SkullStripResult(image_path=output_path)

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
    
    def _cuda_available(self) -> bool:
        try:
            import torch
        except Exception:
            return False

        try:
            return bool(torch.cuda.is_available())
        except Exception:
            return False


    def _resolve_hd_bet_device(self) -> str:
        device = self.settings.hd_bet_device.strip().lower()

        if device not in {"cuda", "cpu", "mps"}:
            raise ValueError(
                f"Unsupported HD-BET device '{device}'. Expected one of: cuda, cpu, mps."
            )

        if device == "cuda" and not self._cuda_available():
            return "cpu"

        return device

    def _build_command(
        self,
        *,
        exe: str,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        device = self._resolve_hd_bet_device()

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

        return cmd

    def _validate_input(self, input_path: Path, workspace: CaseWorkspace) -> None:
        if not input_path.exists():
            raise FileNotFoundError(f"HD-BET input does not exist: {input_path}")

        img = nib.load(str(input_path))
        if img.ndim != 3:
            raise ValueError(
                f"HD-BET expects a 3D NIfTI image, but got ndim={img.ndim} for {input_path}"
            )
        
        temp_case = MRICase(
            subject_id=workspace.subject_id,
            acquisition_date=workspace.acquisition_date,
            raw_path=input_path,
        )
        orientation = check_input_orientation(temp_case, self.settings)

        if orientation.status != OrientationStatus.ALREADY_STANDARD:
            raise RuntimeError(
                "HD-BET input is expected to already be in the chosen standard "
                "orientation, but the check returned "
                f"{orientation.status.name}: {orientation.message}"
            )

    def _handle_existing_outputs(
        self,
        *,
        workspace: CaseWorkspace,
        output_path: Path,
    ) -> SkullStripResult | None:
        if not output_path.exists():
            return None

        if self.settings.skip_existing:
            return SkullStripResult(image_path=output_path)

        if not self.settings.overwrite:
            raise FileExistsError(
                f"HD-BET output already exists in {workspace.hd_bet_dir}. "
                "Set overwrite=True or remove the file manually."
            )

        output_path.unlink()
        return None


__all__ = [
    "HdBetSkullStripBackend",
]
