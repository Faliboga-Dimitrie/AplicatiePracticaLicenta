from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


def strip_nii_suffix(path: Path) -> str:
    """
    Remove .nii or .nii.gz from a filename and return the stem-like base name.
    """
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


@dataclass(frozen=True)
class MRICase:
    """
    Represents one raw MRI case.
    Stores only identity + raw input path, not loaded image data.
    """
    subject_id: str
    raw_path: Path

    @classmethod
    def from_input_path(cls, input_path: str | Path, subject_id: str | None = None) -> "MRICase":
        path = Path(input_path).resolve()
        sid = subject_id or strip_nii_suffix(path)
        return cls(subject_id=sid, raw_path=path)


@dataclass(frozen=True)
class CasePaths:
    """
    Stores all expected paths for one MRI case across the preprocessing pipeline.

    Important:
    - This class stores paths only, not loaded MRI objects.
    - Each stage should load only the image it currently needs.
    """
    subject_id: str
    raw_path: Path

    reoriented_dir: Path
    hd_bet_dir: Path
    fast_dir: Path
    qc_dir: Path

    # ---------- directories ----------
    @property
    def stage_dirs(self) -> list[Path]:
        return [
            self.reoriented_dir,
            self.hd_bet_dir,
            self.fast_dir,
            self.qc_dir,
        ]

    def ensure_stage_dirs(self) -> None:
        """
        Create all per-subject stage directories for this case.
        Safe to call multiple times.
        """
        for directory in self.stage_dirs:
            directory.mkdir(parents=True, exist_ok=True)

    # ---------- reorientation ----------
    @property
    def reoriented_path(self) -> Path:
        return self.reoriented_dir / f"{self.subject_id}_reo.nii.gz"

    # ---------- HD-BET ----------
    @property
    def skull_stripped_path(self) -> Path:
        return self.hd_bet_dir / f"{self.subject_id}_bet.nii.gz"

    @property
    def skull_stripped_mask_path(self) -> Path:
        return self.hd_bet_dir / f"{self.subject_id}_bet_mask.nii.gz"

    # ---------- FAST ----------
    @property
    def fast_prefix(self) -> Path:
        """
        FAST uses a prefix, then generates multiple files from it.
        Example: <prefix>_pve_0.nii.gz
        """
        return self.fast_dir / f"{self.subject_id}"

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
        return self.fast_dir / f"{self.subject_id}_pve_seg.nii.gz"

    @property
    def fast_seg_path(self) -> Path:
        return self.fast_dir / f"{self.subject_id}_seg.nii.gz"

    # ---------- QC ----------
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
    def qc_atlas_png(self) -> Path:
        return self.qc_dir / f"{self.subject_id}_atlas_qc.png"

    # ---------- existence helpers ----------
    @property
    def has_reoriented(self) -> bool:
        return self.reoriented_path.exists()

    @property
    def has_skull_stripped(self) -> bool:
        return self.skull_stripped_path.exists()

    @property
    def has_skull_mask(self) -> bool:
        return self.skull_stripped_mask_path.exists()

    @property
    def has_fast_outputs(self) -> bool:
        required = [
            self.fast_mixeltype_path,
            self.fast_pve_csf_path,
            self.fast_pve_gm_path,
            self.fast_pve_wm_path,
            self.fast_pve_seg_path,
            self.fast_seg_path,
        ]
        return all(path.exists() for path in required)
    
    @property
    def fast_input_path(self) -> Path:
        return self.skull_stripped_path


def build_case_paths(case: MRICase, settings: Any) -> CasePaths:
    """
    Build all per-subject output paths from a global settings object.

    Expected settings fields:
        - reoriented_dir
        - hd_bet_dir
        - fast_dir
        - qc_dir
    """
    subject_id = case.subject_id

    return CasePaths(
        subject_id=subject_id,
        raw_path=case.raw_path,

        reoriented_dir=Path(settings.reoriented_dir) / subject_id,
        hd_bet_dir=Path(settings.hd_bet_dir) / subject_id,
        fast_dir=Path(settings.fast_dir) / subject_id,
        qc_dir=Path(settings.qc_dir) / subject_id,
    )