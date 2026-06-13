from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Mapping


class TissueName(str, Enum):
    """
    Canonical tissue identifiers used across the application.

    Keeping these names centralized prevents each layer from inventing its own
    spelling for the same tissue type. Values are lowercase because they are
    convenient as dictionary keys and API/JSON values.
    """

    CSF = "csf"
    GM = "gm"
    WM = "wm"


TISSUE_NAMES: tuple[TissueName, ...] = (
    TissueName.CSF,
    TissueName.GM,
    TissueName.WM,
)


def tissue_key(tissue: TissueName | str) -> str:
    """
    Normalize a tissue identifier to the canonical lowercase string key.
    """
    if isinstance(tissue, TissueName):
        return tissue.value
    return tissue.strip().lower()


def strip_nii_suffix(path: Path) -> str:
    """
    Remove .nii or .nii.gz from a filename and return the case-like base name.
    """
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


def validate_acquisition_date(value: str) -> str:
    """
    Validate and normalize acquisition/session dates used in folder names.

    The project convention is ISO format: YYYY-MM-DD.
    """
    normalized = value.strip()
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"Invalid acquisition date '{value}'. Expected ISO format YYYY-MM-DD."
        ) from exc
    return normalized


def _looks_like_acquisition_date(value: str) -> bool:
    try:
        validate_acquisition_date(value)
        return True
    except ValueError:
        return False


def _infer_subject_and_date_from_path(path: Path) -> tuple[str | None, str | None]:
    """
    Infer subject/date from the standardized input layout when possible.

    Supported examples:
        input_mri/<subject_id>/<YYYY-MM-DD>/<file>.nii.gz
        input_mri/<subject_id>/<YYYY-MM-DD>/mri/<file>.nii.gz
    """
    parent = path.parent

    # Optional inner folder, useful if the professor wants a literal mri/ folder.
    if parent.name.lower() == "mri":
        date_dir = parent.parent
        subject_dir = date_dir.parent
    else:
        date_dir = parent
        subject_dir = parent.parent

    if not _looks_like_acquisition_date(date_dir.name):
        return None, None

    return subject_dir.name, validate_acquisition_date(date_dir.name)


@dataclass(frozen=True)
class MRICase:
    """
    Identity of one MRI acquisition/session.

    A subject can now have multiple MRI acquisitions. Therefore the stable case
    identity is the pair (subject_id, acquisition_date), while raw_path points to
    the raw NIfTI source selected for this acquisition.
    """

    subject_id: str
    acquisition_date: str
    raw_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "acquisition_date", validate_acquisition_date(self.acquisition_date))
        object.__setattr__(self, "raw_path", Path(self.raw_path))

    @property
    def case_id(self) -> str:
        """Human-readable unique identifier for this subject acquisition."""
        return f"{self.subject_id}_{self.acquisition_date}"


@dataclass(frozen=True)
class TissueVolumes:
    """
    Tissue volume metrics in cubic millimetres.
    """

    csf_mm3: float
    gm_mm3: float
    wm_mm3: float

    def to_dict(self) -> dict[str, float]:
        return {
            "csf_mm3": self.csf_mm3,
            "gm_mm3": self.gm_mm3,
            "wm_mm3": self.wm_mm3,
        }

    def as_tissue_dict(self) -> dict[str, float]:
        """
        Return values keyed by canonical tissue name rather than metric field.
        """
        return {
            TissueName.CSF.value: self.csf_mm3,
            TissueName.GM.value: self.gm_mm3,
            TissueName.WM.value: self.wm_mm3,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> "TissueVolumes":
        """
        Build volumes from either metric-style keys or tissue-style keys.

        Accepted examples:
            {"csf_mm3": 10.0, "gm_mm3": 20.0, "wm_mm3": 30.0}
            {"csf": 10.0, "gm": 20.0, "wm": 30.0}
        """
        return cls(
            csf_mm3=float(data.get("csf_mm3", data.get("csf", 0.0))),
            gm_mm3=float(data.get("gm_mm3", data.get("gm", 0.0))),
            wm_mm3=float(data.get("wm_mm3", data.get("wm", 0.0))),
        )


@dataclass(frozen=True)
class TissueSurfaces:
    """
    Tissue surface-area metrics in square millimetres.

    The name deliberately avoids saying "mesh surface" because the domain only
    cares about the final metric. The current implementation may estimate it
    from a marching-cubes mesh, but a future implementation could use another
    method without changing the domain model.
    """

    csf_mm2: float
    gm_mm2: float
    wm_mm2: float

    def to_dict(self) -> dict[str, float]:
        return {
            "csf_mm2": self.csf_mm2,
            "gm_mm2": self.gm_mm2,
            "wm_mm2": self.wm_mm2,
        }

    def as_tissue_dict(self) -> dict[str, float]:
        """
        Return values keyed by canonical tissue name rather than metric field.
        """
        return {
            TissueName.CSF.value: self.csf_mm2,
            TissueName.GM.value: self.gm_mm2,
            TissueName.WM.value: self.wm_mm2,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> "TissueSurfaces":
        """
        Build surfaces from either metric-style keys or tissue-style keys.

        Accepted examples:
            {"csf_mm2": 10.0, "gm_mm2": 20.0, "wm_mm2": 30.0}
            {"csf": 10.0, "gm": 20.0, "wm": 30.0}
        """
        return cls(
            csf_mm2=float(data.get("csf_mm2", data.get("csf", 0.0))),
            gm_mm2=float(data.get("gm_mm2", data.get("gm", 0.0))),
            wm_mm2=float(data.get("wm_mm2", data.get("wm", 0.0))),
        )


@dataclass(frozen=True)
class CaseMetrics:
    """
    Scientific/analytical metrics produced for one processed MRI acquisition.
    """

    volumes: TissueVolumes
    surfaces: TissueSurfaces

    def to_dict(self) -> dict[str, object]:
        return {
            "volumes": self.volumes.to_dict(),
            "surfaces": self.surfaces.to_dict(),
        }


@dataclass(frozen=True)
class MeshAnalysisResult:
    """
    Current mesh-analysis result shape used by the web/API processing flow.

    acquisition_date is optional to keep older deserialization paths tolerant,
    but new code should fill it from CaseWorkspace.
    """

    subject_id: str
    volumes: TissueVolumes
    surfaces: TissueSurfaces
    acquisition_date: str | None = None

    @property
    def case_id(self) -> str:
        if self.acquisition_date is None:
            return self.subject_id
        return f"{self.subject_id}_{self.acquisition_date}"

    @property
    def metrics(self) -> CaseMetrics:
        return CaseMetrics(volumes=self.volumes, surfaces=self.surfaces)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "subject_id": self.subject_id,
            **self.metrics.to_dict(),
        }
        if self.acquisition_date is not None:
            payload["acquisition_date"] = self.acquisition_date
        return payload


__all__ = [
    "TissueName",
    "TISSUE_NAMES",
    "tissue_key",
    "strip_nii_suffix",
    "validate_acquisition_date",
    "MRICase",
    "TissueVolumes",
    "TissueSurfaces",
    "CaseMetrics",
    "MeshAnalysisResult",
]
