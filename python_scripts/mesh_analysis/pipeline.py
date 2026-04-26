from __future__ import annotations

import json
from dataclasses import dataclass

import nibabel as nib
from nibabel.affines import apply_affine
import numpy as np
import trimesh
from skimage.measure import marching_cubes, mesh_surface_area

from ..project_core import Settings, ensure_main_directories, settings
from ..project_core import MRICase, CasePaths
from ..project_core import build_prepared_case_paths, run_pipeline_cli
from .io import load_fast_pves
from .models import (
    MeshAnalysisResult,
    TissueMeshes,
    TissueMeshSurfaces,
    TissueVolumes,
)

@dataclass
class CaseRunResult:
    subject_id: str
    success: bool
    result: MeshAnalysisResult | None = None
    error: str | None = None


class MeshAnalysisPipeline:
    """
    Mesh-analysis stage for one MRI case.

    This class now focuses only on the actual mesh-analysis work:
    - load FAST PVE images
    - compute tissue volumes
    - use PVE images to build meshes via marching cubes
    - compute surface areas
    - write meshes, and metrics

    Path and existence knowledge is delegated to CasePaths.
    Directory creation is expected to be handled before this class runs:
    - ensure_main_directories(settings) for global project folders
    - paths.ensure_stage_dirs() for per-case folders
    """

    PVE_MESH_LEVEL = 0.5

    def __init__(self, paths: CasePaths, settings: Settings):
        self.paths = paths
        self.settings = settings

        self._pves: dict[str, nib.Nifti1Image] | None = None
        self._meshes: TissueMeshes | None = None

    def run(self) -> MeshAnalysisResult:
        self._validate_inputs()

        existing = self._handle_existing_outputs()
        if existing is not None:
            return existing

        volumes = self._compute_volumes()

        meshes = self._build_tissue_meshes()
        surfaces = self._compute_surface_areas_from_meshes(meshes)
        self._export_meshes(meshes)

        result = MeshAnalysisResult(
            subject_id=self.paths.subject_id,
            volumes=volumes,
            surfaces=surfaces,
        )
        self._write_metrics_json(result)
        return result

    # -------------------------------------------------------------------------
    # existing-output policy
    # -------------------------------------------------------------------------

    def _handle_existing_outputs(self) -> MeshAnalysisResult | None:
        if self.paths.has_complete_mesh_outputs:
            if self.settings.skip_existing:
                return self._load_existing_result()

            if not self.settings.overwrite:
                raise FileExistsError(
                    f"Mesh-analysis outputs already exist for {self.paths.subject_id} in "
                    f"{self.paths.mesh_dir}. Set overwrite=True to rerun."
                )

            self._remove_existing_mesh_outputs()
            return None

        if self.paths.has_any_mesh_outputs:
            if not self.settings.overwrite:
                raise FileExistsError(
                    f"Partial mesh-analysis outputs already exist for {self.paths.subject_id} in "
                    f"{self.paths.mesh_dir}. Set overwrite=True to clean and rerun."
                )

            self._remove_existing_mesh_outputs()

        return None

    def _remove_existing_mesh_outputs(self) -> None:
        for path in self.paths.mesh_output_paths:
            if path.exists():
                path.unlink()

    def _load_existing_result(self) -> MeshAnalysisResult:
        metrics_path = self.paths.mesh_metrics_json_path

        with metrics_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        volumes_data = payload["volumes"]
        surfaces_data = payload["surfaces"]

        return MeshAnalysisResult(
            subject_id=str(payload["subject_id"]),
            volumes=TissueVolumes(
                csf_mm3=float(volumes_data["csf_mm3"]),
                gm_mm3=float(volumes_data["gm_mm3"]),
                wm_mm3=float(volumes_data["wm_mm3"]),
            ),
            surfaces=TissueMeshSurfaces(
                csf_mm2=float(surfaces_data["csf_mm2"]),
                gm_mm2=float(surfaces_data["gm_mm2"]),
                wm_mm2=float(surfaces_data["wm_mm2"]),
            ),
        )

    # -------------------------------------------------------------------------
    # validation / loading
    # -------------------------------------------------------------------------

    def _validate_inputs(self) -> None:
        missing = self.paths.missing_fast_pve_paths
        if missing:
            missing_str = "\n".join(str(path) for path in missing)
            raise FileNotFoundError(
                "Mesh analysis requires FAST PVE outputs, but some files are missing:\n"
                f"{missing_str}"
            )

    def _load_pves(self) -> dict[str, nib.Nifti1Image]:
        if self._pves is None:
            self._pves = load_fast_pves(self.paths)
        return self._pves

    # -------------------------------------------------------------------------
    # volume
    # -------------------------------------------------------------------------

    def _voxel_volume_mm3(self, img: nib.Nifti1Image) -> float:
    # More robust than header zooms if the affine has rotations/shears
        return float(abs(np.linalg.det(img.affine[:3, :3])))


    def _pve_volume_mm3(self, pve_img: nib.Nifti1Image) -> float:
        data = np.asarray(pve_img.get_fdata(), dtype=np.float32)

        # Avoid tiny numerical weirdness outside [0, 1]
        data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)
        data = np.clip(data, 0.0, 1.0)

        voxel_volume_mm3 = self._voxel_volume_mm3(pve_img)

        return round(float(data.sum() * voxel_volume_mm3), 3)

    def _compute_volumes(self) -> TissueVolumes:
        pves = self._load_pves()

        return TissueVolumes(
            csf_mm3=self._pve_volume_mm3(pves["csf"]),
            gm_mm3=self._pve_volume_mm3(pves["gm"]),
            wm_mm3=self._pve_volume_mm3(pves["wm"]),
        )

    # -------------------------------------------------------------------------
    # meshes
    # -------------------------------------------------------------------------

    def _scale_mesh(
    self,
    mesh: trimesh.Trimesh,
    factor: float,
) -> None:
        transform = trimesh.transformations.scale_matrix(
            factor=factor,
            origin=mesh.centroid,
        )
        mesh.apply_transform(transform)

    def _rotate_mesh_x_90(self, mesh: trimesh.Trimesh) -> None:
        transform = trimesh.transformations.rotation_matrix(
            angle=np.deg2rad(-90.0),
            direction=[1, 0, 0],
            point=mesh.centroid,
        )
        mesh.apply_transform(transform)

    def _apply_transparent_material(
        self,
        mesh: trimesh.Trimesh,
        rgba: tuple[int, int, int, int],
    ) -> None:
        material = trimesh.visual.material.PBRMaterial(
            baseColorFactor=list(rgba),
            alphaMode="BLEND",
            doubleSided=True,
        )

        mesh.visual = trimesh.visual.TextureVisuals(material=material)

    def _build_tissue_meshes(self) -> TissueMeshes:
        if self._meshes is not None:
            return self._meshes
        
        pves = self._load_pves()

        self._meshes = TissueMeshes(
            csf=self._mask_image_to_mesh(pves["csf"], "CSF"),
            gm=self._mask_image_to_mesh(pves["gm"], "GM"),
            wm=self._mask_image_to_mesh(pves["wm"], "WM"),
        )
        return self._meshes  

    def _mask_image_to_mesh(
        self,
        pve_img: nib.Nifti1Image,
        tissue_name: str,
        level: float = PVE_MESH_LEVEL,
    ) -> trimesh.Trimesh:
        
        pve_data = np.asarray(pve_img.get_fdata(), dtype=np.float32)

        if pve_data.ndim != 3:
            raise ValueError(
                f"Expected 3D PVE image for mesh analysis, got ndim={pve_data.ndim}"
            )

        pve_data = np.nan_to_num(pve_data, nan=0.0, posinf=0.0, neginf=0.0)
        pve_data = np.clip(pve_data, 0.0, 1.0)

        data_min = float(pve_data.min())
        data_max = float(pve_data.max())

        if not (data_min < level < data_max):
            raise ValueError(
                f"{tissue_name} PVE image cannot be meshed at level {level}. "
                f"Data range is [{data_min}, {data_max}]."
            )

        verts_voxel, faces, _, _ = marching_cubes(pve_data, level=level)
        verts_world = apply_affine(pve_img.affine, verts_voxel)

        return trimesh.Trimesh(
            vertices=verts_world,
            faces=faces,
            process=False,
        )

    def _compute_surface_areas_from_meshes(
        self,
        meshes: TissueMeshes,
    ) -> TissueMeshSurfaces:
        return TissueMeshSurfaces(
            csf_mm2=round(float(mesh_surface_area(meshes.csf.vertices, meshes.csf.faces)), 3),
            gm_mm2=round(float(mesh_surface_area(meshes.gm.vertices, meshes.gm.faces)), 3),
            wm_mm2=round(float(mesh_surface_area(meshes.wm.vertices, meshes.wm.faces)), 3),
        )

    def _export_meshes(self, meshes: TissueMeshes) -> None:
        export_map = {
        "csf": (self.paths.mesh_csf_mesh_path, (80, 140, 255, 60)),
        "gm":  (self.paths.mesh_gm_mesh_path,  (80, 140, 255, 90)),
        "wm":  (self.paths.mesh_wm_mesh_path,  (80, 140, 255, 180)),
    }

        for tissue, mesh in meshes.as_dict().items():
            out_path, rgba = export_map[tissue]
            self._rotate_mesh_x_90(mesh)
            self._scale_mesh(mesh, factor=1.0)
            self._apply_transparent_material(mesh, rgba)
            mesh.export(str(out_path), file_type="glb")

    # -------------------------------------------------------------------------
    # metrics export
    # -------------------------------------------------------------------------

    def _write_metrics_json(self, result: MeshAnalysisResult) -> None:
        payload = result.to_dict()
        payload["mesh_paths"] = {
            tissue: str(path)
            for tissue, path in self.paths.mesh_paths.items()
        }

        with self.paths.mesh_metrics_json_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


def _preflight_checks(settings_obj: Settings) -> None:
    ensure_main_directories(settings_obj)


def _process_case(case: MRICase, settings_obj: Settings) -> CaseRunResult:
    paths = build_prepared_case_paths(case, settings_obj)

    try:
        pipeline = MeshAnalysisPipeline(paths, settings_obj)
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


def _print_summary(results: list[CaseRunResult]) -> None:
    print("\n" + "#" * 80)
    print("MESH ANALYSIS SUMMARY")
    print("#" * 80)

    ok_count = 0
    fail_count = 0

    for res in results:
        if res.success and res.result is not None:
            ok_count += 1
            print(f"[OK] {res.subject_id}")
            print(f"     volumes : {res.result.volumes.to_dict()}")
            print(f"     surfaces: {res.result.surfaces.to_dict()}")
        else:
            fail_count += 1
            print(f"[FAIL] {res.subject_id}")
            print(f"       error: {res.error}")

    print("-" * 80)
    print(f"Successful: {ok_count}")
    print(f"Failed    : {fail_count}")
    print(f"Total     : {len(results)}")


def main() -> int:
    return run_pipeline_cli(
        description="Run the mesh-analysis pipeline: PVE volumes -> masks -> meshes -> metrics",
        settings_obj=settings,
        preflight_checks=_preflight_checks,
        process_case=_process_case,
        print_summary=_print_summary,
        case_header_title="Mesh analysis for case",
        success_message=lambda case, _result: f"[OK] Completed mesh analysis: {case.subject_id}",
    )


if __name__ == "__main__":
    raise SystemExit(main())
