from __future__ import annotations

import json

import numpy as np
import pytest

from python_scripts.mesh_analysis.analysis import MeshAnalysisPipeline
from python_scripts.mesh_analysis.volume_estimators import PveSumVolumeEstimator
from python_scripts.project_core import MeshExportResult, TissueSurfaces, TissueVolumes


class FakeImage:
    def __init__(self, data, affine):
        self._data = np.asarray(data, dtype=np.float32)
        self.affine = np.asarray(affine, dtype=float)

    def get_fdata(self):
        return self._data


def _create_required_pve_files(workspace):
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)
    for path in workspace.fast_pve_paths.values():
        path.write_text("pve", encoding="utf-8")


def test_pve_sum_volume_estimator_clips_invalid_probabilities_before_volume_sum():
    # Arrange
    estimator = PveSumVolumeEstimator()
    image = FakeImage(
        data=np.array([0.5, 1.2, -1.0, np.nan, np.inf, -np.inf], dtype=np.float32),
        affine=np.diag([2.0, 3.0, 4.0, 1.0]),
    )

    # Act
    volume = estimator._volume_for_image(image)  # direct unit test of the core formula

    # Assert
    assert volume == 36.0


def test_mesh_analysis_pipeline_uses_injected_strategies_and_writes_metrics(settings, workspace):
    # Arrange
    _create_required_pve_files(workspace)
    calls: list[str] = []

    class FakeVolumeEstimator:
        def compute(self, pve_paths):
            calls.append("volume")
            assert pve_paths == workspace.fast_pve_paths
            return TissueVolumes(csf_mm3=1.0, gm_mm3=2.0, wm_mm3=3.0)

    class FakeMeshExtractor:
        def extract_all(self, pve_paths):
            calls.append("extract")
            assert pve_paths == workspace.fast_pve_paths
            return {"fake": "meshes"}

    class FakeSurfaceEstimator:
        def compute(self, meshes):
            calls.append("surface")
            assert meshes == {"fake": "meshes"}
            return TissueSurfaces(csf_mm2=4.0, gm_mm2=5.0, wm_mm2=6.0)

    class FakeMeshExporter:
        def export(self, meshes, export_workspace):
            calls.append("export")
            assert meshes == {"fake": "meshes"}
            assert export_workspace is workspace
            export_workspace.mesh_dir.mkdir(parents=True, exist_ok=True)
            for path in export_workspace.mesh_paths.values():
                path.write_text("mesh", encoding="utf-8")
            return MeshExportResult(mesh_paths=export_workspace.mesh_paths)

    pipeline = MeshAnalysisPipeline(
        workspace=workspace,
        settings=settings,
        volume_estimator=FakeVolumeEstimator(),
        mesh_extractor=FakeMeshExtractor(),
        surface_estimator=FakeSurfaceEstimator(),
        mesh_exporter=FakeMeshExporter(),
    )

    # Act
    result = pipeline.run()

    # Assert
    assert calls == ["volume", "extract", "surface", "export"]
    assert result.subject_id == workspace.subject_id
    assert result.acquisition_date == workspace.acquisition_date
    assert result.volumes.gm_mm3 == 2.0
    assert result.surfaces.wm_mm2 == 6.0

    with workspace.metrics_json_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["subject_id"] == workspace.subject_id
    assert payload["acquisition_date"] == workspace.acquisition_date
    assert payload["case_id"] == workspace.case_id
    assert payload["volumes"] == {"csf_mm3": 1.0, "gm_mm3": 2.0, "wm_mm3": 3.0}
    assert payload["surfaces"] == {"csf_mm2": 4.0, "gm_mm2": 5.0, "wm_mm2": 6.0}
    assert set(payload["mesh_paths"]) == {"csf", "gm", "wm"}


def test_mesh_analysis_pipeline_loads_existing_complete_outputs_when_skip_existing(settings, workspace):
    # Arrange
    _create_required_pve_files(workspace)
    workspace.mesh_dir.mkdir(parents=True, exist_ok=True)
    for path in workspace.mesh_paths.values():
        path.write_text("mesh", encoding="utf-8")

    workspace.metrics_json_path.write_text(
        json.dumps(
            {
                "subject_id": workspace.subject_id,
                # Backward-compatible typo supported by the current loader.
                "aquisition_date": "2026-06-02",
                "volumes": {"csf_mm3": 10, "gm_mm3": 20, "wm_mm3": 30},
                "surfaces": {"csf_mm2": 40, "gm_mm2": 50, "wm_mm2": 60},
            }
        ),
        encoding="utf-8",
    )

    class ShouldNotRun:
        def compute(self, *_args, **_kwargs):
            raise AssertionError("Strategy should not run when complete outputs already exist")

        def extract_all(self, *_args, **_kwargs):
            raise AssertionError("Strategy should not run when complete outputs already exist")

        def export(self, *_args, **_kwargs):
            raise AssertionError("Strategy should not run when complete outputs already exist")

    pipeline = MeshAnalysisPipeline(
        workspace=workspace,
        settings=settings,
        volume_estimator=ShouldNotRun(),
        mesh_extractor=ShouldNotRun(),
        surface_estimator=ShouldNotRun(),
        mesh_exporter=ShouldNotRun(),
    )

    # Act
    result = pipeline.run()

    # Assert
    assert result.subject_id == workspace.subject_id
    assert result.acquisition_date == "2026-06-02"
    assert result.volumes.csf_mm3 == 10.0
    assert result.surfaces.wm_mm2 == 60.0


def test_mesh_analysis_pipeline_requires_all_fast_pve_outputs(settings, workspace):
    # Arrange
    workspace.fast_dir.mkdir(parents=True, exist_ok=True)
    next(iter(workspace.fast_pve_paths.values())).write_text("only one pve", encoding="utf-8")
    pipeline = MeshAnalysisPipeline(workspace=workspace, settings=settings)

    # Act / Assert
    with pytest.raises(FileNotFoundError, match="FAST PVE outputs"):
        pipeline.run()
