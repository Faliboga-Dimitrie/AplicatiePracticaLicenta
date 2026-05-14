from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import Settings
from .domain import MRICase, TISSUE_NAMES, TissueName, tissue_key


def _safe_case_segment(value: str) -> str:
    """Keep filesystem path segments simple and prevent accidental nesting."""
    return value.replace("/", "_").replace("\\", "_").strip()


def _case_dir(root: Path, case: MRICase) -> Path:
    """Standard subject/acquisition directory for a given stage root."""
    return (
        Path(root)
        / _safe_case_segment(case.subject_id)
        / _safe_case_segment(case.acquisition_date)
    )


@dataclass(frozen=True)
class CaseWorkspace:
    """
    Local working area for one MRI acquisition.

    The workspace now separates:
        - source_raw_path: the file selected by the caller/importer;
        - raw_path: the standardized raw file inside input_mri/<subject>/<date>/.

    The processing tools should read from workspace.raw_path after the workspace
    provider has copied/staged the source file into the standardized input area.
    """

    subject_id: str
    acquisition_date: str
    source_raw_path: Path
    raw_path: Path

    input_mri_dir: Path
    reoriented_dir: Path
    hd_bet_dir: Path
    fast_dir: Path
    qc_dir: Path
    mesh_dir: Path

    @property
    def case_id(self) -> str:
        return f"{self.subject_id}_{self.acquisition_date}"

    # ------------------------------------------------------------------
    # directories
    # ------------------------------------------------------------------

    @property
    def stage_dirs(self) -> list[Path]:
        return [
            self.input_mri_dir,
            self.reoriented_dir,
            self.hd_bet_dir,
            self.fast_dir,
            self.qc_dir,
            self.mesh_dir,
        ]

    def ensure_directories(self) -> None:
        """
        Create all local workspace directories for this acquisition.
        Safe to call multiple times.
        """
        for directory in self.stage_dirs:
            directory.mkdir(parents=True, exist_ok=True)

    def ensure_input_file(self, *, overwrite: bool = False) -> None:
        """
        Copy the caller-selected raw MRI into the standardized input folder.

        If the source is already the canonical workspace raw_path, nothing is
        copied. Existing canonical input is preserved unless overwrite=True.
        """
        self.input_mri_dir.mkdir(parents=True, exist_ok=True)

        source = Path(self.source_raw_path).resolve()
        target = Path(self.raw_path).resolve()

        if source == target:
            return

        if not source.exists():
            raise FileNotFoundError(f"Raw MRI source file does not exist: {source}")
        if not source.is_file():
            raise ValueError(f"Raw MRI source path is not a file: {source}")

        if target.exists() and not overwrite:
            return

        shutil.copy2(source, target)

    # ------------------------------------------------------------------
    # reorientation
    # ------------------------------------------------------------------

    @property
    def reoriented_path(self) -> Path:
        return self.reoriented_dir / f"{self.subject_id}_reo.nii.gz"

    @property
    def has_reoriented(self) -> bool:
        return self.reoriented_path.exists()

    # ------------------------------------------------------------------
    # HD-BET
    # ------------------------------------------------------------------

    @property
    def skull_stripped_path(self) -> Path:
        return self.hd_bet_dir / f"{self.subject_id}_bet.nii.gz"

    @property
    def skull_stripped_mask_path(self) -> Path:
        return self.hd_bet_dir / f"{self.subject_id}_bet_mask.nii.gz"

    # ------------------------------------------------------------------
    # FAST
    # ------------------------------------------------------------------

    @property
    def fast_input_path(self) -> Path:
        return self.skull_stripped_path

    @property
    def fast_prefix(self) -> Path:
        """
        FAST receives a prefix and generates several files from it.
        Example: <prefix>_pve_0.nii.gz
        """
        return self.fast_dir / self.subject_id

    @property
    def fast_mixeltype_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_mixeltype.nii.gz"

    @property
    def fast_pve_csf_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_pve_0.nii.gz"

    @property
    def fast_pve_gm_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_pve_1.nii.gz"

    @property
    def fast_pve_wm_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_pve_2.nii.gz"

    @property
    def fast_pve_seg_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_pveseg.nii.gz"

    @property
    def fast_seg_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_seg.nii.gz"

    @property
    def fast_pve_paths(self) -> dict[str, Path]:
        return {
            TissueName.CSF.value: self.fast_pve_csf_path,
            TissueName.GM.value: self.fast_pve_gm_path,
            TissueName.WM.value: self.fast_pve_wm_path,
        }

    @property
    def fast_output_paths(self) -> list[Path]:
        return [
            self.fast_mixeltype_path,
            self.fast_pve_csf_path,
            self.fast_pve_gm_path,
            self.fast_pve_wm_path,
            self.fast_pve_seg_path,
            self.fast_seg_path,
        ]

    @property
    def has_fast_outputs(self) -> bool:
        return all(path.exists() for path in self.fast_output_paths)

    @property
    def has_fast_pve_outputs(self) -> bool:
        return all(path.exists() for path in self.fast_pve_paths.values())

    @property
    def missing_fast_pve_paths(self) -> list[Path]:
        return [path for path in self.fast_pve_paths.values() if not path.exists()]

    # ------------------------------------------------------------------
    # QC
    # ------------------------------------------------------------------

    @property
    def qc_reorientation_png(self) -> Path:
        return self.qc_dir / f"{self.subject_id}_reorientation_qc.png"

    @property
    def qc_bet_png(self) -> Path:
        return self.qc_dir / f"{self.subject_id}_bet_qc.png"

    @property
    def qc_fast_png(self) -> Path:
        return self.qc_dir / f"{self.subject_id}_fast_qc.png"

    @property
    def qc_paths(self) -> dict[str, Path]:
        return {
            "reorientation": self.qc_reorientation_png,
            "hd_bet": self.qc_bet_png,
            "fast": self.qc_fast_png,
        }

    @property
    def existing_qc_paths(self) -> dict[str, Path]:
        return {name: path for name, path in self.qc_paths.items() if path.exists()}

    # ------------------------------------------------------------------
    # meshes / wireframes / metrics
    # ------------------------------------------------------------------

    def mesh_path_for(self, tissue: TissueName | str) -> Path:
        key = tissue_key(tissue)
        return self.mesh_dir / f"{self.subject_id}_{key}_mesh.glb"

    def wireframe_path_for(self, tissue: TissueName | str) -> Path:
        key = tissue_key(tissue)
        return self.mesh_dir / f"{self.subject_id}_{key}_wireframe.glb"

    @property
    def mesh_csf_mesh_path(self) -> Path:
        return self.mesh_path_for(TissueName.CSF)

    @property
    def mesh_gm_mesh_path(self) -> Path:
        return self.mesh_path_for(TissueName.GM)

    @property
    def mesh_wm_mesh_path(self) -> Path:
        return self.mesh_path_for(TissueName.WM)

    @property
    def wireframe_csf_path(self) -> Path:
        return self.wireframe_path_for(TissueName.CSF)

    @property
    def wireframe_gm_path(self) -> Path:
        return self.wireframe_path_for(TissueName.GM)

    @property
    def wireframe_wm_path(self) -> Path:
        return self.wireframe_path_for(TissueName.WM)

    @property
    def mesh_metrics_json_path(self) -> Path:
        return self.mesh_dir / f"{self.subject_id}_metrics.json"

    # Preferred shorter name for new code.
    @property
    def metrics_json_path(self) -> Path:
        return self.mesh_metrics_json_path

    @property
    def mesh_paths(self) -> dict[str, Path]:
        return {tissue.value: self.mesh_path_for(tissue) for tissue in TISSUE_NAMES}

    @property
    def wireframe_paths(self) -> dict[str, Path]:
        return {tissue.value: self.wireframe_path_for(tissue) for tissue in TISSUE_NAMES}

    @property
    def mesh_output_paths(self) -> list[Path]:
        return [*self.mesh_paths.values(), self.mesh_metrics_json_path]

    @property
    def wireframe_output_paths(self) -> list[Path]:
        return list(self.wireframe_paths.values())

    @property
    def mesh_analysis_output_paths(self) -> list[Path]:
        return [
            *self.mesh_paths.values(),
            *self.wireframe_paths.values(),
            self.mesh_metrics_json_path,
        ]

    @property
    def has_complete_mesh_outputs(self) -> bool:
        return all(path.exists() for path in self.mesh_output_paths)

    @property
    def has_any_mesh_outputs(self) -> bool:
        return any(path.exists() for path in self.mesh_output_paths)

    @property
    def has_complete_wireframe_outputs(self) -> bool:
        return all(path.exists() for path in self.wireframe_output_paths)

    @property
    def has_any_wireframe_outputs(self) -> bool:
        return any(path.exists() for path in self.wireframe_output_paths)

    @property
    def has_complete_mesh_analysis_outputs(self) -> bool:
        return all(path.exists() for path in self.mesh_analysis_output_paths)

    @property
    def has_any_mesh_analysis_outputs(self) -> bool:
        return any(path.exists() for path in self.mesh_analysis_output_paths)

    def existing_paths(self, paths: Iterable[Path]) -> list[Path]:
        return [path for path in paths if path.exists()]


class FileSystemWorkspaceProvider:
    """
    Default WorkspaceProvider implementation backed by the local filesystem.

    New layout:
        input_mri/<subject>/<date>/...
        processed_mri/reoriented/<subject>/<date>/...
        processed_mri/hd_bet/<subject>/<date>/...
        processed_mri/fast/<subject>/<date>/...
        processed_mri/qc/<subject>/<date>/...
        processed_mri/meshes/<subject>/<date>/...
    """

    def __init__(self, settings: Settings, *, create_directories: bool = True):
        self.settings = settings
        self.create_directories = create_directories

    def create_workspace(self, case: MRICase) -> CaseWorkspace:
        workspace = build_case_workspace(case, self.settings)

        if self.create_directories:
            workspace.ensure_directories()
            workspace.ensure_input_file(overwrite=self.settings.overwrite)

        return workspace


def build_case_workspace(case: MRICase, settings: Settings) -> CaseWorkspace:
    """
    Build the local workspace paths for one subject/date acquisition without
    creating directories.
    """
    input_mri_dir = _case_dir(Path(settings.input_mri_dir), case)

    return CaseWorkspace(
        subject_id=case.subject_id,
        acquisition_date=case.acquisition_date,
        source_raw_path=case.raw_path,
        raw_path=input_mri_dir / Path(case.raw_path).name,
        input_mri_dir=input_mri_dir,
        reoriented_dir=_case_dir(Path(settings.reoriented_dir), case),
        hd_bet_dir=_case_dir(Path(settings.hd_bet_dir), case),
        fast_dir=_case_dir(Path(settings.fast_dir), case),
        qc_dir=_case_dir(Path(settings.qc_dir), case),
        mesh_dir=_case_dir(Path(settings.mesh_dir), case),
    )


def build_case_paths(case: MRICase, settings: Settings) -> CaseWorkspace:
    return build_case_workspace(case, settings)


__all__ = [
    "CaseWorkspace",
    "FileSystemWorkspaceProvider",
    "build_case_workspace",
    "build_case_paths",
]
