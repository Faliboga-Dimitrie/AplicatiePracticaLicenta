from __future__ import annotations

from datetime import date
from pathlib import Path

from ..project_core import (
    CaseWorkspace,
    FileSystemWorkspaceProvider,
    MRICase,
    Settings,
    build_case_workspace,
)
from ..project_core.ports import WorkspaceGateway


class ProjectCaseWorkspaceGateway:
    """
    Adapter from access_control to the project_core filesystem workspace.

    The access-control layer owns database metadata and permission decisions.
    CaseWorkspace/FileSystemWorkspaceProvider own the actual filesystem layout
    and destructive workspace operations.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def _provider(self, *, create_directories: bool = False) -> FileSystemWorkspaceProvider:
        return FileSystemWorkspaceProvider(
            self.settings,
            create_directories=create_directories,
        )

    def create_case_workspace(
        self,
        *,
        subject_id: str,
        acquisition_date: date,
        source_raw_path: Path | None = None,
    ) -> CaseWorkspace:
        if source_raw_path is None:
            raise ValueError("source_raw_path is required to create a CaseWorkspace input file.")

        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=Path(source_raw_path),
        )
        return self._provider(create_directories=True).create_workspace(case)

    def delete_case_workspace(self, *, subject_id: str, acquisition_date: date) -> list[Path]:
        placeholder_raw = Path("__deleted_case_placeholder__.nii.gz")
        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=placeholder_raw,
        )
        return self._provider().delete_workspace(
            case,
            include_input=True,
            prune_empty_subject_dirs=True,
        )

    def delete_subject_workspaces(self, *, subject_id: str) -> list[Path]:
        return self._provider().delete_subject_workspaces(subject_id)


    def stage_case_workspace_delete(
        self,
        *,
        subject_id: str,
        acquisition_date: date,
    ) -> list[tuple[Path, Path]]:
        placeholder_raw = Path("__staged_delete_case_placeholder__.nii.gz")
        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=placeholder_raw,
        )
        return self._provider().stage_workspace_delete(
            case,
            include_input=True,
        )

    def stage_subject_workspaces_delete(self, *, subject_id: str) -> list[tuple[Path, Path]]:
        return self._provider().stage_subject_workspaces_delete(subject_id)

    def commit_staged_delete(self, staged: list[tuple[Path, Path]]) -> list[Path]:
        return self._provider().commit_staged_delete(staged)

    def rollback_staged_delete(self, staged: list[tuple[Path, Path]]) -> None:
        self._provider().rollback_staged_delete(staged)

    def _find_existing_raw_input(self, *, subject_id: str, acquisition_date: date) -> Path | None:
        """Return the first staged raw NIfTI file for this case, if one exists.

        CaseWorkspace.raw_path depends on the raw filename. During creation we
        know the uploaded filename, but during later lookup we only know
        subject_id + acquisition_date from the database. Without rediscovering
        the staged input file, workspace.raw_path would point to a placeholder
        name and raw_uploaded would incorrectly become false after refresh.
        """
        lookup_case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=Path("__lookup_case_placeholder__.nii.gz"),
        )
        input_dir = build_case_workspace(lookup_case, self.settings).input_mri_dir

        if not input_dir.exists() or not input_dir.is_dir():
            return None

        for candidate in input_dir.iterdir():
            if not candidate.is_file():
                continue
            name = candidate.name.lower()
            if name.endswith(".nii") or name.endswith(".nii.gz"):
                return candidate

        return None

    def get_case_workspace(self, *, subject_id: str, acquisition_date: date) -> CaseWorkspace:
        raw_path = self._find_existing_raw_input(
            subject_id=subject_id,
            acquisition_date=acquisition_date,
        ) or Path("__lookup_case_placeholder__.nii.gz")

        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=raw_path,
        )
        return self._provider().get_workspace(case)

    def rename_case_workspace(
        self,
        *,
        subject_id: str,
        old_acquisition_date: date,
        new_acquisition_date: date,
        overwrite: bool = False,
    ) -> list[tuple[Path, Path]]:
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

        return self._provider().rename_workspace(
            old_case,
            new_case,
            overwrite=overwrite,
            prune_empty_subject_dirs=True,
        )


__all__ = ["ProjectCaseWorkspaceGateway", "WorkspaceGateway"]
