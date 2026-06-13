from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from ..project_core.domain import TissueName, tissue_key, validate_acquisition_date

if TYPE_CHECKING:
    from ..project_core import CaseWorkspace

MetricBlock = dict[str, dict[str, float]]
JsonDict = dict[str, object]


@dataclass(frozen=True)
class EvolutionMriArtifacts:
    """
    Small value object describing the files needed to compare one MRI acquisition
    through time.

    It deliberately stores only paths, not loaded meshes or metrics. This keeps the
    comparison object cheap to create and friendly to a future API endpoint.
    """

    subject_id: str
    acquisition_date: str
    metrics_json_path: Path
    csf_mesh_path: Path
    gm_mesh_path: Path
    wm_mesh_path: Path
    csf_pve_path: Path
    gm_pve_path: Path
    wm_pve_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "acquisition_date", validate_acquisition_date(self.acquisition_date))
        object.__setattr__(self, "metrics_json_path", Path(self.metrics_json_path))
        object.__setattr__(self, "csf_mesh_path", Path(self.csf_mesh_path))
        object.__setattr__(self, "gm_mesh_path", Path(self.gm_mesh_path))
        object.__setattr__(self, "wm_mesh_path", Path(self.wm_mesh_path))
        object.__setattr__(self, "csf_pve_path", Path(self.csf_pve_path))
        object.__setattr__(self, "gm_pve_path", Path(self.gm_pve_path))
        object.__setattr__(self, "wm_pve_path", Path(self.wm_pve_path))

    @property
    def mesh_paths(self) -> dict[str, Path]:
        return {
            TissueName.CSF.value: self.csf_mesh_path,
            TissueName.GM.value: self.gm_mesh_path,
            TissueName.WM.value: self.wm_mesh_path,
        }

    @property
    def pve_paths(self) -> dict[str, Path]:
        return {
            TissueName.CSF.value: self.csf_pve_path,
            TissueName.GM.value: self.gm_pve_path,
            TissueName.WM.value: self.wm_pve_path,
        }

    @classmethod
    def from_workspace(cls, workspace: CaseWorkspace) -> "EvolutionMriArtifacts":
        """
        Build the seven required paths from the existing CaseWorkspace convention.
        """
        return cls(
            subject_id=workspace.subject_id,
            acquisition_date=workspace.acquisition_date,
            metrics_json_path=workspace.metrics_json_path,
            csf_mesh_path=workspace.mesh_paths[TissueName.CSF.value],
            gm_mesh_path=workspace.mesh_paths[TissueName.GM.value],
            wm_mesh_path=workspace.mesh_paths[TissueName.WM.value],
            csf_pve_path=workspace.fast_pve_paths[TissueName.CSF.value],
            gm_pve_path=workspace.fast_pve_paths[TissueName.GM.value],
            wm_pve_path=workspace.fast_pve_paths[TissueName.WM.value],
        )

    def missing_metric_paths(self) -> list[Path]:
        return [self.metrics_json_path] if not self.metrics_json_path.exists() else []

    def missing_visual_paths(
        self,
        *,
        tissues: Iterable[str] | None = None,
        include_meshes: bool = True,
    ) -> list[Path]:
        selected_tissues = _normalize_tissues(tissues)
        missing: list[Path] = []

        for tissue in selected_tissues:
            if include_meshes:
                mesh_path = self.mesh_paths[tissue]
                if not mesh_path.exists():
                    missing.append(mesh_path)

        return missing

    def missing_pve_paths(self, *, tissues: Iterable[str] | None = None) -> list[Path]:
        selected_tissues = _normalize_tissues(tissues)
        return [self.pve_paths[tissue] for tissue in selected_tissues if not self.pve_paths[tissue].exists()]


@dataclass(frozen=True)
class EvolutionCaseMetrics:
    """Loaded volume and surface metrics for one acquisition."""

    subject_id: str
    acquisition_date: str
    volumes: dict[str, float]
    surfaces: dict[str, float]

    @property
    def values(self) -> dict[str, dict[str, float]]:
        return {
            "volumes_mm3": self.volumes,
            "surfaces_mm2": self.surfaces,
        }


def evolution_artifacts_from_workspaces(
    workspaces: Iterable[CaseWorkspace],
) -> list[EvolutionMriArtifacts]:
    """
    Helper function useful for the future API service layer.
    """
    return [EvolutionMriArtifacts.from_workspace(workspace) for workspace in workspaces]


def _normalize_tissues(tissues: Iterable[str] | None) -> tuple[str, ...]:
    if tissues is None:
        return (TissueName.CSF.value, TissueName.GM.value, TissueName.WM.value)

    normalized: list[str] = []
    for tissue in tissues:
        key = tissue_key(tissue)
        if key not in {TissueName.CSF.value, TissueName.GM.value, TissueName.WM.value}:
            raise ValueError(f"Unsupported tissue '{tissue}'. Expected one of: csf, gm, wm.")
        if key not in normalized:
            normalized.append(key)

    if not normalized:
        raise ValueError("At least one tissue must be selected.")

    return tuple(normalized)


__all__ = [
    "MetricBlock",
    "JsonDict",
    "EvolutionMriArtifacts",
    "EvolutionCaseMetrics",
    "evolution_artifacts_from_workspaces",
]
