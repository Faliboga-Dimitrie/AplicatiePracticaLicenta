from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any, Protocol


class WorkspaceGateway(Protocol):
    """
    Optional adapter used when the service should also touch the filesystem.

    The recommended API flow is still:
        1. database operation succeeds;
        2. API/application layer calls CaseWorkspace through this gateway.

    Injecting a gateway here is useful for a small local application where you
    want the same service method to also create/delete case folders.
    """

    def create_case_workspace(
        self,
        *,
        subject_id: str,
        acquisition_date: date,
        source_raw_path: Path | None = None,
    ) -> Any:
        ...

    def delete_case_workspace(self, *, subject_id: str, acquisition_date: date) -> None:
        ...

    def get_case_workspace(self, *, subject_id: str, acquisition_date: date) -> Any:
        ...


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

        MRICase, FileSystemWorkspaceProvider, _build_case_workspace = self._load_project_core()
        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=Path(source_raw_path),
        )
        provider = FileSystemWorkspaceProvider(self.settings)
        return provider.create_workspace(case)

    def delete_case_workspace(self, *, subject_id: str, acquisition_date: date) -> None:
        MRICase, _FileSystemWorkspaceProvider, build_case_workspace = self._load_project_core()
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

    def get_case_workspace(self, *, subject_id: str, acquisition_date: date) -> Any:
        MRICase, _FileSystemWorkspaceProvider, build_case_workspace = self._load_project_core()
        placeholder_raw = Path("__lookup_case_placeholder__.nii.gz")
        case = MRICase(
            subject_id=subject_id,
            acquisition_date=acquisition_date.isoformat(),
            raw_path=placeholder_raw,
        )
        return build_case_workspace(case, self.settings)

    def _load_project_core(self) -> tuple[Any, Any, Any]:
        try:
            from ..project_core import MRICase, FileSystemWorkspaceProvider, build_case_workspace
        except ImportError:
            from project_core import MRICase, FileSystemWorkspaceProvider, build_case_workspace
        return MRICase, FileSystemWorkspaceProvider, build_case_workspace


__all__ = ["ProjectCaseWorkspaceGateway", "WorkspaceGateway"]
