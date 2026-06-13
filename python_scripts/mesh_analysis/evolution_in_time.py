from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence, TYPE_CHECKING

from ..project_core.domain import validate_acquisition_date
from .evolution_metrics import (
    _append_optional_float,
    _basic_stats,
    _build_metric_point,
    _build_statistics,
    _compare_metric_group,
    _load_metrics,
    _nested_mapping,
    _require_float,
    _require_mapping,
    _safe_change_percent,
    _safe_ratio_percent,
    _validate_metric_inputs,
)
from .evolution_models import (
    EvolutionCaseMetrics,
    EvolutionMriArtifacts,
    JsonDict,
    MetricBlock,
    _normalize_tissues,
    evolution_artifacts_from_workspaces,
)
from .evolution_visuals import (
    _ComparisonColors,
    _add_comparison_layers,
    _apply_rgba,
    _apply_shared_view_transform,
    _build_nearest_distance_visual_glb,
    _build_pve_difference_visual_glb,
    _combined_geometry_center,
    _export_scene_to_glb_bytes,
    _geometry_vertices,
    _hex_to_rgba,
    _iter_loaded_geometries,
    _load_first_trimesh,
    _load_pve_image,
    _load_resampling_template,
    _pve_data_to_mesh,
    _reference_for_volume_change,
    _require_visual_inputs,
    _resample_pve_data_to_template,
    _sample_volume_at_world_vertices,
    _split_mesh_by_vertex_mask,
    build_visual_comparison_glb as _build_visual_comparison_glb,
)

if TYPE_CHECKING:
    from ..project_core import CaseWorkspace


@dataclass
class MriEvolutionInTime:
    """
    Compare MRI mesh-analysis metrics for one subject across a selected interval.

    The class is intentionally filesystem-aware but API-independent. A FastAPI
    service can build it from CaseWorkspace instances, call build_comparison_json(),
    and expose build_visual_comparison_glb() as an in-memory FileResponse/Response.
    """

    start_date: str
    end_date: str
    mris: list[EvolutionMriArtifacts]

    def __post_init__(self) -> None:
        self.start_date = validate_acquisition_date(self.start_date)
        self.end_date = validate_acquisition_date(self.end_date)

        if date.fromisoformat(self.start_date) > date.fromisoformat(self.end_date):
            raise ValueError("start_date must be lower than or equal to end_date.")

        if not self.mris:
            raise ValueError("At least one MRI artifact set is required.")

        subject_ids = {mri.subject_id for mri in self.mris}
        if len(subject_ids) != 1:
            raise ValueError(
                "All MRI artifact sets must belong to the same subject. "
                f"Received: {sorted(subject_ids)}"
            )

        self.mris = sorted(self.mris, key=lambda mri: mri.acquisition_date)

    @property
    def subject_id(self) -> str:
        return self.mris[0].subject_id

    @classmethod
    def from_workspaces(
        cls,
        *,
        start_date: str,
        end_date: str,
        workspaces: Iterable[CaseWorkspace],
    ) -> "MriEvolutionInTime":
        return cls(
            start_date=start_date,
            end_date=end_date,
            mris=[EvolutionMriArtifacts.from_workspace(workspace) for workspace in workspaces],
        )

    # ------------------------------------------------------------------
    # public JSON/report method
    # ------------------------------------------------------------------

    def build_comparison_json(self) -> JsonDict:
        """
        Build a JSON-serializable comparison report.

        The baseline is the MRI whose acquisition_date is start_date. Every later
        MRI is compared to that baseline. Previous-date comparison starts from the
        second MRI in the selected interval. For the second MRI, the previous
        comparison is intentionally identical to the baseline comparison, because
        the previous date is the baseline date itself.
        """
        selected = self._selected_mris()
        self._validate_metric_inputs(selected)

        loaded = [self._load_metrics(mri) for mri in selected]
        baseline = loaded[0]

        points = [
            self._build_metric_point(
                current=current,
                baseline=baseline,
                previous=loaded[index - 1] if index >= 1 else None,
                index=index,
            )
            for index, current in enumerate(loaded)
        ]

        return {
            "subject_id": self.subject_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "baseline_date": baseline.acquisition_date,
            "dates": [metrics.acquisition_date for metrics in loaded],
            "baseline_values": baseline.values,
            "points": points,
            "statistics": self._build_statistics(points),
            "notes": {
                "ratio_to_baseline_percent": "current_value / baseline_value * 100",
                "change_from_baseline_percent": "(current_value - baseline_value) / baseline_value * 100",
                "change_from_previous_percent": (
                    "computed from the second selected MRI onward; for the second MRI, "
                    "the previous comparison is identical to the baseline comparison"
                ),
                "std_dev": "population standard deviation",
            },
        }

    # ------------------------------------------------------------------
    # public volatile GLB method
    # ------------------------------------------------------------------

    def build_visual_comparison_glb(
        self,
        *,
        target_date: str | None = None,
        tissues: Iterable[str] | None = None,
        comparison_method: str = "pve",
        pve_threshold: float = 0.2,
        distance_threshold_mm: float = 1.0,
        baseline_color: str = "#508cff",
        changed_color: str = "#ff2d2d",
        marching_cubes_step_size: int = 1,
        template_path: Path | str | None = None,
    ) -> bytes:
        """
        Return an in-memory GLB comparing baseline and target acquisitions.

        The exported GLB contains one reference surface split into two mesh
        layers:
        * unchanged_<reference>_<tissue>_mesh
        * changed_<reference>_<tissue>_mesh

        The reference is normally the baseline mesh. If the tissue volume
        increased, the target mesh is used instead so growth can be shown on the
        larger object. The frontend can recolor and change opacity for each layer
        without rebuilding the GLB.
        """
        selected = self._selected_mris()
        target = self._get_target_visual_mri(selected, target_date)
        return _build_visual_comparison_glb(
            selected=selected,
            target=target,
            tissues=tissues,
            comparison_method=comparison_method,
            pve_threshold=pve_threshold,
            distance_threshold_mm=distance_threshold_mm,
            baseline_color=baseline_color,
            changed_color=changed_color,
            marching_cubes_step_size=marching_cubes_step_size,
            template_path=template_path,
        )

    # ------------------------------------------------------------------
    # selected interval and validation
    # ------------------------------------------------------------------

    def _selected_mris(self) -> list[EvolutionMriArtifacts]:
        start = date.fromisoformat(self.start_date)
        end = date.fromisoformat(self.end_date)
        selected = [
            mri
            for mri in self.mris
            if start <= date.fromisoformat(mri.acquisition_date) <= end
        ]

        if not selected:
            raise ValueError(
                f"No MRI acquisitions found between {self.start_date} and {self.end_date}."
            )

        if selected[0].acquisition_date != self.start_date:
            available = ", ".join(mri.acquisition_date for mri in selected)
            raise ValueError(
                "The selected start_date must match a registered MRI acquisition. "
                f"start_date={self.start_date}; available in interval: {available}"
            )

        if selected[-1].acquisition_date != self.end_date:
            available = ", ".join(mri.acquisition_date for mri in selected)
            raise ValueError(
                "The selected end_date must match a registered MRI acquisition. "
                f"end_date={self.end_date}; available in interval: {available}"
            )

        return selected

    def _validate_metric_inputs(self, selected: Sequence[EvolutionMriArtifacts]) -> None:
        _validate_metric_inputs(selected)

    def _get_target_visual_mri(
        self,
        selected: Sequence[EvolutionMriArtifacts],
        target_date: str | None,
    ) -> EvolutionMriArtifacts:
        if target_date is None:
            return selected[-1]

        normalized_target_date = validate_acquisition_date(target_date)
        if normalized_target_date == self.start_date:
            raise ValueError("target_date must be different from start_date for a visual comparison.")

        for mri in selected:
            if mri.acquisition_date == normalized_target_date:
                return mri

        available = ", ".join(mri.acquisition_date for mri in selected)
        raise ValueError(
            f"target_date={normalized_target_date} is not in the selected interval. "
            f"Available dates: {available}"
        )

    # ------------------------------------------------------------------
    # metric loading/comparison wrappers
    # ------------------------------------------------------------------

    def _load_metrics(self, mri: EvolutionMriArtifacts) -> EvolutionCaseMetrics:
        return _load_metrics(mri)

    def _build_metric_point(
        self,
        *,
        current: EvolutionCaseMetrics,
        baseline: EvolutionCaseMetrics,
        previous: EvolutionCaseMetrics | None,
        index: int,
    ) -> JsonDict:
        return _build_metric_point(
            current=current,
            baseline=baseline,
            previous=previous,
            index=index,
        )

    def _compare_metric_group(
        self,
        *,
        current: Mapping[str, float],
        baseline: Mapping[str, float],
        previous: Mapping[str, float] | None,
    ) -> JsonDict:
        return _compare_metric_group(current=current, baseline=baseline, previous=previous)

    def _build_statistics(self, points: Sequence[JsonDict]) -> JsonDict:
        return _build_statistics(points)


__all__ = [
    "MetricBlock",
    "JsonDict",
    "EvolutionMriArtifacts",
    "EvolutionCaseMetrics",
    "MriEvolutionInTime",
    "evolution_artifacts_from_workspaces",
    "_ComparisonColors",
    "_append_optional_float",
    "_basic_stats",
    "_build_nearest_distance_visual_glb",
    "_build_pve_difference_visual_glb",
    "_combined_geometry_center",
    "_export_scene_to_glb_bytes",
    "_hex_to_rgba",
    "_iter_loaded_geometries",
    "_load_first_trimesh",
    "_load_pve_image",
    "_load_resampling_template",
    "_normalize_tissues",
    "_require_float",
    "_require_mapping",
    "_resample_pve_data_to_template",
    "_safe_change_percent",
    "_safe_ratio_percent",
    "_sample_volume_at_world_vertices",
    "_split_mesh_by_vertex_mask",
]
