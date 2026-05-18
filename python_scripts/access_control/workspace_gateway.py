from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any
from ..project_core import MRICase, FileSystemWorkspaceProvider, build_case_workspace
from ..project_core.ports import WorkspaceGateway

class ProjectCaseWorkspaceGateway:
    """
    Adapter from access_control to your existing project_core workspace.

    It supports both import styles:
    - package style:     from python_scripts.access_control import ...
    - top-level style:   from access_control import ...
    """

    def __init__(self, settings: Any):
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
            Path(self.settings.qc_dir) / subject_id,
            Path(self.settings.mesh_dir) / subject_id,
        ]

        for directory in subject_dirs:
            if directory.exists():
                shutil.rmtree(directory)

    def get_case_workspace(self, *, subject_id: str, acquisition_date: date) -> Any:
        placeholder_raw = Path("__lookup_case_placeholder__.nii.gz")
        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=placeholder_raw,
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
