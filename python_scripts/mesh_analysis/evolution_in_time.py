from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Any, TYPE_CHECKING

from ..project_core.domain import TissueName, TissueSurfaces, TissueVolumes, tissue_key, validate_acquisition_date

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
    csf_wireframe_path: Path
    gm_wireframe_path: Path
    wm_wireframe_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "acquisition_date", validate_acquisition_date(self.acquisition_date))
        object.__setattr__(self, "metrics_json_path", Path(self.metrics_json_path))
        object.__setattr__(self, "csf_mesh_path", Path(self.csf_mesh_path))
        object.__setattr__(self, "gm_mesh_path", Path(self.gm_mesh_path))
        object.__setattr__(self, "wm_mesh_path", Path(self.wm_mesh_path))
        object.__setattr__(self, "csf_wireframe_path", Path(self.csf_wireframe_path))
        object.__setattr__(self, "gm_wireframe_path", Path(self.gm_wireframe_path))
        object.__setattr__(self, "wm_wireframe_path", Path(self.wm_wireframe_path))

    @property
    def mesh_paths(self) -> dict[str, Path]:
        return {
            TissueName.CSF.value: self.csf_mesh_path,
            TissueName.GM.value: self.gm_mesh_path,
            TissueName.WM.value: self.wm_mesh_path,
        }

    @property
    def wireframe_paths(self) -> dict[str, Path]:
        return {
            TissueName.CSF.value: self.csf_wireframe_path,
            TissueName.GM.value: self.gm_wireframe_path,
            TissueName.WM.value: self.wm_wireframe_path,
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
            csf_wireframe_path=workspace.wireframe_paths[TissueName.CSF.value],
            gm_wireframe_path=workspace.wireframe_paths[TissueName.GM.value],
            wm_wireframe_path=workspace.wireframe_paths[TissueName.WM.value],
        )

    def missing_metric_paths(self) -> list[Path]:
        return [self.metrics_json_path] if not self.metrics_json_path.exists() else []

    def missing_visual_paths(
        self,
        *,
        tissues: Iterable[str] | None = None,
        include_meshes: bool = True,
        include_wireframes: bool = True,
    ) -> list[Path]:
        selected_tissues = _normalize_tissues(tissues)
        missing: list[Path] = []

        for tissue in selected_tissues:
            if include_meshes:
                mesh_path = self.mesh_paths[tissue]
                if not mesh_path.exists():
                    missing.append(mesh_path)

            if include_wireframes:
                wireframe_path = self.wireframe_paths[tissue]
                if not wireframe_path.exists():
                    missing.append(wireframe_path)

        return missing


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
        include_meshes: bool = False,
        include_wireframes: bool = True,
    ) -> bytes:
        """
        Return an in-memory GLB overlay of the baseline MRI and a selected target MRI.

        This method does not write anything to the filesystem. It is intended for a
        FastAPI endpoint that returns Response(content=bytes, media_type="model/gltf-binary").

        The current implementation is a robust first visual comparison strategy:
        baseline and target GLB layers are rendered together with different
        materials. By default, it uses wireframes only, because they make shape
        mismatch easier to inspect than two filled translucent surfaces.
        """
        try:
            import numpy as np
            import trimesh
        except ImportError as exc:
            raise RuntimeError(
                "Visual comparison requires trimesh and numpy to be installed."
            ) from exc

        if not include_meshes and not include_wireframes:
            raise ValueError("Visual comparison requires at least one of include_meshes/include_wireframes to be true.")

        selected = self._selected_mris()
        if len(selected) < 2:
            raise ValueError("Visual comparison requires at least two MRI acquisitions in the selected interval.")

        baseline = selected[0]
        target = self._get_target_visual_mri(selected, target_date)
        selected_tissues = _normalize_tissues(tissues)

        missing = baseline.missing_visual_paths(
            tissues=selected_tissues,
            include_meshes=include_meshes,
            include_wireframes=include_wireframes,
        )
        missing.extend(
            target.missing_visual_paths(
                tissues=selected_tissues,
                include_meshes=include_meshes,
                include_wireframes=include_wireframes,
            )
        )
        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Cannot build visual comparison GLB. Missing files:\n{missing_str}")

        scene = trimesh.Scene()
        base_rgba = (80, 140, 255, 75)
        target_rgba = (255, 90, 60, 115)
        base_wire_rgba = (80, 140, 255, 180)
        target_wire_rgba = (255, 90, 60, 220)

        for tissue in selected_tissues:
            if include_meshes:
                self._add_loaded_glb_to_scene(
                    scene=scene,
                    path=baseline.mesh_paths[tissue],
                    prefix=f"baseline_{baseline.acquisition_date}_{tissue}_mesh",
                    rgba=base_rgba,
                    trimesh_module=trimesh,
                    numpy_module=np,
                )
                self._add_loaded_glb_to_scene(
                    scene=scene,
                    path=target.mesh_paths[tissue],
                    prefix=f"target_{target.acquisition_date}_{tissue}_mesh",
                    rgba=target_rgba,
                    trimesh_module=trimesh,
                    numpy_module=np,
                )

            if include_wireframes:
                self._add_loaded_glb_to_scene(
                    scene=scene,
                    path=baseline.wireframe_paths[tissue],
                    prefix=f"baseline_{baseline.acquisition_date}_{tissue}_wireframe",
                    rgba=base_wire_rgba,
                    trimesh_module=trimesh,
                    numpy_module=np,
                )
                self._add_loaded_glb_to_scene(
                    scene=scene,
                    path=target.wireframe_paths[tissue],
                    prefix=f"target_{target.acquisition_date}_{tissue}_wireframe",
                    rgba=target_wire_rgba,
                    trimesh_module=trimesh,
                    numpy_module=np,
                )

        exported = scene.export(file_type="glb")
        if isinstance(exported, bytes):
            return exported
        if isinstance(exported, bytearray):
            return bytes(exported)
        if isinstance(exported, str):
            return exported.encode("utf-8")

        raise TypeError(f"Unexpected GLB export type: {type(exported)!r}")

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
        missing: list[Path] = []
        for mri in selected:
            missing.extend(mri.missing_metric_paths())

        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Cannot build MRI evolution JSON. Missing metrics files:\n{missing_str}")

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
    # metric loading/comparison
    # ------------------------------------------------------------------

    def _load_metrics(self, mri: EvolutionMriArtifacts) -> EvolutionCaseMetrics:
        with mri.metrics_json_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        volumes = TissueVolumes.from_mapping(_require_mapping(payload, "volumes")).as_tissue_dict()
        surfaces = TissueSurfaces.from_mapping(_require_mapping(payload, "surfaces")).as_tissue_dict()

        return EvolutionCaseMetrics(
            subject_id=mri.subject_id,
            acquisition_date=mri.acquisition_date,
            volumes=volumes,
            surfaces=surfaces,
        )

    def _build_metric_point(
        self,
        *,
        current: EvolutionCaseMetrics,
        baseline: EvolutionCaseMetrics,
        previous: EvolutionCaseMetrics | None,
        index: int,
    ) -> JsonDict:
        return {
            "index": index,
            "acquisition_date": current.acquisition_date,
            "is_baseline": current.acquisition_date == baseline.acquisition_date,
            "compared_to_baseline_date": baseline.acquisition_date,
            "compared_to_previous_date": previous.acquisition_date if previous is not None else None,
            "volumes_mm3": self._compare_metric_group(
                current=current.volumes,
                baseline=baseline.volumes,
                previous=previous.volumes if previous is not None else None,
            ),
            "surfaces_mm2": self._compare_metric_group(
                current=current.surfaces,
                baseline=baseline.surfaces,
                previous=previous.surfaces if previous is not None else None,
            ),
        }

    def _compare_metric_group(
        self,
        *,
        current: Mapping[str, float],
        baseline: Mapping[str, float],
        previous: Mapping[str, float] | None,
    ) -> JsonDict:
        compared: JsonDict = {}

        for tissue in _normalize_tissues(None):
            value = float(current[tissue])
            baseline_value = float(baseline[tissue])
            previous_value = float(previous[tissue]) if previous is not None else None

            compared[tissue] = {
                "value": value,
                "baseline_value": baseline_value,
                "absolute_change_from_baseline": value - baseline_value,
                "ratio_to_baseline_percent": _safe_ratio_percent(value, baseline_value),
                "change_from_baseline_percent": _safe_change_percent(value, baseline_value),
                "previous_value": previous_value,
                "absolute_change_from_previous": None if previous_value is None else value - previous_value,
                "ratio_to_previous_percent": None if previous_value is None else _safe_ratio_percent(value, previous_value),
                "change_from_previous_percent": None if previous_value is None else _safe_change_percent(value, previous_value),
            }

        return compared

    def _build_statistics(self, points: Sequence[JsonDict]) -> JsonDict:
        stats: JsonDict = {}

        for metric_group in ("volumes_mm3", "surfaces_mm2"):
            group_stats: JsonDict = {}

            for tissue in _normalize_tissues(None):
                values: list[float] = []
                baseline_changes: list[float] = []
                previous_changes: list[float] = []

                for point in points:
                    tissue_payload = _nested_mapping(point, metric_group, tissue)
                    values.append(float(tissue_payload["value"]))
                    _append_optional_float(baseline_changes, tissue_payload.get("change_from_baseline_percent"))
                    _append_optional_float(previous_changes, tissue_payload.get("change_from_previous_percent"))

                # The first baseline change is always 0.0. Excluding it makes the
                # reported average describe actual follow-up change, not baseline identity.
                baseline_changes_without_first = baseline_changes[1:] if len(baseline_changes) > 1 else []

                group_stats[tissue] = {
                    "values": _basic_stats(values),
                    "change_from_baseline_percent": _basic_stats(baseline_changes_without_first),
                    "change_from_previous_percent": _basic_stats(previous_changes),
                }

            stats[metric_group] = group_stats

        return stats

    # ------------------------------------------------------------------
    # visual helper internals
    # ------------------------------------------------------------------

    def _add_loaded_glb_to_scene(
        self,
        *,
        scene: Any,
        path: Path,
        prefix: str,
        rgba: tuple[int, int, int, int],
        trimesh_module: Any,
        numpy_module: Any,
    ) -> None:
        loaded = trimesh_module.load(str(path), force="scene")
        geometry_items = getattr(loaded, "geometry", {})

        if not geometry_items:
            raise ValueError(f"No geometry found inside GLB file: {path}")

        for index, geometry in enumerate(geometry_items.values()):
            prepared = geometry.copy()
            _apply_rgba(prepared, rgba, trimesh_module=trimesh_module, numpy_module=numpy_module)
            scene.add_geometry(prepared, node_name=f"{prefix}_{index}", geom_name=f"{prefix}_{index}")


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


def _require_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, float]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"Metrics JSON is missing an object field named '{key}'.")
    return value  # type: ignore[return-value]


def _safe_ratio_percent(value: float, reference: float) -> float | None:
    if math.isclose(reference, 0.0):
        return None
    return (value / reference) * 100.0


def _safe_change_percent(value: float, reference: float) -> float | None:
    if math.isclose(reference, 0.0):
        return None
    return ((value - reference) / reference) * 100.0


def _append_optional_float(values: list[float], value: object) -> None:
    if value is None:
        return
    values.append(float(value))


def _basic_stats(values: Sequence[float]) -> JsonDict:
    if not values:
        return {
            "count": 0,
            "average": None,
            "std_dev": None,
            "min": None,
            "max": None,
        }

    return {
        "count": len(values),
        "average": statistics.fmean(values),
        "std_dev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _nested_mapping(payload: Mapping[str, object], first_key: str, second_key: str) -> Mapping[str, object]:
    first = payload.get(first_key)
    if not isinstance(first, Mapping):
        raise ValueError(f"Expected mapping at key '{first_key}'.")

    second = first.get(second_key)
    if not isinstance(second, Mapping):
        raise ValueError(f"Expected mapping at key '{first_key}.{second_key}'.")

    return second


def _apply_rgba(
    geometry: Any,
    rgba: tuple[int, int, int, int],
    *,
    trimesh_module: Any,
    numpy_module: Any,
) -> None:
    if isinstance(geometry, trimesh_module.Trimesh):
        material = trimesh_module.visual.material.PBRMaterial(
            baseColorFactor=list(rgba),
            alphaMode="BLEND",
            doubleSided=True,
        )
        geometry.visual = trimesh_module.visual.TextureVisuals(material=material)
        return

    # Path3D objects used for wireframes expose a colors collection. If that is
    # unavailable for a loaded GLB variant, leaving the geometry untouched is safer
    # than failing the whole visual comparison.
    if hasattr(geometry, "entities") and hasattr(geometry, "colors"):
        color = numpy_module.array(rgba, dtype=numpy_module.uint8)
        geometry.colors = numpy_module.tile(color, (len(geometry.entities), 1))


__all__ = [
    "EvolutionMriArtifacts",
    "EvolutionCaseMetrics",
    "MriEvolutionInTime",
    "evolution_artifacts_from_workspaces",
]
