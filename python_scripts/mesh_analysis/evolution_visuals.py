from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..project_core.config import settings
from .evolution_metrics import _load_metrics
from .evolution_models import EvolutionMriArtifacts, _normalize_tissues


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


_HEATMAP_UNCHANGED_COLOR: tuple[int, int, int, int] = (255, 214, 10, 210)
_PVE_COMPARISON_SMOOTHING_SIGMA = 0.5
_ICP_ALIGNMENT_MAX_POINTS = 8000
_ICP_ALIGNMENT_MAX_ITERATIONS = 50


def build_visual_comparison_glb(
    *,
    selected: Sequence[EvolutionMriArtifacts],
    target: EvolutionMriArtifacts,
    tissues: Iterable[str] | None = None,
    comparison_method: str = "pve",
    pve_threshold: float = 0.2,
    distance_threshold_mm: float = 1.0,
    baseline_color: str = "#508cff",
    changed_color: str = "#ff2d2d",
    marching_cubes_step_size: int = 1,
    template_path: Path | str | None = None,
    visual_mode: str = "changed_unchanged",
    visual_style: str = "binary",
) -> bytes:
    """
    Return an in-memory GLB comparing baseline and target acquisitions.
    """
    try:
        import nibabel as nib
        import numpy as np
        import trimesh
        from nibabel.affines import apply_affine
        from nibabel.processing import resample_from_to
        from scipy.ndimage import gaussian_filter, map_coordinates
        from scipy.spatial import cKDTree
        from skimage.measure import marching_cubes
    except ImportError as exc:
        raise RuntimeError(
            "Visual comparison requires nibabel, numpy, scipy, trimesh, and scikit-image to be installed."
        ) from exc

    if len(selected) < 2:
        raise ValueError("Visual comparison requires at least two MRI acquisitions in the selected interval.")

    method = comparison_method.strip().lower().replace("-", "_")
    if method not in {"pve", "nearest_distance"}:
        raise ValueError("comparison_method must be either 'pve' or 'nearest_distance'.")

    mode = visual_mode.strip().lower().replace("-", "_")
    if mode in {"comparison", "default"}:
        mode = "changed_unchanged"
    if mode in {"before_after", "changed_region"}:
        mode = "changed_region_before_after"
    if mode not in {"changed_unchanged", "changed_region_before_after"}:
        raise ValueError(
            "visual_mode must be either 'changed_unchanged' or 'changed_region_before_after'."
        )

    style = visual_style.strip().lower().replace("-", "_")
    if style in {"default", "simple"}:
        style = "binary"
    if style in {"heatmap", "statistical", "statistics"}:
        style = "statistical_heatmap"
    if style not in {"binary", "statistical_heatmap"}:
        raise ValueError("visual_style must be either 'binary' or 'statistical_heatmap'.")

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
    selected_tissues = _normalize_tissues(tissues)
    colors = _ComparisonColors.from_hex(
        baseline_color=baseline_color,
        changed_color=changed_color,
    )

    if mode == "changed_region_before_after":
        return _build_changed_region_before_after_glb(
            baseline=baseline,
            target=target,
            selected_tissues=selected_tissues,
            comparison_method=method,
            pve_threshold=pve_threshold,
            distance_threshold_mm=distance_threshold_mm,
            colors=colors,
            marching_cubes_step_size=marching_cubes_step_size,
            nib_module=nib,
            trimesh_module=trimesh,
            numpy_module=np,
            apply_affine_fn=apply_affine,
            marching_cubes_fn=marching_cubes,
            map_coordinates_fn=map_coordinates,
            resample_from_to_fn=resample_from_to,
            gaussian_filter_fn=gaussian_filter,
            cKDTree_cls=cKDTree,
            template_path=Path(template_path) if template_path is not None else settings.mni_template_path,
            visual_style=style,
        )

    if method == "nearest_distance":
        return _build_nearest_distance_visual_glb(
            baseline=baseline,
            target=target,
            selected_tissues=selected_tissues,
            distance_threshold_mm=distance_threshold_mm,
            colors=colors,
            trimesh_module=trimesh,
            numpy_module=np,
            cKDTree_cls=cKDTree,
            visual_style=style,
        )

    return _build_pve_difference_visual_glb(
        baseline=baseline,
        target=target,
        selected_tissues=selected_tissues,
        pve_threshold=pve_threshold,
        colors=colors,
        marching_cubes_step_size=marching_cubes_step_size,
        nib_module=nib,
        trimesh_module=trimesh,
        numpy_module=np,
        apply_affine_fn=apply_affine,
        marching_cubes_fn=marching_cubes,
        map_coordinates_fn=map_coordinates,
        resample_from_to_fn=resample_from_to,
        gaussian_filter_fn=gaussian_filter,
        template_path=Path(template_path) if template_path is not None else settings.mni_template_path,
        visual_style=style,
    )


def _build_pve_difference_visual_glb(
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
    gaussian_filter_fn: Any,
    template_path: Path,
    visual_style: str = "binary",
) -> bytes:
    _require_visual_inputs(
        (baseline, target),
        selected_tissues=selected_tissues,
        error_prefix="Cannot build PVE visual comparison GLB",
        include_pves=True,
    )

    baseline_metrics = _load_metrics(baseline)
    target_metrics = _load_metrics(target)

    scene = trimesh_module.Scene()
    added_geometry = False

    for tissue in selected_tissues:
        baseline_img, baseline_data = _load_pve_image(
            baseline.pve_paths[tissue],
            nib_module=nib_module,
            numpy_module=numpy_module,
        )
        target_img, _target_original_data = _load_pve_image(
            target.pve_paths[tissue],
            nib_module=nib_module,
            numpy_module=numpy_module,
        )
        baseline_target = (baseline_img.shape[:3], baseline_img.affine)
        target_data = _resample_pve_data_to_template(
            target_img,
            target=baseline_target,
            resample_from_to_fn=resample_from_to_fn,
            numpy_module=numpy_module,
        )
        baseline_comparison_data = _smooth_pve_data_for_comparison(
            baseline_data,
            gaussian_filter_fn=gaussian_filter_fn,
            numpy_module=numpy_module,
        )
        target_comparison_data = _smooth_pve_data_for_comparison(
            target_data,
            gaussian_filter_fn=gaussian_filter_fn,
            numpy_module=numpy_module,
        )
        delta_data = target_comparison_data - baseline_comparison_data
        diff_data = numpy_module.abs(delta_data)
        normalized_data = _threshold_relative_signed(
            delta_data,
            threshold=pve_threshold,
            numpy_module=numpy_module,
        )
        pve_sigma = _robust_std_from_changed_values(
            normalized_data,
            numpy_module=numpy_module,
        )
        reference_label, reference_date, use_target_reference = _reference_for_volume_change(
            baseline_volume=float(baseline_metrics.volumes[tissue]),
            target_volume=float(target_metrics.volumes[tissue]),
            baseline_date=baseline.acquisition_date,
            target_date=target.acquisition_date,
        )
        reference_data = target_data if use_target_reference else baseline_data

        reference_mesh = _pve_data_to_mesh(
            data=reference_data,
            affine=baseline_img.affine,
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
            affine=baseline_img.affine,
            vertices=reference_mesh.vertices,
            numpy_module=numpy_module,
            map_coordinates_fn=map_coordinates_fn,
        )
        if visual_style == "statistical_heatmap":
            vertex_normalized = _sample_volume_at_world_vertices(
                normalized_data,
                affine=baseline_img.affine,
                vertices=reference_mesh.vertices,
                numpy_module=numpy_module,
                map_coordinates_fn=map_coordinates_fn,
            )
            changed_mask = numpy_module.abs(vertex_normalized) > 0.0
        else:
            changed_mask = vertex_diff >= pve_threshold
        unchanged_mesh, changed_mesh = _split_mesh_by_vertex_mask(
            reference_mesh,
            changed_vertex_mask=changed_mask,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
        )
        if visual_style == "statistical_heatmap" and changed_mesh is not None:
            changed_vertex_normalized = _sample_volume_at_world_vertices(
                normalized_data,
                affine=baseline_img.affine,
                vertices=changed_mesh.vertices,
                numpy_module=numpy_module,
                map_coordinates_fn=map_coordinates_fn,
            )
            _apply_heatmap_vertex_colors(
                changed_mesh,
                changed_vertex_normalized,
                sigma=pve_sigma,
                color_family="pve_signed",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
            )
            added_geometry = _add_comparison_layers(
                scene,
                unchanged_mesh=unchanged_mesh,
                changed_mesh=changed_mesh,
                colors=colors,
                unchanged_color_override=_HEATMAP_UNCHANGED_COLOR,
                reference_label=reference_label,
                reference_date=reference_date,
                tissue=tissue,
                method_suffix="pve_heatmap",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
                preserve_changed_vertex_colors=True,
            ) or added_geometry
        else:
            added_geometry = _add_comparison_layers(
                scene,
                unchanged_mesh=unchanged_mesh,
                changed_mesh=changed_mesh,
                colors=colors,
                reference_label=reference_label,
                reference_date=reference_date,
                tissue=tissue,
                method_suffix="pve",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
            ) or added_geometry

    if not added_geometry:
        raise ValueError("No PVE comparison mesh could be built.")
    return _export_scene_to_glb_bytes(scene)


def _build_nearest_distance_visual_glb(
    *,
    baseline: EvolutionMriArtifacts,
    target: EvolutionMriArtifacts,
    selected_tissues: Sequence[str],
    distance_threshold_mm: float,
    colors: _ComparisonColors,
    trimesh_module: Any,
    numpy_module: Any,
    cKDTree_cls: Any,
    visual_style: str = "binary",
) -> bytes:
    _require_visual_inputs(
        (baseline, target),
        selected_tissues=selected_tissues,
        error_prefix="Cannot build nearest-distance comparison GLB",
        include_meshes=True,
    )

    baseline_metrics = _load_metrics(baseline)
    target_metrics = _load_metrics(target)
    baseline_meshes = _load_meshes_for_tissues(
        baseline,
        selected_tissues,
        trimesh_module=trimesh_module,
    )
    target_meshes = _load_meshes_for_tissues(
        target,
        selected_tissues,
        trimesh_module=trimesh_module,
    )
    _align_target_meshes_to_baseline(
        baseline_meshes=baseline_meshes,
        target_meshes=target_meshes,
        trimesh_module=trimesh_module,
        numpy_module=numpy_module,
    )

    scene = trimesh_module.Scene()
    added_geometry = False

    for tissue in selected_tissues:
        baseline_mesh = baseline_meshes[tissue]
        target_mesh = target_meshes[tissue]
        reference_label, reference_date, use_target_reference = _reference_for_volume_change(
            baseline_volume=float(baseline_metrics.volumes[tissue]),
            target_volume=float(target_metrics.volumes[tissue]),
            baseline_date=baseline.acquisition_date,
            target_date=target.acquisition_date,
        )
        reference_mesh = target_mesh.copy() if use_target_reference else baseline_mesh.copy()
        comparison_vertices = numpy_module.asarray(
            baseline_mesh.vertices if use_target_reference else target_mesh.vertices,
            dtype=float,
        )
        if len(reference_mesh.vertices) == 0 or len(comparison_vertices) == 0:
            raise ValueError(f"Mesh comparison for {tissue} contains no vertices.")

        comparison_tree = cKDTree_cls(comparison_vertices)
        distances, _indices = comparison_tree.query(
            numpy_module.asarray(reference_mesh.vertices, dtype=float),
            k=1,
            workers=-1,
        )
        normalized_distances = _threshold_relative_unsigned(
            distances,
            threshold=distance_threshold_mm,
            numpy_module=numpy_module,
        )
        distance_sigma = _robust_std_from_changed_values(
            normalized_distances,
            numpy_module=numpy_module,
        )
        changed_mask = normalized_distances > 0.0 if visual_style == "statistical_heatmap" else distances > distance_threshold_mm
        unchanged_mesh, changed_mesh = _split_mesh_by_vertex_mask(
            reference_mesh,
            changed_vertex_mask=changed_mask,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
        )
        if visual_style == "statistical_heatmap" and changed_mesh is not None:
            changed_distances, _changed_indices = comparison_tree.query(
                numpy_module.asarray(changed_mesh.vertices, dtype=float),
                k=1,
                workers=-1,
            )
            changed_normalized = _threshold_relative_unsigned(
                changed_distances,
                threshold=distance_threshold_mm,
                numpy_module=numpy_module,
            )
            _apply_heatmap_vertex_colors(
                changed_mesh,
                changed_normalized,
                sigma=distance_sigma,
                color_family="distance",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
            )
            added_geometry = _add_comparison_layers(
                scene,
                unchanged_mesh=unchanged_mesh,
                changed_mesh=changed_mesh,
                colors=colors,
                unchanged_color_override=_HEATMAP_UNCHANGED_COLOR,
                reference_label=reference_label,
                reference_date=reference_date,
                tissue=tissue,
                method_suffix="nearest_heatmap",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
                extra_x_degrees=85.0,
                preserve_changed_vertex_colors=True,
            ) or added_geometry
        else:
            added_geometry = _add_comparison_layers(
                scene,
                unchanged_mesh=unchanged_mesh,
                changed_mesh=changed_mesh,
                colors=colors,
                reference_label=reference_label,
                reference_date=reference_date,
                tissue=tissue,
                method_suffix="nearest",
                trimesh_module=trimesh_module,
                numpy_module=numpy_module,
                extra_x_degrees=85.0,
            ) or added_geometry

    if not added_geometry:
        raise ValueError("No nearest-distance comparison mesh could be built.")
    return _export_scene_to_glb_bytes(scene)


def _build_changed_region_before_after_glb(
    *,
    baseline: EvolutionMriArtifacts,
    target: EvolutionMriArtifacts,
    selected_tissues: Sequence[str],
    comparison_method: str,
    pve_threshold: float,
    distance_threshold_mm: float,
    colors: _ComparisonColors,
    marching_cubes_step_size: int,
    nib_module: Any,
    trimesh_module: Any,
    numpy_module: Any,
    apply_affine_fn: Any,
    marching_cubes_fn: Any,
    map_coordinates_fn: Any,
    resample_from_to_fn: Any,
    gaussian_filter_fn: Any,
    cKDTree_cls: Any,
    template_path: Path,
    visual_style: str = "binary",
) -> bytes:
    if comparison_method == "nearest_distance":
        return _build_nearest_distance_changed_region_before_after_glb(
            baseline=baseline,
            target=target,
            selected_tissues=selected_tissues,
            distance_threshold_mm=distance_threshold_mm,
            colors=colors,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
            cKDTree_cls=cKDTree_cls,
            visual_style=visual_style,
        )

    return _build_pve_changed_region_before_after_glb(
        baseline=baseline,
        target=target,
        selected_tissues=selected_tissues,
        pve_threshold=pve_threshold,
        colors=colors,
        marching_cubes_step_size=marching_cubes_step_size,
        nib_module=nib_module,
        trimesh_module=trimesh_module,
        numpy_module=numpy_module,
        apply_affine_fn=apply_affine_fn,
        marching_cubes_fn=marching_cubes_fn,
        map_coordinates_fn=map_coordinates_fn,
        resample_from_to_fn=resample_from_to_fn,
        gaussian_filter_fn=gaussian_filter_fn,
        template_path=template_path,
        visual_style=visual_style,
    )


def _build_pve_changed_region_before_after_glb(
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
    gaussian_filter_fn: Any,
    template_path: Path,
    visual_style: str = "binary",
) -> bytes:
    _require_visual_inputs(
        (baseline, target),
        selected_tissues=selected_tissues,
        error_prefix="Cannot build changed-region before/after GLB",
        include_pves=True,
    )

    scene = trimesh_module.Scene()
    added_geometry = False

    for tissue in selected_tissues:
        baseline_img, baseline_data = _load_pve_image(
            baseline.pve_paths[tissue],
            nib_module=nib_module,
            numpy_module=numpy_module,
        )
        target_img, _target_original_data = _load_pve_image(
            target.pve_paths[tissue],
            nib_module=nib_module,
            numpy_module=numpy_module,
        )
        baseline_target = (baseline_img.shape[:3], baseline_img.affine)
        target_data = _resample_pve_data_to_template(
            target_img,
            target=baseline_target,
            resample_from_to_fn=resample_from_to_fn,
            numpy_module=numpy_module,
        )
        baseline_comparison_data = _smooth_pve_data_for_comparison(
            baseline_data,
            gaussian_filter_fn=gaussian_filter_fn,
            numpy_module=numpy_module,
        )
        target_comparison_data = _smooth_pve_data_for_comparison(
            target_data,
            gaussian_filter_fn=gaussian_filter_fn,
            numpy_module=numpy_module,
        )
        delta_data = target_comparison_data - baseline_comparison_data
        normalized_data = _threshold_relative_signed(
            delta_data,
            threshold=pve_threshold,
            numpy_module=numpy_module,
        )
        changed_volume_mask = numpy_module.abs(normalized_data) > 0.0 if visual_style == "statistical_heatmap" else numpy_module.abs(delta_data) >= pve_threshold
        if not bool(numpy_module.any(changed_volume_mask)):
            continue

        baseline_changed_data = numpy_module.where(changed_volume_mask, baseline_data, 0.0)
        target_changed_data = numpy_module.where(changed_volume_mask, target_data, 0.0)

        before_mesh = _pve_data_to_mesh_or_none(
            data=baseline_changed_data,
            affine=baseline_img.affine,
            level=0.5,
            step_size=marching_cubes_step_size,
            tissue_name=f"before {tissue} changed region",
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
            apply_affine_fn=apply_affine_fn,
            marching_cubes_fn=marching_cubes_fn,
        )
        after_mesh = _pve_data_to_mesh_or_none(
            data=target_changed_data,
            affine=baseline_img.affine,
            level=0.5,
            step_size=marching_cubes_step_size,
            tissue_name=f"after {tissue} changed region",
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
            apply_affine_fn=apply_affine_fn,
            marching_cubes_fn=marching_cubes_fn,
        )
        added_geometry = _add_before_after_layers(
            scene,
            before_mesh=before_mesh,
            after_mesh=after_mesh,
            colors=colors,
            baseline_date=baseline.acquisition_date,
            target_date=target.acquisition_date,
            tissue=tissue,
            method_suffix="pve",
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
        ) or added_geometry

    if not added_geometry:
        raise ValueError("No PVE changed-region before/after mesh could be built.")
    return _export_scene_to_glb_bytes(scene)


def _build_nearest_distance_changed_region_before_after_glb(
    *,
    baseline: EvolutionMriArtifacts,
    target: EvolutionMriArtifacts,
    selected_tissues: Sequence[str],
    distance_threshold_mm: float,
    colors: _ComparisonColors,
    trimesh_module: Any,
    numpy_module: Any,
    cKDTree_cls: Any,
    visual_style: str = "binary",
) -> bytes:
    _require_visual_inputs(
        (baseline, target),
        selected_tissues=selected_tissues,
        error_prefix="Cannot build nearest-distance changed-region before/after GLB",
        include_meshes=True,
    )

    baseline_meshes = _load_meshes_for_tissues(
        baseline,
        selected_tissues,
        trimesh_module=trimesh_module,
    )
    target_meshes = _load_meshes_for_tissues(
        target,
        selected_tissues,
        trimesh_module=trimesh_module,
    )
    _align_target_meshes_to_baseline(
        baseline_meshes=baseline_meshes,
        target_meshes=target_meshes,
        trimesh_module=trimesh_module,
        numpy_module=numpy_module,
    )

    scene = trimesh_module.Scene()
    added_geometry = False

    for tissue in selected_tissues:
        baseline_mesh = baseline_meshes[tissue]
        target_mesh = target_meshes[tissue]
        baseline_vertices = numpy_module.asarray(baseline_mesh.vertices, dtype=float)
        target_vertices = numpy_module.asarray(target_mesh.vertices, dtype=float)
        if len(baseline_vertices) == 0 or len(target_vertices) == 0:
            continue

        target_tree = cKDTree_cls(target_vertices)
        baseline_tree = cKDTree_cls(baseline_vertices)
        baseline_distances, _baseline_indices = target_tree.query(
            baseline_vertices,
            k=1,
            workers=-1,
        )
        target_distances, _target_indices = baseline_tree.query(
            target_vertices,
            k=1,
            workers=-1,
        )
        baseline_normalized = _threshold_relative_unsigned(
            baseline_distances,
            threshold=distance_threshold_mm,
            numpy_module=numpy_module,
        )
        target_normalized = _threshold_relative_unsigned(
            target_distances,
            threshold=distance_threshold_mm,
            numpy_module=numpy_module,
        )
        _baseline_unchanged, before_mesh = _split_mesh_by_vertex_mask(
            baseline_mesh,
            changed_vertex_mask=baseline_normalized > 0.0 if visual_style == "statistical_heatmap" else baseline_distances > distance_threshold_mm,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
        )
        _target_unchanged, after_mesh = _split_mesh_by_vertex_mask(
            target_mesh,
            changed_vertex_mask=target_normalized > 0.0 if visual_style == "statistical_heatmap" else target_distances > distance_threshold_mm,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
        )
        added_geometry = _add_before_after_layers(
            scene,
            before_mesh=before_mesh,
            after_mesh=after_mesh,
            colors=colors,
            baseline_date=baseline.acquisition_date,
            target_date=target.acquisition_date,
            tissue=tissue,
            method_suffix="nearest",
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
            extra_x_degrees=85.0,
        ) or added_geometry

    if not added_geometry:
        raise ValueError("No nearest-distance changed-region before/after mesh could be built.")
    return _export_scene_to_glb_bytes(scene)


def _load_meshes_for_tissues(
    artifact: EvolutionMriArtifacts,
    selected_tissues: Sequence[str],
    *,
    trimesh_module: Any,
) -> dict[str, Any]:
    return {
        tissue: _load_first_trimesh(artifact.mesh_paths[tissue], trimesh_module=trimesh_module)
        for tissue in selected_tissues
    }


def _align_target_meshes_to_baseline(
    *,
    baseline_meshes: Mapping[str, Any],
    target_meshes: Mapping[str, Any],
    trimesh_module: Any,
    numpy_module: Any,
) -> Any:
    """Rigidly align target meshes to the baseline meshes in-place using ICP."""
    transform = _estimate_rigid_icp_transform(
        fixed_meshes=baseline_meshes,
        moving_meshes=target_meshes,
        trimesh_module=trimesh_module,
        numpy_module=numpy_module,
    )
    for mesh in target_meshes.values():
        if len(_geometry_vertices(mesh, numpy_module=numpy_module)) > 0:
            mesh.apply_transform(transform)
    return transform


def _estimate_rigid_icp_transform(
    *,
    fixed_meshes: Mapping[str, Any],
    moving_meshes: Mapping[str, Any],
    trimesh_module: Any,
    numpy_module: Any,
) -> Any:
    """Estimate a rigid transform that maps the moving/target meshes to the fixed/baseline meshes."""
    fixed_points = _downsample_alignment_points(
        _stack_mesh_vertices(fixed_meshes.values(), numpy_module=numpy_module),
        numpy_module=numpy_module,
    )
    moving_points = _downsample_alignment_points(
        _stack_mesh_vertices(moving_meshes.values(), numpy_module=numpy_module),
        numpy_module=numpy_module,
    )
    initial = _centroid_translation_transform(
        moving_points=moving_points,
        fixed_points=fixed_points,
        numpy_module=numpy_module,
    )

    if len(fixed_points) < 3 or len(moving_points) < 3:
        return initial

    registration = getattr(trimesh_module, "registration", None)
    icp_fn = getattr(registration, "icp", None)
    if icp_fn is None:
        return initial

    try:
        matrix, _transformed, _cost = icp_fn(
            moving_points,
            fixed_points,
            initial=initial,
            threshold=1e-5,
            max_iterations=_ICP_ALIGNMENT_MAX_ITERATIONS,
            scale=False,
            reflection=False,
        )
    except Exception:
        return initial

    matrix = numpy_module.asarray(matrix, dtype=float)
    if matrix.shape != (4, 4) or not bool(numpy_module.all(numpy_module.isfinite(matrix))):
        return initial
    return matrix


def _stack_mesh_vertices(meshes: Iterable[Any], *, numpy_module: Any) -> Any:
    chunks = []
    for mesh in meshes:
        vertices = _geometry_vertices(mesh, numpy_module=numpy_module)
        if len(vertices) > 0:
            chunks.append(vertices)
    if not chunks:
        return numpy_module.empty((0, 3), dtype=float)
    return numpy_module.vstack(chunks)


def _downsample_alignment_points(points: Any, *, numpy_module: Any) -> Any:
    points_array = numpy_module.asarray(points, dtype=float)
    if len(points_array) <= _ICP_ALIGNMENT_MAX_POINTS:
        return points_array
    indices = numpy_module.linspace(0, len(points_array) - 1, _ICP_ALIGNMENT_MAX_POINTS, dtype=int)
    return points_array[indices]


def _centroid_translation_transform(*, moving_points: Any, fixed_points: Any, numpy_module: Any) -> Any:
    transform = numpy_module.eye(4, dtype=float)
    if len(moving_points) == 0 or len(fixed_points) == 0:
        return transform
    transform[:3, 3] = numpy_module.mean(fixed_points, axis=0) - numpy_module.mean(moving_points, axis=0)
    return transform


def _smooth_pve_data_for_comparison(data: Any, *, gaussian_filter_fn: Any, numpy_module: Any) -> Any:
    smoothed = gaussian_filter_fn(
        numpy_module.asarray(data, dtype=numpy_module.float32),
        sigma=_PVE_COMPARISON_SMOOTHING_SIGMA,
        mode="nearest",
    )
    return numpy_module.clip(numpy_module.asarray(smoothed, dtype=numpy_module.float32), 0.0, 1.0)

def _pve_data_to_mesh_or_none(
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
) -> Any | None:
    data_min = float(data.min())
    data_max = float(data.max())
    if not (data_min < level < data_max):
        return None

    return _pve_data_to_mesh(
        data=data,
        affine=affine,
        level=level,
        step_size=step_size,
        tissue_name=tissue_name,
        trimesh_module=trimesh_module,
        numpy_module=numpy_module,
        apply_affine_fn=apply_affine_fn,
        marching_cubes_fn=marching_cubes_fn,
    )


def _threshold_relative_signed(values: Any, *, threshold: float, numpy_module: Any) -> Any:
    """Keep only signed change that exceeds the user threshold."""
    values_array = numpy_module.asarray(values, dtype=numpy_module.float32)
    magnitude = numpy_module.maximum(numpy_module.abs(values_array) - float(threshold), 0.0)
    return numpy_module.sign(values_array) * magnitude


def _threshold_relative_unsigned(values: Any, *, threshold: float, numpy_module: Any) -> Any:
    """Keep only unsigned change that exceeds the user threshold."""
    values_array = numpy_module.asarray(values, dtype=numpy_module.float32)
    return numpy_module.maximum(values_array - float(threshold), 0.0)


def _robust_std_from_changed_values(values: Any, *, numpy_module: Any) -> float:
    """Return std on changed magnitudes after a first-pass 3σ outlier rejection."""
    values_array = numpy_module.asarray(values, dtype=numpy_module.float32)
    changed_magnitudes = numpy_module.abs(values_array[values_array != 0])
    if changed_magnitudes.size == 0:
        return 1.0

    first_sigma = float(numpy_module.std(changed_magnitudes))
    if first_sigma <= 1e-12:
        fallback = float(numpy_module.max(changed_magnitudes))
        return fallback if fallback > 1e-12 else 1.0

    first_z = changed_magnitudes / first_sigma
    kept = changed_magnitudes[first_z <= 3.0]
    if kept.size == 0:
        kept = changed_magnitudes

    refined_sigma = float(numpy_module.std(kept))
    if refined_sigma <= 1e-12:
        fallback = float(numpy_module.max(kept))
        return fallback if fallback > 1e-12 else first_sigma
    return refined_sigma


def _heatmap_intensity(values: Any, *, sigma: float, numpy_module: Any) -> Any:
    magnitudes = numpy_module.abs(numpy_module.asarray(values, dtype=numpy_module.float32))
    safe_sigma = float(sigma) if float(sigma) > 1e-12 else 1.0
    z_scores = magnitudes / safe_sigma
    t = numpy_module.clip(z_scores / 3.0, 0.0, 1.0)
    return numpy_module.where(z_scores >= 3.0, 1.0, numpy_module.power(t, 1.8))


def _mix_rgb(
    low_rgb: tuple[int, int, int],
    high_rgb: tuple[int, int, int],
    intensity: Any,
    *,
    numpy_module: Any,
) -> Any:
    low = numpy_module.asarray(low_rgb, dtype=numpy_module.float32)
    high = numpy_module.asarray(high_rgb, dtype=numpy_module.float32)
    intensity_column = numpy_module.asarray(intensity, dtype=numpy_module.float32).reshape(-1, 1)
    return low + (high - low) * intensity_column


def _rgba_heatmap_colors(
    values: Any,
    *,
    sigma: float,
    color_family: str,
    numpy_module: Any,
) -> Any:
    values_array = numpy_module.asarray(values, dtype=numpy_module.float32)
    intensity = _heatmap_intensity(values_array, sigma=sigma, numpy_module=numpy_module)

    if color_family == "pve_signed":
        positive_rgb = _mix_rgb((255, 213, 170), (255, 28, 0), intensity, numpy_module=numpy_module)
        negative_rgb = _mix_rgb((178, 220, 255), (0, 60, 255), intensity, numpy_module=numpy_module)
        rgb = numpy_module.where((values_array >= 0).reshape(-1, 1), positive_rgb, negative_rgb)
    else:
        rgb = _mix_rgb((215, 206, 255), (103, 36, 255), intensity, numpy_module=numpy_module)

    alpha = numpy_module.full((len(values_array), 1), 255.0, dtype=numpy_module.float32)
    rgba = numpy_module.concatenate([rgb, alpha], axis=1)
    return numpy_module.clip(rgba, 0, 255).astype(numpy_module.uint8)


def _apply_heatmap_vertex_colors(
    geometry: Any,
    values: Any,
    *,
    sigma: float,
    color_family: str,
    trimesh_module: Any,
    numpy_module: Any,
) -> None:
    if not isinstance(geometry, trimesh_module.Trimesh):
        return

    rgba = _rgba_heatmap_colors(
        values,
        sigma=sigma,
        color_family=color_family,
        numpy_module=numpy_module,
    )
    if len(rgba) != len(geometry.vertices):
        raise ValueError("Heatmap color count does not match mesh vertex count.")
    geometry.visual = trimesh_module.visual.ColorVisuals(mesh=geometry, vertex_colors=rgba)


def _add_before_after_layers(
    scene: Any,
    *,
    before_mesh: Any | None,
    after_mesh: Any | None,
    colors: _ComparisonColors,
    baseline_date: str,
    target_date: str,
    tissue: str,
    method_suffix: str,
    trimesh_module: Any,
    numpy_module: Any,
    extra_x_degrees: float = 0.0,
    preserve_source_colors: bool = False,
) -> bool:
    geometries = [mesh for mesh in (before_mesh, after_mesh) if mesh is not None]
    if not geometries:
        return False

    origin = _combined_geometry_center(geometries, numpy_module=numpy_module)
    for geometry in geometries:
        _apply_shared_view_transform(
            geometry,
            origin=origin,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
            extra_x_degrees=extra_x_degrees,
        )

    added = False
    for change_label, mesh, date_label, color in (
        ("before", before_mesh, baseline_date, colors.baseline),
        ("after", after_mesh, target_date, colors.changed),
    ):
        if mesh is None:
            continue
        geometry_name = f"{change_label}_{date_label}_{tissue}_{method_suffix}_changed_region_mesh"
        if not preserve_source_colors:
            _apply_rgba(mesh, color, trimesh_module=trimesh_module, numpy_module=numpy_module)
        scene.add_geometry(mesh, node_name=geometry_name, geom_name=geometry_name)
        added = True

    return added


def _require_visual_inputs(
    mris: Iterable[EvolutionMriArtifacts],
    *,
    selected_tissues: Sequence[str],
    error_prefix: str,
    include_meshes: bool = False,
    include_pves: bool = False,
) -> None:
    missing: list[Path] = []
    for mri in mris:
        if include_meshes:
            missing.extend(mri.missing_visual_paths(tissues=selected_tissues, include_meshes=True))
        if include_pves:
            missing.extend(mri.missing_pve_paths(tissues=selected_tissues))
        missing.extend(mri.missing_metric_paths())

    if missing:
        missing_str = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"{error_prefix}. Missing files:\n{missing_str}")


def _reference_for_volume_change(
    *,
    baseline_volume: float,
    target_volume: float,
    baseline_date: str,
    target_date: str,
) -> tuple[str, str, bool]:
    use_target_reference = target_volume > baseline_volume
    if use_target_reference:
        return "target", target_date, True
    return "baseline", baseline_date, False


def _add_comparison_layers(
    scene: Any,
    *,
    unchanged_mesh: Any | None,
    changed_mesh: Any | None,
    colors: _ComparisonColors,
    reference_label: str,
    reference_date: str,
    tissue: str,
    method_suffix: str,
    trimesh_module: Any,
    numpy_module: Any,
    extra_x_degrees: float = 0.0,
    preserve_changed_vertex_colors: bool = False,
    unchanged_color_override: tuple[int, int, int, int] | None = None,
) -> bool:
    geometries = [mesh for mesh in (unchanged_mesh, changed_mesh) if mesh is not None]
    if not geometries:
        return False

    origin = _combined_geometry_center(geometries, numpy_module=numpy_module)
    for geometry in geometries:
        _apply_shared_view_transform(
            geometry,
            origin=origin,
            trimesh_module=trimesh_module,
            numpy_module=numpy_module,
            extra_x_degrees=extra_x_degrees,
        )

    added = False
    for change_label, mesh, color in (
        ("unchanged", unchanged_mesh, unchanged_color_override or colors.baseline),
        ("changed", changed_mesh, colors.changed),
    ):
        if mesh is None:
            continue
        geometry_name = f"{change_label}_{reference_label}_{reference_date}_{tissue}_{method_suffix}_mesh"
        if not (change_label == "changed" and preserve_changed_vertex_colors):
            _apply_rgba(mesh, color, trimesh_module=trimesh_module, numpy_module=numpy_module)
        scene.add_geometry(mesh, node_name=geometry_name, geom_name=geometry_name)
        added = True

    return added


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
    extra_x_degrees: float = 0.0,
) -> None:
    transform = trimesh_module.transformations.rotation_matrix(
        angle=numpy_module.deg2rad(-90.0 + extra_x_degrees),
        direction=[1, 0, 0],
        point=origin,
    )
    geometry.apply_transform(transform)


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

    # Some loaded GLB variants expose an entities/colors collection. If that is
    # unavailable, leaving the geometry untouched is safer than failing the whole
    # visual comparison.
    if hasattr(geometry, "entities") and hasattr(geometry, "colors"):
        color = numpy_module.array(rgba, dtype=numpy_module.uint8)
        geometry.colors = numpy_module.tile(color, (len(geometry.entities), 1))


__all__ = [
    "build_visual_comparison_glb",
    "_ComparisonColors",
    "_build_pve_difference_visual_glb",
    "_build_nearest_distance_visual_glb",
    "_build_changed_region_before_after_glb",
    "_build_pve_changed_region_before_after_glb",
    "_build_nearest_distance_changed_region_before_after_glb",
    "_require_visual_inputs",
    "_reference_for_volume_change",
    "_add_comparison_layers",
    "_add_before_after_layers",
    "_export_scene_to_glb_bytes",
    "_iter_loaded_geometries",
    "_load_first_trimesh",
    "_load_pve_image",
    "_load_resampling_template",
    "_resample_pve_data_to_template",
    "_sample_volume_at_world_vertices",
    "_split_mesh_by_vertex_mask",
    "_pve_data_to_mesh",
    "_pve_data_to_mesh_or_none",
    "_geometry_vertices",
    "_combined_geometry_center",
    "_apply_shared_view_transform",
    "_hex_to_rgba",
    "_apply_rgba",
]
