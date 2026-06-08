from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from ..project_core import (
    CaseWorkspace,
    MeshAnalysisResult,
    MeshExportResult,
    MeshExporter as MeshExporterPort,
    MeshExtractor as MeshExtractorPort,
    Settings,
    SurfaceEstimator as SurfaceEstimatorPort,
    TissueSurfaces,
    TissueVolumes,
    VolumeEstimator as VolumeEstimatorPort,
)

from .exporters import GlbMeshExporter
from .mesh_extractors import MarchingCubesMeshExtractor
from .models import MeshAnalysisMeshes
from .surface_estimators import TrimeshSurfaceEstimator
from .volume_estimators import PveSumVolumeEstimator


class MeshAnalysisPipeline:
    """
    Mesh-analysis orchestration for one MRI case.

    The class coordinates injectable strategy interfaces instead of hardcoding
    the algorithms directly. The default strategies use the current approach:
    PVE-sum volume estimation, skimage marching cubes, trimesh surface area,
    and GLB export.
    """

    def __init__(
        self,
        workspace: CaseWorkspace,
        settings: Settings,
        *,
        volume_estimator: VolumeEstimatorPort | None = None,
        mesh_extractor: MeshExtractorPort[MeshAnalysisMeshes] | None = None,
        surface_estimator: SurfaceEstimatorPort[MeshAnalysisMeshes] | None = None,
        mesh_exporter: MeshExporterPort[MeshAnalysisMeshes] | None = None,
    ):
        self.workspace = workspace
        self.settings = settings
        self.volume_estimator = volume_estimator or PveSumVolumeEstimator()
        self.mesh_extractor = mesh_extractor or MarchingCubesMeshExtractor()
        self.surface_estimator = surface_estimator or TrimeshSurfaceEstimator()
        self.mesh_exporter = mesh_exporter or GlbMeshExporter()

    def run(self) -> MeshAnalysisResult:
        self._validate_inputs()

        existing = self._handle_existing_outputs()
        if existing is not None:
            return existing

        pve_paths = self.workspace.fast_pve_paths
        volumes = self.volume_estimator.compute(pve_paths)
        meshes = self.mesh_extractor.extract_all(pve_paths)
        surfaces = self.surface_estimator.compute(meshes)
        export_result = self.mesh_exporter.export(meshes, self.workspace)

        result = MeshAnalysisResult(
            subject_id=self.workspace.subject_id,
            volumes=volumes,
            surfaces=surfaces,
            acquisition_date=self.workspace.acquisition_date,
        )

        self._write_metrics_json(result, export_result)

        return result

    def _handle_existing_outputs(self) -> MeshAnalysisResult | None:
        partial_outputs_exist = self.workspace.has_any_mesh_analysis_outputs

        if not partial_outputs_exist:
            return None

        full_outputs_exist = self.workspace.has_complete_mesh_analysis_outputs

        if full_outputs_exist:
            if self.settings.skip_existing:
                return self._load_existing_result()

            if not self.settings.overwrite:
                raise FileExistsError(
                    f"Mesh-analysis outputs already exist for {self.workspace.subject_id} in "
                    f"{self.workspace.mesh_dir}. Set overwrite=True to rerun."
                )

            self._remove_existing_outputs()
            return None

        if partial_outputs_exist:
            if not self.settings.overwrite:
                raise FileExistsError(
                    f"Partial mesh-analysis outputs already exist for {self.workspace.subject_id} in "
                    f"{self.workspace.mesh_dir}. Set overwrite=True to clean and rerun."
                )

            self._remove_existing_outputs()

        return None

    def _remove_existing_outputs(self) -> None:
        for path in self.workspace.mesh_analysis_output_paths:
            if path.exists():
                path.unlink()

    def _load_existing_result(self) -> MeshAnalysisResult:
        metrics_path = self.workspace.metrics_json_path

        with metrics_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        return MeshAnalysisResult(
            subject_id=str(payload["subject_id"]),
            volumes=TissueVolumes.from_mapping(payload["volumes"]),
            surfaces=TissueSurfaces.from_mapping(payload["surfaces"]),
            acquisition_date=str(payload.get("acquisition_date") or payload.get("aquisition_date") or self.workspace.acquisition_date),
        )

    def _validate_inputs(self) -> None:
        missing = self.workspace.missing_fast_pve_paths
        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(
                "Mesh analysis requires FAST PVE outputs, but some files are missing:\n"
                f"{missing_str}"
            )

    def _write_metrics_json(
        self,
        result: MeshAnalysisResult,
        export_result: MeshExportResult,
    ) -> None:
        payload = result.to_dict()
        payload["mesh_paths"] = _stringify_paths(export_result.mesh_paths)

        self.workspace.metrics_json_path.parent.mkdir(parents=True, exist_ok=True)
        with self.workspace.metrics_json_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


def _stringify_paths(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items()}


__all__ = ["MeshAnalysisPipeline"]
