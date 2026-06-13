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
        from scipy.ndimage import map_coordinates
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
        template_path=Path(template_path) if template_path is not None else settings.mni_template_path,
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
    template_path: Path,
) -> bytes:
    _require_visual_inputs(
        (baseline, target),
        selected_tissues=selected_tissues,
        error_prefix="Cannot build PVE visual comparison GLB",
        include_pves=True,
    )

    template_img = _load_resampling_template(template_path, nib_module=nib_module)
    template_target = (template_img.shape[:3], template_img.affine)
    baseline_metrics = _load_metrics(baseline)
    target_metrics = _load_metrics(target)

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
        reference_label, reference_date, use_target_reference = _reference_for_volume_change(
            baseline_volume=float(baseline_metrics.volumes[tissue]),
            target_volume=float(target_metrics.volumes[tissue]),
            baseline_date=baseline.acquisition_date,
            target_date=target.acquisition_date,
        )
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
) -> bytes:
    _require_visual_inputs(
        (baseline, target),
        selected_tissues=selected_tissues,
        error_prefix="Cannot build nearest-distance comparison GLB",
        include_meshes=True,
    )

    baseline_metrics = _load_metrics(baseline)
    target_metrics = _load_metrics(target)
    scene = trimesh_module.Scene()
    added_geometry = False

    for tissue in selected_tissues:
        baseline_mesh = _load_first_trimesh(baseline.mesh_paths[tissue], trimesh_module=trimesh_module)
        target_mesh = _load_first_trimesh(target.mesh_paths[tissue], trimesh_module=trimesh_module)
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
        ("unchanged", unchanged_mesh, colors.baseline),
        ("changed", changed_mesh, colors.changed),
    ):
        if mesh is None:
            continue
        geometry_name = f"{change_label}_{reference_label}_{reference_date}_{tissue}_{method_suffix}_mesh"
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
    "_require_visual_inputs",
    "_reference_for_volume_change",
    "_add_comparison_layers",
    "_export_scene_to_glb_bytes",
    "_iter_loaded_geometries",
    "_load_first_trimesh",
    "_load_pve_image",
    "_load_resampling_template",
    "_resample_pve_data_to_template",
    "_sample_volume_at_world_vertices",
    "_split_mesh_by_vertex_mask",
    "_pve_data_to_mesh",
    "_geometry_vertices",
    "_combined_geometry_center",
    "_apply_shared_view_transform",
    "_hex_to_rgba",
    "_apply_rgba",
]
