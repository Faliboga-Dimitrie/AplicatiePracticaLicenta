from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..project_core.config import Settings
from ..project_core.domain import MRICase
from ..project_core.ports import ReorientationResult
from ..project_core.workspace import CaseWorkspace
from .input_checks import OrientationStatus, check_input_orientation
from .qc import maybe_save_reorientation_qc


class FslReorientationBackend:
    """
    ReorientationBackend implementation using the existing PowerShell/Docker/FSL
    wrapper around fslreorient2std.

    The backend is responsible only for producing the reoriented image inside the
    provided CaseWorkspace. It does not decide how final artifacts are stored or
    exposed to an API/frontend.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, case: MRICase, workspace: CaseWorkspace) -> ReorientationResult:
        output_path = workspace.reoriented_path

        existing = self._handle_existing_output(output_path)
        if existing is not None:
            return existing

        orientation = check_input_orientation(case, self.settings)

        if orientation.status == OrientationStatus.ALREADY_STANDARD:
            shutil.copy2(case.raw_path, output_path)
            maybe_save_reorientation_qc(case, workspace, self.settings)
            return ReorientationResult(
                output_path=output_path,
                already_standard=True,
            )

        if orientation.status == OrientationStatus.CAN_REORIENT:
            self._run_reorient_script(
                input_path=case.raw_path,
                output_path=output_path,
            )
            self._check_output_is_standard(case, workspace)
            maybe_save_reorientation_qc(case, workspace, self.settings)
            return ReorientationResult(
                output_path=output_path,
                already_standard=False,
            )

        raise RuntimeError(
            f"Automatic reorientation refused for {case.subject_id}: {orientation.message}"
        )

    def _handle_existing_output(self, output_path: Path) -> ReorientationResult | None:
        if not output_path.exists():
            return None

        if self.settings.skip_existing:
            return ReorientationResult(
                output_path=output_path,
                already_standard=True,
            )

        if not self.settings.overwrite:
            raise FileExistsError(
                f"Reoriented output already exists: {output_path}. "
                "Set overwrite=True or remove the file."
            )

        output_path.unlink()
        return None

    def _build_command(self, input_path: Path, output_path: Path) -> list[str]:
        return [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.settings.reorient_script),
            "-InputPath",
            str(input_path),
            "-OutputPath",
            str(output_path),
            "-DockerImage",
            str(self.settings.fsl_docker_image),
        ]

    def _run_reorient_script(self, input_path: Path, output_path: Path) -> None:
        cmd = self._build_command(input_path, output_path)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                "FSL reorientation failed.\n"
                f"Command: {' '.join(cmd)}\n\n"
                f"STDOUT:\n{proc.stdout}\n\n"
                f"STDERR:\n{proc.stderr}"
            )

    def _check_output_is_standard(self, case: MRICase, workspace: CaseWorkspace) -> None:
        post_case = MRICase(
            subject_id=case.subject_id,
            raw_path=workspace.reoriented_path,
        )

        post = check_input_orientation(post_case, self.settings)

        if post.status != OrientationStatus.ALREADY_STANDARD:
            raise RuntimeError(
                "Reorientation finished, but the output still does not match the "
                f"template orientation. Details: {post.message}"
            )


__all__ = [
    "FslReorientationBackend",
]
