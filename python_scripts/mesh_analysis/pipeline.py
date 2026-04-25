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
    TissueMasks,
    TissueMeshes,
    TissueSurfaces,
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
    - threshold PVE images into tissue masks
    - convert masks to meshes
    - compute surface areas
    - write masks, meshes, and metrics

    Path and existence knowledge is delegated to CasePaths.
    Directory creation is expected to be handled before this class runs:
    - ensure_main_directories(settings) for global project folders
    - paths.ensure_stage_dirs() for per-case folders
    """

    def __init__(self, paths: CasePaths, settings: Settings):
        self.paths = paths
        self.settings = settings

        self._pves: dict[str, nib.Nifti1Image] | None = None
        self._masks: TissueMasks | None = None
        self._meshes: TissueMeshes | None = None

    def run(self) -> MeshAnalysisResult:
        self._validate_inputs()

        existing = self._handle_existing_outputs()
        if existing is not None:
            return existing

        volumes = self._compute_volumes()

        masks = self._build_tissue_masks()
        self._save_tissue_masks(masks)

        meshes = self._build_tissue_meshes(masks)
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
            surfaces=TissueSurfaces(
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

    def _pve_volume_mm3(self, pve_img: nib.Nifti1Image) -> float:
        data = np.asarray(pve_img.get_fdata(), dtype=np.float32)
        dx, dy, dz = pve_img.header.get_zooms()[:3]
        voxel_volume_mm3 = float(dx * dy * dz)
        return float(data.sum() * voxel_volume_mm3)

    def _compute_volumes(self) -> TissueVolumes:
        pves = self._load_pves()

        return TissueVolumes(
            csf_mm3=self._pve_volume_mm3(pves["csf"]),
            gm_mm3=self._pve_volume_mm3(pves["gm"]),
            wm_mm3=self._pve_volume_mm3(pves["wm"]),
        )

    # -------------------------------------------------------------------------
    # masks
    # -------------------------------------------------------------------------

    def _build_tissue_masks(self) -> TissueMasks:
        if self._masks is not None:
            return self._masks

        pves = self._load_pves()

        self._masks = TissueMasks(
            csf_img=self._make_threshold_mask_image(pves["csf"]),
            gm_img=self._make_threshold_mask_image(pves["gm"]),
            wm_img=self._make_threshold_mask_image(pves["wm"]),
        )
        return self._masks

    def _make_threshold_mask_image(
        self,
        pve_img: nib.Nifti1Image,
        threshold: float = 0.5,
    ) -> nib.Nifti1Image:
        pve_data = np.asarray(pve_img.get_fdata(), dtype=np.float32)

        if pve_data.ndim != 3:
            raise ValueError(
                f"Expected 3D PVE image for mesh analysis, got ndim={pve_data.ndim}"
            )

        mask_data = (pve_data >= threshold).astype(np.uint8)

        header = pve_img.header.copy()
        header.set_data_dtype(np.uint8)

        return nib.Nifti1Image(
            mask_data,
            affine=pve_img.affine,
            header=header,
        )

    def _save_tissue_masks(self, masks: TissueMasks) -> None:
        for tissue, mask_img in masks.as_dict().items():
            nib.save(mask_img, str(self.paths.mesh_mask_paths[tissue]))

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

    def _build_tissue_meshes(self, masks: TissueMasks) -> TissueMeshes:
        if self._meshes is not None:
            return self._meshes

        self._meshes = TissueMeshes(
            csf=self._mask_image_to_mesh(masks.csf_img, "CSF"),
            gm=self._mask_image_to_mesh(masks.gm_img, "GM"),
            wm=self._mask_image_to_mesh(masks.wm_img, "WM"),
        )
        return self._meshes

    def _crop_and_pad_mask_image_to_foreground(
        self,
        mask_img: nib.Nifti1Image,
        tissue_name: str,
    ) -> nib.Nifti1Image:
        mask_data = np.asarray(mask_img.get_fdata(), dtype=np.uint8)

        if mask_data.ndim != 3:
            raise ValueError(
                f"{tissue_name} mask must be 3D, got ndim={mask_data.ndim}"
            )

        foreground = np.argwhere(mask_data > 0)
        if foreground.size == 0:
            raise ValueError(f"{tissue_name} mask contains no foreground voxels.")

        min_i, min_j, min_k = foreground.min(axis=0)
        max_i, max_j, max_k = foreground.max(axis=0)

        cropped = mask_data[
            min_i:max_i + 1,
            min_j:max_j + 1,
            min_k:max_k + 1,
        ]

        # Add a 1-voxel zero border so marching cubes sees a clean outside region.
        padded = np.pad(cropped, pad_width=1, mode="constant", constant_values=0)

        # The padded voxel (1,1,1) corresponds to original voxel (min_i,min_j,min_k).
        # So padded voxel (0,0,0) corresponds to original voxel (min_i-1,min_j-1,min_k-1).
        offset = np.array([min_i - 1, min_j - 1, min_k - 1], dtype=np.float64)

        new_affine = mask_img.affine.copy()
        new_affine[:3, 3] = (
            mask_img.affine[:3, :3] @ offset + mask_img.affine[:3, 3]
        )

        header = mask_img.header.copy()
        header.set_data_dtype(np.uint8)

        return nib.Nifti1Image(
            padded.astype(np.uint8),
            affine=new_affine,
            header=header,
        )

    def _mask_image_to_mesh(
        self,
        mask_img: nib.Nifti1Image,
        tissue_name: str,
    ) -> trimesh.Trimesh:
        prepared_mask_img = self._crop_and_pad_mask_image_to_foreground(
            mask_img,
            tissue_name,
        )
        mask_data = np.asarray(prepared_mask_img.get_fdata(), dtype=np.uint8)

        mask_min = int(mask_data.min())
        mask_max = int(mask_data.max())

        if mask_min == mask_max:
            raise ValueError(
                f"{tissue_name} mask does not contain both background and foreground. "
                f"Found only value {mask_min}."
            )

        verts_voxel, faces, _, _ = marching_cubes(mask_data, level=0.5)
        verts_world = apply_affine(prepared_mask_img.affine, verts_voxel)

        return trimesh.Trimesh(
            vertices=verts_world,
            faces=faces,
            process=False,
        )

    def _compute_surface_areas_from_meshes(
        self,
        meshes: TissueMeshes,
    ) -> TissueSurfaces:
        return TissueSurfaces(
            csf_mm2=float(mesh_surface_area(meshes.csf.vertices, meshes.csf.faces)),
            gm_mm2=float(mesh_surface_area(meshes.gm.vertices, meshes.gm.faces)),
            wm_mm2=float(mesh_surface_area(meshes.wm.vertices, meshes.wm.faces)),
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
        payload["mask_paths"] = {
            tissue: str(path)
            for tissue, path in self.paths.mesh_mask_paths.items()
        }
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
