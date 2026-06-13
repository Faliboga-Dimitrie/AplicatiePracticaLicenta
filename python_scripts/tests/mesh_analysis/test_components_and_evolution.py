from __future__ import annotations

import json
import types

import numpy as np
import pytest
import trimesh

from python_scripts.mesh_analysis.analysis import MeshAnalysisPipeline
from python_scripts.mesh_analysis.evolution_in_time import (
    EvolutionMriArtifacts,
    MriEvolutionInTime,
    _ComparisonColors,
    _append_optional_float,
    _basic_stats,
    _combined_geometry_center,
    _export_scene_to_glb_bytes,
    _hex_to_rgba,
    _iter_loaded_geometries,
    _load_first_trimesh,
    _load_pve_image,
    _load_resampling_template,
    _normalize_tissues,
    _require_float,
    _require_mapping,
    _resample_pve_data_to_template,
    _safe_change_percent,
    _safe_ratio_percent,
    _sample_volume_at_world_vertices,
    _split_mesh_by_vertex_mask,
)
from python_scripts.mesh_analysis.exporters import GlbExportConfig, GlbMeshExporter
from python_scripts.mesh_analysis.mesh_extractors import MarchingCubesConfig, MarchingCubesMeshExtractor
from python_scripts.mesh_analysis.models import MeshAnalysisMeshes, TissueMeshes
from python_scripts.mesh_analysis.surface_estimators import TrimeshSurfaceEstimator
from python_scripts.mesh_analysis.volume_estimators import PveSumVolumeEstimator
from python_scripts.project_core import MeshAnalysisResult, TissueSurfaces, TissueVolumes


class FakeImage:
    def __init__(self, data, affine=None):
        self._data = np.asarray(data, dtype=np.float32)
        self.affine = np.eye(4) if affine is None else np.asarray(affine, dtype=float)
        self.shape = self._data.shape

    def get_fdata(self):
        return self._data


def _touch_metric_json(path, *, volumes, surfaces):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"subject_id": "IXI001", "volumes": volumes, "surfaces": surfaces}), encoding="utf-8")


def _create_evolution_artifact(tmp_path, date, *, volumes=None, surfaces=None):
    root = tmp_path / date
    metrics = root / "metrics.json"
    meshes = {name: root / f"{name}.glb" for name in ("csf", "gm", "wm")}
    pves = {name: root / f"{name}.nii.gz" for name in ("csf", "gm", "wm")}
    _touch_metric_json(
        metrics,
        volumes=volumes or {"csf_mm3": 10, "gm_mm3": 20, "wm_mm3": 30},
        surfaces=surfaces or {"csf_mm2": 1, "gm_mm2": 2, "wm_mm2": 3},
    )
    for path in [*meshes.values(), *pves.values()]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("artifact", encoding="utf-8")
    return EvolutionMriArtifacts(
        subject_id="IXI001",
        acquisition_date=date,
        metrics_json_path=metrics,
        csf_mesh_path=meshes["csf"],
        gm_mesh_path=meshes["gm"],
        wm_mesh_path=meshes["wm"],
        csf_pve_path=pves["csf"],
        gm_pve_path=pves["gm"],
        wm_pve_path=pves["wm"],
    )


def test_pipeline_existing_output_errors_and_overwrite_cleanup(settings, workspace):
    # Arrange
    for path in workspace.fast_pve_paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("pve", encoding="utf-8")
    workspace.mesh_dir.mkdir(parents=True, exist_ok=True)
    workspace.metrics_json_path.write_text("{}", encoding="utf-8")
    partial_settings = type(settings)(**{**settings.__dict__, "overwrite": False, "skip_existing": False})

    # Act / Assert
    with pytest.raises(FileExistsError, match="Partial"):
        MeshAnalysisPipeline(workspace, partial_settings)._handle_existing_outputs()

    overwrite_settings = type(settings)(**{**settings.__dict__, "overwrite": True, "skip_existing": False})
    assert MeshAnalysisPipeline(workspace, overwrite_settings)._handle_existing_outputs() is None
    assert not workspace.metrics_json_path.exists()


def test_pipeline_loads_old_typo_acquisition_date_for_backward_compatibility(settings, workspace):
    # Arrange
    workspace.mesh_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "subject_id": "IXI001",
        "aquisition_date": "2026-01-01",
        "volumes": {"csf": 1, "gm": 2, "wm": 3},
        "surfaces": {"csf": 4, "gm": 5, "wm": 6},
    }
    workspace.metrics_json_path.write_text(json.dumps(payload), encoding="utf-8")

    # Act
    result = MeshAnalysisPipeline(workspace, settings)._load_existing_result()

    # Assert
    assert result.acquisition_date == "2026-01-01"
    assert result.volumes.gm_mm3 == 2


def test_pipeline_write_metrics_json_excludes_local_mesh_paths(settings, workspace):
    # Arrange
    pipeline = MeshAnalysisPipeline(workspace, settings)
    result = MeshAnalysisResult("IXI001", TissueVolumes(1, 2, 3), TissueSurfaces(4, 5, 6), "2026-06-02")

    # Act
    pipeline._write_metrics_json(result)

    # Assert
    payload = json.loads(workspace.metrics_json_path.read_text(encoding="utf-8"))
    assert "mesh_paths" not in payload


def test_volume_estimator_compute_loads_all_tissues(monkeypatch, tmp_path):
    # Arrange
    estimator = PveSumVolumeEstimator()
    paths = {"csf": tmp_path / "csf.nii.gz", "gm": tmp_path / "gm.nii.gz", "wm": tmp_path / "wm.nii.gz"}
    images = {
        str(paths["csf"]): FakeImage(np.ones((1, 1, 1)), affine=np.diag([1, 1, 1, 1])),
        str(paths["gm"]): FakeImage(np.ones((1, 1, 1)) * 2, affine=np.diag([2, 1, 1, 1])),
        str(paths["wm"]): FakeImage(np.ones((1, 1, 1)) * 3, affine=np.diag([3, 1, 1, 1])),
    }
    monkeypatch.setattr("python_scripts.mesh_analysis.volume_estimators.nib.load", lambda path: images[path])

    # Act
    volumes = estimator.compute(paths)

    # Assert
    assert volumes == TissueVolumes(csf_mm3=1.0, gm_mm3=2.0, wm_mm3=3.0)


def test_surface_estimator_computes_area_from_meshes():
    # Arrange
    triangle = trimesh.Trimesh(vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]), faces=np.array([[0, 1, 2]]), process=False)
    meshes = MeshAnalysisMeshes(solid=TissueMeshes(csf=triangle, gm=triangle, wm=triangle))

    # Act
    surfaces = TrimeshSurfaceEstimator().compute(meshes)

    # Assert
    assert surfaces == TissueSurfaces(csf_mm2=0.5, gm_mm2=0.5, wm_mm2=0.5)
    assert meshes.solid.as_dict()["gm"] is triangle


def test_marching_cubes_extracts_mesh_and_rejects_invalid_data():
    # Arrange
    extractor = MarchingCubesMeshExtractor(MarchingCubesConfig(level=0.5, solid_step_size=1))
    data = np.zeros((3, 3, 3), dtype=np.float32)
    data[1, 1, 1] = 1.0

    # Act
    mesh = extractor._pve_image_to_mesh(pve_img=FakeImage(data), tissue_name="GM", step_size=1)

    # Assert
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0

    with pytest.raises(ValueError, match="Expected 3D"):
        extractor._pve_image_to_mesh(pve_img=FakeImage(np.zeros((2, 2))), tissue_name="GM", step_size=1)
    with pytest.raises(ValueError, match="cannot be meshed"):
        extractor._pve_image_to_mesh(pve_img=FakeImage(np.zeros((3, 3, 3))), tissue_name="GM", step_size=1)


def test_marching_cubes_extract_all_loads_each_pve(monkeypatch, tmp_path):
    # Arrange
    extractor = MarchingCubesMeshExtractor()
    data = np.zeros((3, 3, 3), dtype=np.float32)
    data[1, 1, 1] = 1.0
    paths = {name: tmp_path / f"{name}.nii.gz" for name in ("csf", "gm", "wm")}
    monkeypatch.setattr("python_scripts.mesh_analysis.mesh_extractors.nib.load", lambda _path: FakeImage(data))

    # Act
    meshes = extractor.extract_all(paths)

    # Assert
    assert set(meshes.solid.as_dict()) == {"csf", "gm", "wm"}


def test_glb_exporter_writes_each_mesh_and_applies_material(workspace):
    # Arrange
    triangle = trimesh.Trimesh(vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]), faces=np.array([[0, 1, 2]]), process=False)
    meshes = MeshAnalysisMeshes(solid=TissueMeshes(csf=triangle, gm=triangle.copy(), wm=triangle.copy()))
    workspace.mesh_dir.mkdir(parents=True, exist_ok=True)
    exporter = GlbMeshExporter(GlbExportConfig(rotate_x_degrees=None, scale_factor=1.0))

    # Act
    result = exporter.export(meshes, workspace)

    # Assert
    assert result is None
    assert all(path.exists() for path in workspace.mesh_paths.values())


def test_glb_exporter_applies_scale_transform_when_configured():
    # Arrange
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    exporter = GlbMeshExporter(GlbExportConfig(rotate_x_degrees=0, scale_factor=2.0))
    original_extents = mesh.extents.copy()

    # Act
    exporter._apply_view_transform(mesh)

    # Assert
    assert np.allclose(mesh.extents, original_extents * 2)


def test_evolution_artifacts_report_missing_metric_visual_and_pve_paths(tmp_path):
    # Arrange
    artifact = EvolutionMriArtifacts(
        subject_id="IXI001",
        acquisition_date="2026-06-02",
        metrics_json_path=tmp_path / "missing_metrics.json",
        csf_mesh_path=tmp_path / "csf.glb",
        gm_mesh_path=tmp_path / "gm.glb",
        wm_mesh_path=tmp_path / "wm.glb",
        csf_pve_path=tmp_path / "csf.nii.gz",
        gm_pve_path=tmp_path / "gm.nii.gz",
        wm_pve_path=tmp_path / "wm.nii.gz",
    )
    artifact.gm_mesh_path.write_text("mesh", encoding="utf-8")
    artifact.wm_pve_path.write_text("pve", encoding="utf-8")

    # Act / Assert
    assert artifact.missing_metric_paths() == [artifact.metrics_json_path]
    assert artifact.missing_visual_paths(tissues=["csf", "gm"], include_meshes=True) == [artifact.csf_mesh_path]
    assert artifact.missing_visual_paths(tissues=["csf"], include_meshes=False) == []
    assert artifact.missing_pve_paths(tissues=["wm", "gm"]) == [artifact.gm_pve_path]


def test_evolution_comparison_json_builds_points_and_statistics(tmp_path):
    # Arrange
    first = _create_evolution_artifact(
        tmp_path,
        "2026-01-01",
        volumes={"csf_mm3": 10, "gm_mm3": 20, "wm_mm3": 30},
        surfaces={"csf_mm2": 5, "gm_mm2": 10, "wm_mm2": 15},
    )
    second = _create_evolution_artifact(
        tmp_path,
        "2026-02-01",
        volumes={"csf_mm3": 20, "gm_mm3": 10, "wm_mm3": 30},
        surfaces={"csf_mm2": 10, "gm_mm2": 20, "wm_mm2": 30},
    )
    evolution = MriEvolutionInTime(start_date="2026-01-01", end_date="2026-02-01", mris=[second, first])

    # Act
    report = evolution.build_comparison_json()

    # Assert
    assert report["subject_id"] == "IXI001"
    assert report["dates"] == ["2026-01-01", "2026-02-01"]
    assert report["points"][0]["is_baseline"] is True
    assert report["points"][1]["volumes_mm3"]["csf"]["change_from_baseline_percent"] == 100.0
    assert report["statistics"]["volumes_mm3"]["csf"]["values"]["count"] == 2


def test_evolution_rejects_bad_intervals_missing_dates_and_mixed_subjects(tmp_path):
    # Arrange
    first = _create_evolution_artifact(tmp_path, "2026-01-01")
    second = _create_evolution_artifact(tmp_path, "2026-02-01")
    other_subject = EvolutionMriArtifacts(**{**second.__dict__, "subject_id": "IXI002"})

    # Act / Assert
    with pytest.raises(ValueError, match="start_date"):
        MriEvolutionInTime(start_date="2026-03-01", end_date="2026-01-01", mris=[first])
    with pytest.raises(ValueError, match="same subject"):
        MriEvolutionInTime(start_date="2026-01-01", end_date="2026-02-01", mris=[first, other_subject])

    evolution = MriEvolutionInTime(start_date="2026-01-01", end_date="2026-02-01", mris=[first, second])
    with pytest.raises(ValueError, match="start_date must match"):
        MriEvolutionInTime(start_date="2026-01-15", end_date="2026-02-01", mris=[first, second])._selected_mris()
    with pytest.raises(ValueError, match="end_date must match"):
        MriEvolutionInTime(start_date="2026-01-01", end_date="2026-01-15", mris=[first, second])._selected_mris()
    with pytest.raises(ValueError, match="different from start_date"):
        evolution._get_target_visual_mri([first, second], "2026-01-01")
    with pytest.raises(ValueError, match="not in the selected interval"):
        evolution._get_target_visual_mri([first, second], "2026-03-01")


def test_evolution_validation_and_metric_loading_errors(tmp_path):
    # Arrange
    artifact = _create_evolution_artifact(tmp_path, "2026-01-01")
    artifact.metrics_json_path.unlink()
    evolution = MriEvolutionInTime(start_date="2026-01-01", end_date="2026-01-01", mris=[artifact])

    # Act / Assert
    with pytest.raises(FileNotFoundError):
        evolution.build_comparison_json()

    artifact.metrics_json_path.write_text(json.dumps({"volumes": {}, "surfaces": {}}), encoding="utf-8")
    sparse_report = evolution.build_comparison_json()
    assert sparse_report["baseline_values"]["volumes_mm3"] == {"csf": 0.0, "gm": 0.0, "wm": 0.0}

    artifact.metrics_json_path.write_text(json.dumps({"volumes": [], "surfaces": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing an object"):
        evolution.build_comparison_json()


def test_evolution_math_and_validation_helpers():
    # Arrange
    values = []

    # Act
    _append_optional_float(values, None)
    _append_optional_float(values, "2.5")

    # Assert
    assert values == [2.5]
    assert _safe_ratio_percent(10, 0) is None
    assert _safe_change_percent(15, 10) == 50.0
    assert _basic_stats([]) == {"count": 0, "average": None, "std_dev": None, "min": None, "max": None}
    assert _basic_stats([1, 2, 3])["average"] == 2.0
    assert _normalize_tissues(["GM", "gm", "wm"]) == ("gm", "wm")
    with pytest.raises(ValueError):
        _normalize_tissues([])
    with pytest.raises(ValueError):
        _normalize_tissues(["bad"])
    with pytest.raises(TypeError):
        _require_float(True, label="x")
    with pytest.raises(ValueError):
        _require_float("nan", label="x")
    with pytest.raises(TypeError):
        _require_float(object(), label="x")
    assert _require_mapping({"x": {"a": 1}}, "x") == {"a": 1}
    with pytest.raises(ValueError):
        _require_mapping({"x": []}, "x")


def test_evolution_color_and_export_helpers():
    # Arrange / Act / Assert
    assert _hex_to_rgba("#abc", default_alpha=128) == (170, 187, 204, 128)
    assert _hex_to_rgba("#11223344", default_alpha=128) == (17, 34, 51, 68)
    assert _ComparisonColors.from_hex(baseline_color="#000000", changed_color="#ffffff").baseline == (0, 0, 0, 210)
    with pytest.raises(ValueError):
        _hex_to_rgba("#12", default_alpha=128)
    with pytest.raises(ValueError):
        _hex_to_rgba("#gggggg", default_alpha=128)

    assert _export_scene_to_glb_bytes(types.SimpleNamespace(export=lambda file_type: b"glb")) == b"glb"
    assert _export_scene_to_glb_bytes(types.SimpleNamespace(export=lambda file_type: bytearray(b"glb"))) == b"glb"
    assert _export_scene_to_glb_bytes(types.SimpleNamespace(export=lambda file_type: "glb")) == b"glb"
    with pytest.raises(TypeError):
        _export_scene_to_glb_bytes(types.SimpleNamespace(export=lambda file_type: object()))


def test_evolution_geometry_helpers_split_and_center_meshes():
    # Arrange
    mesh = trimesh.Trimesh(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [5, 5, 5]], dtype=float),
        faces=np.array([[0, 1, 2], [1, 2, 3]]),
        process=False,
    )

    # Act
    unchanged, changed = _split_mesh_by_vertex_mask(mesh, changed_vertex_mask=np.array([False, False, False, True]), trimesh_module=trimesh, numpy_module=np)
    center = _combined_geometry_center([unchanged, changed], numpy_module=np)

    # Assert
    assert unchanged is not None
    assert changed is not None
    assert np.allclose(center, np.array([2.5, 2.5, 2.5]))
    with pytest.raises(ValueError):
        _split_mesh_by_vertex_mask(mesh, changed_vertex_mask=np.array([True]), trimesh_module=trimesh, numpy_module=np)
    empty_mesh = trimesh.Trimesh(vertices=np.empty((0, 3)), faces=np.empty((0, 3), dtype=int), process=False)
    assert _split_mesh_by_vertex_mask(empty_mesh, changed_vertex_mask=np.array([]), trimesh_module=trimesh, numpy_module=np) == (None, None)
    assert np.allclose(_combined_geometry_center([], numpy_module=np), np.zeros(3))


def test_evolution_image_helpers_resample_sample_and_load(monkeypatch, tmp_path):
    # Arrange
    path = tmp_path / "pve.nii.gz"
    path.write_text("pve", encoding="utf-8")
    image = FakeImage(np.array([[[np.nan, 2.0], [-1.0, 0.5]]], dtype=np.float32))
    nib_module = types.SimpleNamespace(load=lambda _path: image)

    # Act
    loaded_img, data = _load_pve_image(path, nib_module=nib_module, numpy_module=np)
    resampled = _resample_pve_data_to_template(image, target=((1, 2, 2), np.eye(4)), resample_from_to_fn=lambda img, _target, **_kwargs: img, numpy_module=np)
    sampled = _sample_volume_at_world_vertices(
        np.arange(8, dtype=float).reshape((2, 2, 2)),
        affine=np.eye(4),
        vertices=np.array([[0, 0, 0], [1, 1, 1]], dtype=float),
        numpy_module=np,
        map_coordinates_fn=lambda volume, coords, **_kwargs: np.array([volume[0, 0, 0], volume[1, 1, 1]]),
    )

    # Assert
    assert loaded_img is image
    assert data.min() == 0.0
    assert data.max() == 1.0
    assert resampled.max() == 1.0
    assert sampled.tolist() == [0.0, 7.0]

    with pytest.raises(ValueError):
        _load_pve_image(path, nib_module=types.SimpleNamespace(load=lambda _path: FakeImage(np.zeros((2, 2)))), numpy_module=np)

    template = tmp_path / "template.nii.gz"
    with pytest.raises(FileNotFoundError):
        _load_resampling_template(template, nib_module=nib_module)
    template.write_text("template", encoding="utf-8")
    assert _load_resampling_template(template, nib_module=nib_module) is image
    with pytest.raises(ValueError):
        _load_resampling_template(template, nib_module=types.SimpleNamespace(load=lambda _path: types.SimpleNamespace(shape=(2, 2))))


def test_evolution_load_first_trimesh_accepts_scene_and_rejects_empty(tmp_path):
    # Arrange
    mesh = trimesh.creation.box()
    scene = types.SimpleNamespace(geometry={"box": mesh})
    module = types.SimpleNamespace(load=lambda *_args, **_kwargs: scene, Trimesh=trimesh.Trimesh)

    # Act / Assert
    assert isinstance(_load_first_trimesh(tmp_path / "mesh.glb", trimesh_module=module), trimesh.Trimesh)
    assert list(_iter_loaded_geometries(scene)) == [mesh]
    assert list(_iter_loaded_geometries(mesh)) == [mesh]

    empty_scene = types.SimpleNamespace(geometry={"empty": trimesh.Trimesh(vertices=[], faces=[])})
    empty_module = types.SimpleNamespace(load=lambda *_args, **_kwargs: empty_scene, Trimesh=trimesh.Trimesh)
    with pytest.raises(ValueError, match="No mesh geometry"):
        _load_first_trimesh(tmp_path / "empty.glb", trimesh_module=empty_module)
