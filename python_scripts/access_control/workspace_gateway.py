from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from ..project_core import Settings
from ..project_core import MRICase, FileSystemWorkspaceProvider, build_case_workspace
from ..project_core.ports import WorkspaceGateway

class ProjectCaseWorkspaceGateway:
    """
    Adapter from access_control to your existing project_core workspace.

    It supports both import styles:
    - package style:     from python_scripts.access_control import ...
    - top-level style:   from access_control import ...
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def create_case_workspace(
        self,
        *,
        subject_id: str,
        acquisition_date: date,
        source_raw_path: Path | None = None,
    ) -> Any:
        if source_raw_path is None:
            raise ValueError("source_raw_path is required to create a CaseWorkspace input file.")

        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=Path(source_raw_path),
        )
        provider = FileSystemWorkspaceProvider(self.settings)
        return provider.create_workspace(case)

    def delete_case_workspace(self, *, subject_id: str, acquisition_date: date) -> None:
        placeholder_raw = Path("__deleted_case_placeholder__.nii.gz")
        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=placeholder_raw,
        )
        workspace = build_case_workspace(case, self.settings)

        for directory in workspace.stage_dirs:
            if directory.exists():
                shutil.rmtree(directory)

    def delete_subject_workspaces(self, *, subject_id: str) -> None:
        subject_dirs = [
            Path(self.settings.input_mri_dir) / subject_id,
            Path(self.settings.reoriented_dir) / subject_id,
            Path(self.settings.hd_bet_dir) / subject_id,
            Path(self.settings.fast_dir) / subject_id,
            Path(self.settings.mesh_dir) / subject_id,
        ]

        for directory in subject_dirs:
            if directory.exists():
                shutil.rmtree(directory)

    def _safe_case_segment(self, value: str) -> str:
        """Mirror project_core workspace path segment safety for lookups."""
        return value.replace("/", "_").replace("\\", "_").strip()

    def _find_existing_raw_input(self, *, subject_id: str, acquisition_date: date) -> Path | None:
        """Return the first staged raw NIfTI file for this case, if one exists.

        CaseWorkspace.raw_path depends on the raw filename. During creation we
        know the uploaded filename, but during later lookup we only know
        subject_id + acquisition_date from the database. Without rediscovering
        the staged input file, workspace.raw_path would point to a placeholder
        name and raw_uploaded would incorrectly become false after refresh.
        """
        input_dir = (
            Path(self.settings.input_mri_dir)
            / self._safe_case_segment(subject_id)
            / self._safe_case_segment(acquisition_date.isoformat())
        )
        if not input_dir.exists() or not input_dir.is_dir():
            return None

        for candidate in input_dir.iterdir():
            if not candidate.is_file():
                continue
            name = candidate.name.lower()
            if name.endswith(".nii") or name.endswith(".nii.gz"):
                return candidate

        return None

    def get_case_workspace(self, *, subject_id: str, acquisition_date: date) -> Any:
        raw_path = self._find_existing_raw_input(
            subject_id=subject_id,
            acquisition_date=acquisition_date,
        ) or Path("__lookup_case_placeholder__.nii.gz")

        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=raw_path,
        )
        return build_case_workspace(case, self.settings)
    
    def rename_case_workspace(
        self,
        *,
        subject_id: str,
        old_acquisition_date: date,
        new_acquisition_date: date,
        overwrite: bool = False,
    ) -> Any:
        placeholder_raw = Path("__renamed_case_placeholder__.nii.gz")

        old_case = MRICase(
            subject_id=subject_id,
            acquisition_date=old_acquisition_date.isoformat(),
            raw_path=placeholder_raw,
        )

        new_case = MRICase(
            subject_id=subject_id,
            acquisition_date=new_acquisition_date.isoformat(),
            raw_path=placeholder_raw,
        )

        provider = FileSystemWorkspaceProvider(
            self.settings,
            create_directories=False,
        )

        return provider.rename_workspace(
            old_case,
            new_case,
            overwrite=overwrite,
            prune_empty_subject_dirs=True,
        )
    

__all__ = ["ProjectCaseWorkspaceGateway", "WorkspaceGateway"]
