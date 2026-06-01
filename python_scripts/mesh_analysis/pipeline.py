from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..project_core import (
    CaseWorkspace,
    MeshAnalysisResult,
    MeshExportResult,
    MeshExporter as MeshExporterPort,
    MeshExtractor as MeshExtractorPort,
    MRICase,
    Settings,
    SurfaceEstimator as SurfaceEstimatorPort,
    TissueSurfaces,
    TissueVolumes,
    VolumeEstimator as VolumeEstimatorPort,
    build_prepared_case_paths,
    ensure_main_directories,
    run_pipeline_cli,
    settings,
)

from .exporters import GlbMeshExporter
from .mesh_extractors import MarchingCubesMeshExtractor
from .models import MeshAnalysisMeshes
from .surface_estimators import TrimeshSurfaceEstimator
from .volume_estimators import PveSumVolumeEstimator


@dataclass
class CaseRunResult:
    subject_id: str
    success: bool
    result: MeshAnalysisResult | None = None
    error: str | None = None


class MeshAnalysisPipeline:
    """
    Mesh-analysis orchestration for one MRI case.

    This class now coordinates strategy interfaces instead of hardcoding the
    algorithms directly. The default strategies still use your current approach:
    - PVE sum volume estimation
    - skimage marching cubes
    - mesh triangle surface area
    - trimesh GLB export

    The important change is that the pipeline depends on protocols, so a future
    implementation can replace one strategy without modifying this class.
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
        log_timings: bool = True,
    ):
        self.workspace = workspace
        self.settings = settings
        self.volume_estimator = volume_estimator or PveSumVolumeEstimator()
        self.mesh_extractor = mesh_extractor or MarchingCubesMeshExtractor()
        self.surface_estimator = surface_estimator or TrimeshSurfaceEstimator()
        self.mesh_exporter = mesh_exporter or GlbMeshExporter()
        self.log_timings = log_timings

    def run(self) -> MeshAnalysisResult:
        self._validate_inputs()

        existing = self._handle_existing_outputs()
        if existing is not None:
            return existing

        pve_paths = self.workspace.fast_pve_paths

        t0 = time.perf_counter()
        volumes = self.volume_estimator.compute(pve_paths)
        t1 = time.perf_counter()

        meshes = self.mesh_extractor.extract_all(pve_paths)
        t2 = time.perf_counter()

        surfaces = self.surface_estimator.compute(meshes)
        t3 = time.perf_counter()

        export_result = self.mesh_exporter.export(meshes, self.workspace)
        t4 = time.perf_counter()

        result = MeshAnalysisResult(
            subject_id=self.workspace.subject_id,
            volumes=volumes,
            surfaces=surfaces,
        )

        self._write_metrics_json(result, export_result)

        if self.log_timings:
            print(f"volume computation: {t1 - t0:.3f}s")
            print(f"mesh build: {t2 - t1:.3f}s")
            print(f"surface area computation: {t3 - t2:.3f}s")
            print(f"mesh/wireframe export: {t4 - t3:.3f}s")

        return result

    # -------------------------------------------------------------------------
    # existing-output policy
    # -------------------------------------------------------------------------

    def _handle_existing_outputs(self) -> MeshAnalysisResult | None:
        partial_outputs_exist = self.workspace.has_any_mesh_analysis_outputs

        if not partial_outputs_exist:
            return None

        full_outputs_exist = (
            self.workspace.has_complete_mesh_analysis_outputs
            if self._wireframes_expected()
            else self.workspace.has_complete_mesh_outputs
        )

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

    def _wireframes_expected(self) -> bool:
        config = getattr(self.mesh_extractor, "config", None)
        if config is None:
            return True
        return bool(getattr(config, "create_wireframe_source", True)) and getattr(config, "wireframe_step_size", None) is not None

    def _load_existing_result(self) -> MeshAnalysisResult:
        metrics_path = self.workspace.mesh_metrics_json_path

        with metrics_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        return MeshAnalysisResult(
            subject_id=str(payload["subject_id"]),
            volumes=TissueVolumes.from_mapping(payload["volumes"]),
            surfaces=TissueSurfaces.from_mapping(payload["surfaces"]),
        )

    # -------------------------------------------------------------------------
    # validation
    # -------------------------------------------------------------------------

    def _validate_inputs(self) -> None:
        missing = self.workspace.missing_fast_pve_paths
        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(
                "Mesh analysis requires FAST PVE outputs, but some files are missing:\n"
                f"{missing_str}"
            )

    # -------------------------------------------------------------------------
    # metrics export
    # -------------------------------------------------------------------------

    def _write_metrics_json(
        self,
        result: MeshAnalysisResult,
        export_result: MeshExportResult,
    ) -> None:
        payload = result.to_dict()
        payload["mesh_paths"] = _stringify_paths(export_result.mesh_paths)

        if export_result.wireframe_paths is not None:
            payload["wireframe_paths"] = _stringify_paths(export_result.wireframe_paths)

        self.workspace.mesh_metrics_json_path.parent.mkdir(parents=True, exist_ok=True)
        with self.workspace.mesh_metrics_json_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


def _stringify_paths(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: str(path) for name, path in paths.items()}


def _preflight_checks(settings_obj: Settings) -> None:
    ensure_main_directories(settings_obj)


def _process_case(case: MRICase, settings_obj: Settings) -> CaseRunResult:
    workspace = build_prepared_case_paths(case, settings_obj)

    try:
        pipeline = MeshAnalysisPipeline(workspace, settings_obj)
        result = pipeline.run()

        return CaseRunResult(
            subject_id=case.subject_id,
            success=True,
            result=result,
        )

    except Exception as exc:
        return CaseRunResult(
            subject_id=case.subject_id,
            success=False,
            error=str(exc),
        )


def _print_summary(case: CaseRunResult) -> bool:
    print("\n" + "#" * 80)
    print("MESH ANALYSIS SUMMARY")
    print("#" * 80)

    ok: bool = case.success and case.result is not None

    if ok:
        print(f"[OK] {case.subject_id}")
        print(f"     volumes : {case.result.volumes.to_dict()}")
        print(f"     surfaces: {case.result.surfaces.to_dict()}")
    else:
        print(f"[FAIL] {case.subject_id}")
        print(f"       error: {case.error}")

    print("-" * 80)
    return ok


def main() -> int:
    return run_pipeline_cli(
        description="Run the mesh-analysis pipeline: PVE volumes -> meshes -> metrics",
        settings_obj=settings,
        preflight_checks=_preflight_checks,
        process_case=_process_case,
        print_summary=_print_summary,
        case_header_title="Mesh analysis for case",
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CaseRunResult",
    "MeshAnalysisPipeline",
    "main",
]
