from __future__ import annotations

import subprocess
from pathlib import Path

import nibabel as nib

from ..project_core.config import Settings
from ..project_core.domain import MRICase
from ..project_core.ports import SegmentationResult
from ..project_core.workspace import CaseWorkspace
from .input_checks import OrientationStatus, check_input_orientation


class FslFastSegmentationBackend:
    """
    SegmentationBackend implementation using FSL FAST through the existing
    PowerShell/Docker wrapper.

    The backend produces FAST PVE outputs in the provided CaseWorkspace and
    returns typed paths to the generated probability-volume-estimation files.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, input_path: Path, workspace: CaseWorkspace) -> SegmentationResult:
        input_path = Path(input_path)

        existing = self._handle_existing_outputs(workspace)
        if existing is not None:
            return existing

        self._validate_input(input_path, workspace)
        self._run_fast(input_path, workspace)
        self._fast_cleanup(workspace)
        self._require_outputs(workspace)

        return self._result_from_workspace(workspace)

    def _handle_existing_outputs(
        self,
        workspace: CaseWorkspace,
    ) -> SegmentationResult | None:
        full_outputs_exist = workspace.has_fast_pve_outputs
        partial_outputs_exist = any(workspace.fast_dir.glob(f"{workspace.subject_id}*"))

        if full_outputs_exist:
            if self.settings.skip_existing:
                return self._result_from_workspace(workspace)

            if not self.settings.overwrite:
                raise FileExistsError(
                    f"FAST PVE outputs already exist for {workspace.subject_id} in "
                    f"{workspace.fast_dir}. Set overwrite=True to rerun."
                )

            self._remove_existing_outputs(workspace)
            return None

        if partial_outputs_exist:
            if not self.settings.overwrite:
                raise FileExistsError(
                    f"Partial FAST PVE outputs already exist for {workspace.subject_id} in "
                    f"{workspace.fast_dir}. Set overwrite=True to clean and rerun."
                )

            self._remove_existing_outputs(workspace)

        return None

    def _remove_existing_outputs(self, workspace: CaseWorkspace) -> None:
        if not workspace.fast_dir.exists():
            return

        for path in workspace.fast_dir.glob(f"{workspace.subject_id}*"):
            if path.is_file():
                path.unlink()

    def _validate_input(self, input_path: Path, workspace: CaseWorkspace) -> None:
        """
        Validate the image passed to FAST.

        FAST expects a brain-extracted 3D structural image. This pipeline also
        keeps the stricter invariant that the input should already match the
        configured MNI/template orientation.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"FAST input does not exist: {input_path}")

        try:
            img = nib.load(str(input_path))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load FAST input with nibabel: {input_path}\n{exc}"
            ) from exc

        if img.ndim != 3:
            raise ValueError(
                "FAST expects a 3D image in this pipeline, but got "
                f"ndim={img.ndim} for {input_path}"
            )

        temp_case = MRICase(
            subject_id=workspace.subject_id,
            acquisition_date=workspace.acquisition_date,
            raw_path=input_path,
        )
        orientation = check_input_orientation(temp_case, self.settings)

        if orientation.status != OrientationStatus.ALREADY_STANDARD:
            raise RuntimeError(
                "FAST input is expected to already be in the chosen standard "
                "orientation, but the check returned "
                f"{orientation.status.name}: {orientation.message}"
            )

    def _build_command(self, input_path: Path, workspace: CaseWorkspace) -> list[str]:
        return [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.settings.fast_script),
            "-InputPath",
            str(input_path),
            "-OutputPrefix",
            str(workspace.fast_prefix),
            "-DockerImage",
            str(self.settings.fsl_docker_image),
            "-Classes",
            str(self.settings.fast_classes),
            "-ImageType",
            "1",  # T1 pipeline
            "-ContainerInputDir",
            str(self.settings.container_input_dir),
            "-ContainerOutputDir",
            str(self.settings.container_output_dir),
        ]

    def _run_fast(self, input_path: Path, workspace: CaseWorkspace) -> None:
        cmd = self._build_command(input_path, workspace)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"FAST failed for {workspace.subject_id}\n"
                f"Command: {' '.join(cmd)}\n\n"
                f"STDOUT:\n{proc.stdout}\n\n"
                f"STDERR:\n{proc.stderr}"
            )

    def _fast_cleanup(self, workspace: CaseWorkspace) -> None:
        """Remove unused FAST outputs from this subject's local FAST folder."""
        subject_fast_dir = workspace.fast_dir.parent
        if not subject_fast_dir.exists():
            return

        unused_markers = ("mixeltype", "pveseg", "_seg")

        for path in subject_fast_dir.rglob("*"):
            if not path.is_file():
                continue

            name = path.name.lower()
            if any(marker in name for marker in unused_markers):
                path.unlink()

    def _require_outputs(self, workspace: CaseWorkspace) -> None:
        missing = workspace.missing_fast_pve_paths
        if not missing:
            return

        missing_str = "\n".join(str(path) for path in missing)
        raise RuntimeError(
            "FAST reported success, but some expected output files were not created:\n"
            f"{missing_str}"
        )

    def _result_from_workspace(self, workspace: CaseWorkspace) -> SegmentationResult:
        return SegmentationResult(
            pve_paths=workspace.fast_pve_paths,
        )

__all__ = [
    "FslFastSegmentationBackend",
]
