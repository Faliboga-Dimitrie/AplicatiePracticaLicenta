from __future__ import annotations

import shutil
from pathlib import Path

from ..project_core.config import Settings
from ..project_core.domain import MRICase
from ..project_core.ports import ReorientationResult
from ..project_core.workspace import CaseWorkspace
from .docker_fsl import FslDockerRunner
from .input_checks import OrientationStatus, check_input_orientation


class FslReorientationBackend:
    """
    ReorientationBackend implementation using FSL fslreorient2std through
    Docker.

    The backend is responsible only for producing the reoriented image inside the
    provided CaseWorkspace. It does not decide how final artifacts are stored or
    exposed to an API/frontend.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.docker = FslDockerRunner(settings.fsl_docker_image)

    def run(self, case: MRICase, workspace: CaseWorkspace) -> ReorientationResult:
        output_path = workspace.reoriented_path

        existing = self._handle_existing_output(output_path)
        if existing is not None:
            return existing

        workspace_case = MRICase(
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
            raw_path=workspace.raw_path,
        )
        orientation = check_input_orientation(workspace_case, self.settings)

        if orientation.status == OrientationStatus.ALREADY_STANDARD:
            self._copy_to_reoriented(workspace.raw_path, output_path)
            return ReorientationResult(
                output_path=output_path,
                already_standard=True,
            )

        if orientation.status == OrientationStatus.CAN_REORIENT:
            self._run_reorient(
                input_path=workspace.raw_path,
                output_path=output_path,
            )
            self._require_output(output_path)
            self._check_output_is_standard(case, workspace)
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
                already_standard=False,
            )

        if not self.settings.overwrite:
            raise FileExistsError(
                f"Reoriented output already exists: {output_path}. "
                "Set overwrite=True or remove the file."
            )

        output_path.unlink()
        return None

    def _copy_to_reoriented(self, input_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, output_path)

    def _build_command(self, input_path: Path, output_path: Path) -> list[str]:
        return self.docker.build_reorient_command(
            input_path=input_path,
            output_path=output_path,
        )

    def _run_reorient(self, input_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = self._build_command(input_path, output_path)

        proc = self.docker.run(cmd)

        if proc.returncode != 0:
            raise RuntimeError(
                "FSL reorientation failed.\n"
                f"Command: {' '.join(cmd)}\n\n"
                f"STDOUT:\n{proc.stdout}\n\n"
                f"STDERR:\n{proc.stderr}"
            )

    def _require_output(self, output_path: Path) -> None:
        if not output_path.exists():
            raise RuntimeError(
                "Reorientation completed, but output file was not created: "
                f"{output_path}"
            )

    def _check_output_is_standard(self, case: MRICase, workspace: CaseWorkspace) -> None:
        post_case = MRICase(
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
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
