from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Any, TYPE_CHECKING

from ..project_core.config import settings
from .mesh_extractors import MarchingCubesConfig
from ..project_core.domain import TissueName, TissueSurfaces, TissueVolumes, tissue_key, validate_acquisition_date

if TYPE_CHECKING:
    from ..project_core import CaseWorkspace


MetricBlock = dict[str, dict[str, float]]
JsonDict = dict[str, object]




@dataclass(frozen=True)
class _ComparisonColors:
    baseline: tuple[int, int, int, int]
    changed: tuple[int, int, int, int]

    @classmethod
    def from_hex(
        cls,
        *,
        baseline_color: str,
        changed_color: str,
    ) -> "_ComparisonColors":
        return cls(
            baseline=_hex_to_rgba(baseline_color, default_alpha=210),
            changed=_hex_to_rgba(changed_color, default_alpha=220),
        )


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
    csf_pve_path: Path
    gm_pve_path: Path
    wm_pve_path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "acquisition_date", validate_acquisition_date(self.acquisition_date))
        object.__setattr__(self, "metrics_json_path", Path(self.metrics_json_path))
        object.__setattr__(self, "csf_mesh_path", Path(self.csf_mesh_path))
        object.__setattr__(self, "gm_mesh_path", Path(self.gm_mesh_path))
        object.__setattr__(self, "wm_mesh_path", Path(self.wm_mesh_path))
        object.__setattr__(self, "csf_wireframe_path", Path(self.csf_wireframe_path))
        object.__setattr__(self, "gm_wireframe_path", Path(self.gm_wireframe_path))
        object.__setattr__(self, "wm_wireframe_path", Path(self.wm_wireframe_path))
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
    def wireframe_paths(self) -> dict[str, Path]:
        return {
            TissueName.CSF.value: self.csf_wireframe_path,
            TissueName.GM.value: self.gm_wireframe_path,
            TissueName.WM.value: self.wm_wireframe_path,
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
            csf_wireframe_path=workspace.wireframe_paths[TissueName.CSF.value],
            gm_wireframe_path=workspace.wireframe_paths[TissueName.GM.value],
            wm_wireframe_path=workspace.wireframe_paths[TissueName.WM.value],
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
        try:
            import nibabel as nib
            import numpy as np
            import trimesh
            from nibabel.affines import apply_affine
            from nibabel.processing import resample_from_to
            from scipy.ndimage import map_coordinates
            from scipy.spatial import cKDTree
            from skimage.measure import marching_cubes
        except ImportError as exc:
            raise RuntimeError(
                "Visual comparison requires nibabel, numpy, scipy, trimesh, and scikit-image to be installed."
            ) from exc

        selected = self._selected_mris()
        if len(selected) < 2:
            raise ValueError("Visual comparison requires at least two MRI acquisitions in the selected interval.")

        method = comparison_method.strip().lower().replace("-", "_")
        if method not in {"pve", "nearest_distance"}:
            raise ValueError("comparison_method must be either 'pve' or 'nearest_distance'.")

        pve_threshold = float(pve_threshold)
        if not (0.0 <= pve_threshold <= 1.0):
            raise ValueError("pve_threshold must be between 0.0 and 1.0.")

        distance_threshold_mm = float(distance_threshold_mm)
        if distance_threshold_mm < 0.0:
            raise ValueError("distance_threshold_mm must be greater than or equal to 0.")

        marching_cubes_step_size = int(marching_cubes_step_size)
        if marching_cubes_step_size < 1:
            raise ValueError("marching_cubes_step_size must be at least 1.")

        baseline = selected[0]
        target = self._get_target_visual_mri(selected, target_date)
        selected_tissues = _normalize_tissues(tissues)
        rgba = _ComparisonColors.from_hex(
            baseline_color=baseline_color,
            changed_color=changed_color,
        )

        if method == "nearest_distance":
            return self._build_nearest_distance_visual_glb(
                baseline=baseline,
                target=target,
                selected_tissues=selected_tissues,
                distance_threshold_mm=distance_threshold_mm,
                colors=rgba,
                trimesh_module=trimesh,
                numpy_module=np,
                cKDTree_cls=cKDTree,
            )

        return self._build_pve_difference_visual_glb(
            baseline=baseline,
            target=target,
            selected_tissues=selected_tissues,
            pve_threshold=pve_threshold,
            colors=rgba,
            marching_cubes_step_size=marching_cubes_step_size,
            nib_module=nib,
            trimesh_module=trimesh,
            numpy_module=np,
            apply_affine_fn=apply_affine,
            marching_cubes_fn=marching_cubes,
            map_coordinates_fn=map_coordinates,
            resample_from_to_fn=resample_from_to,
            template_path=Path(template_path) if template_path is not None else settings.mni_template_path,
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

    def _build_pve_difference_visual_glb(
        self,
        *,
        baseline: EvolutionMriArtifacts,
        target: EvolutionMriArtifacts,
        selected_tissues: Sequence[str],
        pve_threshold: float,
        colors: _ComparisonColors,
        marching_cubes_step_size: int,
        nib_module: Any,
        trimesh_module: Any,
        numpy_module: Any,
        apply_affine_fn: Any,
        marching_cubes_fn: Any,
        map_coordinates_fn: Any,
        resample_from_to_fn: Any,
        template_path: Path,
    ) -> bytes:
        missing: list[Path] = []
        for mri in (baseline, target):
            missing.extend(mri.missing_pve_paths(tissues=selected_tissues))
            missing.extend(mri.missing_metric_paths())
        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Cannot build PVE visual comparison GLB. Missing files:\n{missing_str}")

        template_img = _load_resampling_template(template_path, nib_module=nib_module)
        template_target = (template_img.shape[:3], template_img.affine)
        baseline_metrics = self._load_metrics(baseline)
        target_metrics = self._load_metrics(target)

        scene = trimesh_module.Scene()
        added_geometry = False

        for tissue in selected_tissues:
            baseline_img, _baseline_original_data = _load_pve_image(
                baseline.pve_paths[tissue],
                nib_module=nib_module,
                numpy_module=numpy_module,
            )
            target_img, _target_original_data = _load_pve_image(
                target.pve_paths[tissue],
                nib_module=nib_module,
                numpy_module=numpy_module,
            )
            baseline_data = _resample_pve_data_to_template(
                baseline_img,
                target=template_target,
                resample_from_to_fn=resample_from_to_fn,
                numpy_module=numpy_module,
            )
            target_data = _resample_pve_data_to_template(
                target_img,
                target=template_target,
                resample_from_to_fn=resample_from_to_fn,
                numpy_module=numpy_module,
            )
            diff_data = numpy_module.abs(target_data - baseline_data)
            baseline_volume = float(baseline_metrics.volumes[tissue])
            target_volume = float(target_metrics.volumes[tissue])
            use_target_reference = target_volume > baseline_volume
            reference_label = "target" if use_target_reference else "baseline"
            reference_date = target.acquisition_date if use_target_reference else baseline.acquisition_date
            reference_data = target_data if use_target_reference else baseline_data

            reference_mesh = _pve_data_to_mesh(
                data=reference_data,
                affine=template_img.affine,
                level=0.5,
                step_size=marching_cubes_step_size,
                tissue_name=f"{reference_label} {tissue}",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
                apply_affine_fn=apply_affine_fn,
                marching_cubes_fn=marching_cubes_fn,
            )
            vertex_diff = _sample_volume_at_world_vertices(
                diff_data,
                affine=template_img.affine,
                vertices=reference_mesh.vertices,
                numpy_module=numpy_module,
                map_coordinates_fn=map_coordinates_fn,
            )
            changed_mask = vertex_diff >= pve_threshold
            unchanged_mesh, changed_mesh = _split_mesh_by_vertex_mask(
                reference_mesh,
                changed_vertex_mask=changed_mask,
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
            )
            geometries: list[Any] = []
            if unchanged_mesh is not None:
                geometries.append(unchanged_mesh)
            if changed_mesh is not None:
                geometries.append(changed_mesh)
            if not geometries:
                continue

            origin = _combined_geometry_center(geometries, numpy_module=numpy_module)
            for geometry in geometries:
                _apply_shared_view_transform(geometry, origin=origin, trimesh_module=trimesh_module, numpy_module=numpy_module)

            if unchanged_mesh is not None:
                _apply_rgba(unchanged_mesh, colors.baseline, trimesh_module=trimesh_module, numpy_module=numpy_module)
                scene.add_geometry(
                    unchanged_mesh,
                    node_name=f"unchanged_{reference_label}_{reference_date}_{tissue}_pve_mesh",
                    geom_name=f"unchanged_{reference_label}_{reference_date}_{tissue}_pve_mesh",
                )
                added_geometry = True
            if changed_mesh is not None:
                _apply_rgba(changed_mesh, colors.changed, trimesh_module=trimesh_module, numpy_module=numpy_module)
                scene.add_geometry(
                    changed_mesh,
                    node_name=f"changed_{reference_label}_{reference_date}_{tissue}_pve_mesh",
                    geom_name=f"changed_{reference_label}_{reference_date}_{tissue}_pve_mesh",
                )
                added_geometry = True

        if not added_geometry:
            raise ValueError("No PVE comparison mesh could be built.")
        return _export_scene_to_glb_bytes(scene)

    def _build_nearest_distance_visual_glb(
        self,
        *,
        baseline: EvolutionMriArtifacts,
        target: EvolutionMriArtifacts,
        selected_tissues: Sequence[str],
        distance_threshold_mm: float,
        colors: _ComparisonColors,
        trimesh_module: Any,
        numpy_module: Any,
        cKDTree_cls: Any,
    ) -> bytes:
        missing: list[Path] = []
        for mri in (baseline, target):
            missing.extend(mri.missing_visual_paths(tissues=selected_tissues, include_meshes=True, include_wireframes=False))
            missing.extend(mri.missing_metric_paths())
        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(f"Cannot build nearest-distance comparison GLB. Missing files:\n{missing_str}")

        baseline_metrics = self._load_metrics(baseline)
        target_metrics = self._load_metrics(target)
        scene = trimesh_module.Scene()
        added_geometry = False

        for tissue in selected_tissues:
            baseline_mesh = _load_first_trimesh(baseline.mesh_paths[tissue], trimesh_module=trimesh_module)
            target_mesh = _load_first_trimesh(target.mesh_paths[tissue], trimesh_module=trimesh_module)
            baseline_volume = float(baseline_metrics.volumes[tissue])
            target_volume = float(target_metrics.volumes[tissue])
            use_target_reference = target_volume > baseline_volume
            reference_label = "target" if use_target_reference else "baseline"
            reference_date = target.acquisition_date if use_target_reference else baseline.acquisition_date
            reference_mesh = target_mesh.copy() if use_target_reference else baseline_mesh.copy()
            comparison_vertices = numpy_module.asarray(
                baseline_mesh.vertices if use_target_reference else target_mesh.vertices,
                dtype=float,
            )
            if len(reference_mesh.vertices) == 0 or len(comparison_vertices) == 0:
                raise ValueError(f"Mesh comparison for {tissue} contains no vertices.")

            distances, _indices = cKDTree_cls(comparison_vertices).query(
                numpy_module.asarray(reference_mesh.vertices, dtype=float),
                k=1,
                workers=-1,
            )
            changed_mask = distances > distance_threshold_mm
            unchanged_mesh, changed_mesh = _split_mesh_by_vertex_mask(
                reference_mesh,
                changed_vertex_mask=changed_mask,
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
            )
            geometries: list[Any] = []
            if unchanged_mesh is not None:
                geometries.append(unchanged_mesh)
            if changed_mesh is not None:
                geometries.append(changed_mesh)
            if not geometries:
                continue

            origin = _combined_geometry_center(geometries, numpy_module=numpy_module)
            for geometry in geometries:
                _apply_shared_view_transform(geometry, origin=origin, trimesh_module=trimesh_module, numpy_module=numpy_module)

            if unchanged_mesh is not None:
                _apply_rgba(unchanged_mesh, colors.baseline, trimesh_module=trimesh_module, numpy_module=numpy_module)
                scene.add_geometry(
                    unchanged_mesh,
                    node_name=f"unchanged_{reference_label}_{reference_date}_{tissue}_nearest_mesh",
                    geom_name=f"unchanged_{reference_label}_{reference_date}_{tissue}_nearest_mesh",
                )
                added_geometry = True
            if changed_mesh is not None:
                _apply_rgba(changed_mesh, colors.changed, trimesh_module=trimesh_module, numpy_module=numpy_module)
                scene.add_geometry(
                    changed_mesh,
                    node_name=f"changed_{reference_label}_{reference_date}_{tissue}_nearest_mesh",
                    geom_name=f"changed_{reference_label}_{reference_date}_{tissue}_nearest_mesh",
                )
                added_geometry = True

        if not added_geometry:
            raise ValueError("No nearest-distance comparison mesh could be built.")
        return _export_scene_to_glb_bytes(scene)

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


def _export_scene_to_glb_bytes(scene: Any) -> bytes:
    exported = scene.export(file_type="glb")
    if isinstance(exported, bytes):
        return exported
    if isinstance(exported, bytearray):
        return bytes(exported)
    if isinstance(exported, str):
        return exported.encode("utf-8")

    raise TypeError(f"Unexpected GLB export type: {type(exported)!r}")


def _iter_loaded_geometries(loaded: Any) -> Iterable[Any]:
    if hasattr(loaded, "geometry") and isinstance(getattr(loaded, "geometry"), Mapping):
        yield from loaded.geometry.values()
        return

    yield loaded


def _load_first_trimesh(
    path: Path,
    *,
    trimesh_module: Any,
) -> Any:
    loaded = trimesh_module.load(str(path), force="scene")

    for geometry in _iter_loaded_geometries(loaded):
        if isinstance(geometry, trimesh_module.Trimesh) and len(geometry.vertices) > 0:
            return geometry.copy()

    raise ValueError(f"No mesh geometry found inside GLB file: {path}")

def _load_pve_image(
    path: Path,
    *,
    nib_module: Any,
    numpy_module: Any,
) -> tuple[Any, Any]:
    img = nib_module.load(str(path))
    data = numpy_module.asarray(img.get_fdata(), dtype=numpy_module.float32)
    if data.ndim != 3:
        raise ValueError(f"Expected 3D PVE image at {path}, got ndim={data.ndim}.")
    data = numpy_module.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    data = numpy_module.clip(data, 0.0, 1.0)
    return img, data


def _load_resampling_template(
    template_path: Path,
    *,
    nib_module: Any,
) -> Any:
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(
            f"Cannot resample PVE maps because the MNI template does not exist: {template_path}"
        )

    template_img = nib_module.load(str(template_path))
    if len(template_img.shape) < 3:
        raise ValueError(
            f"Expected a 3D MNI template at {template_path}, got shape={template_img.shape}."
        )
    return template_img


def _resample_pve_data_to_template(
    img: Any,
    *,
    target: tuple[tuple[int, int, int], Any],
    resample_from_to_fn: Any,
    numpy_module: Any,
) -> Any:
    """Resample a PVE image to the common template grid.

    FAST PVE maps are probabilities in [0, 1], so linear interpolation is used
    during resampling. Values are clipped back to [0, 1] after interpolation.
    """
    resampled = resample_from_to_fn(
        img,
        target,
        order=1,
        mode="constant",
        cval=0.0,
    )
    data = numpy_module.asarray(resampled.get_fdata(), dtype=numpy_module.float32)
    if data.ndim != 3:
        raise ValueError(f"Expected 3D resampled PVE image, got ndim={data.ndim}.")
    data = numpy_module.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
    return numpy_module.clip(data, 0.0, 1.0)


def _sample_volume_at_world_vertices(
    volume: Any,
    *,
    affine: Any,
    vertices: Any,
    numpy_module: Any,
    map_coordinates_fn: Any,
) -> Any:
    """Sample a 3D scalar volume at mesh vertices expressed in world coordinates."""
    inverse_affine = numpy_module.linalg.inv(numpy_module.asarray(affine, dtype=float))
    vertices_h = numpy_module.c_[numpy_module.asarray(vertices, dtype=float), numpy_module.ones(len(vertices))]
    voxel_coords = (inverse_affine @ vertices_h.T).T[:, :3]
    # scipy.ndimage.map_coordinates expects axis-first coordinates: zyx? The
    # volume is indexed as [i, j, k], and affine was applied to marching-cubes
    # (i, j, k) coordinates, so pass i/j/k rows in that order.
    return map_coordinates_fn(
        volume,
        voxel_coords.T,
        order=1,
        mode="constant",
        cval=0.0,
    )

def _split_mesh_by_vertex_mask(
    mesh: Any,
    *,
    changed_vertex_mask: Any,
    trimesh_module: Any,
    numpy_module: Any,
) -> tuple[Any | None, Any | None]:
    faces = numpy_module.asarray(mesh.faces, dtype=int)
    if len(faces) == 0:
        return None, None

    mask = numpy_module.asarray(changed_vertex_mask, dtype=bool)
    if mask.shape[0] != len(mesh.vertices):
        raise ValueError("Changed mask length does not match mesh vertex count.")

    changed_face_mask = numpy_module.any(mask[faces], axis=1)
    unchanged_face_mask = ~changed_face_mask
    unchanged_mesh = None
    changed_mesh = None

    if numpy_module.any(unchanged_face_mask):
        unchanged_mesh = mesh.submesh([numpy_module.where(unchanged_face_mask)[0]], append=True, repair=False)
    if numpy_module.any(changed_face_mask):
        changed_mesh = mesh.submesh([numpy_module.where(changed_face_mask)[0]], append=True, repair=False)

    return unchanged_mesh, changed_mesh

def _pve_data_to_mesh(
    *,
    data: Any,
    affine: Any,
    level: float,
    step_size: int,
    tissue_name: str,
    trimesh_module: Any,
    numpy_module: Any,
    apply_affine_fn: Any,
    marching_cubes_fn: Any,
) -> Any:
    data_min = float(data.min())
    data_max = float(data.max())
    if not (data_min < level < data_max):
        raise ValueError(
            f"{tissue_name} PVE image cannot be meshed at level {level}. "
            f"Data range is [{data_min}, {data_max}]."
        )

    verts_voxel, faces, _normals, _values = marching_cubes_fn(data, level=level, step_size=step_size)
    verts_world = apply_affine_fn(affine, verts_voxel)
    return trimesh_module.Trimesh(vertices=verts_world, faces=faces, process=False)


def _geometry_vertices(geometry: Any, *, numpy_module: Any) -> Any:
    vertices = getattr(geometry, "vertices", None)
    if vertices is None or len(vertices) == 0:
        return numpy_module.empty((0, 3), dtype=float)
    return numpy_module.asarray(vertices, dtype=float)


def _combined_geometry_center(geometries: Sequence[Any], *, numpy_module: Any) -> Any:
    chunks = [vertices for vertices in (_geometry_vertices(geometry, numpy_module=numpy_module) for geometry in geometries) if len(vertices) > 0]
    if not chunks:
        return numpy_module.zeros(3, dtype=float)
    all_vertices = numpy_module.vstack(chunks)
    return (all_vertices.min(axis=0) + all_vertices.max(axis=0)) / 2.0


def _apply_shared_view_transform(
    geometry: Any,
    *,
    origin: Any,
    trimesh_module: Any,
    numpy_module: Any,
) -> None:
    transform = trimesh_module.transformations.rotation_matrix(
        angle=numpy_module.deg2rad(-90.0),
        direction=[1, 0, 0],
        point=origin,
    )
    geometry.apply_transform(transform)


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


def _hex_to_rgba(color: str, *, default_alpha: int) -> tuple[int, int, int, int]:
    value = str(color or "").strip()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) == 6:
        value = value + f"{max(0, min(255, int(default_alpha))):02x}"
    if len(value) != 8:
        raise ValueError(f"Invalid color '{color}'. Expected #RRGGBB or #RRGGBBAA.")
    try:
        return tuple(int(value[i:i + 2], 16) for i in range(0, 8, 2))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"Invalid color '{color}'. Expected hexadecimal components.") from exc


def _apply_rgba(
    geometry: Any,
    rgba: tuple[int, int, int, int],
    *,
    trimesh_module: Any,
    numpy_module: Any,
) -> None:
    if isinstance(geometry, trimesh_module.Trimesh):
        material = trimesh_module.visual.material.PBRMaterial(
            baseColorFactor=[component / 255.0 for component in rgba],
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
