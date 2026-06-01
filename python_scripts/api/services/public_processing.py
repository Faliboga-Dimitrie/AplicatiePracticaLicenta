from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO

from ...project_core.config import Settings, settings as project_settings
from ...project_core.domain import MRICase
from ...project_core.workspace import FileSystemWorkspaceProvider
from ...mri_preprocessing.reorient import FslReorientationBackend
from ...mri_preprocessing.skull_strip import HdBetSkullStripBackend
from ...mri_preprocessing.segmentation import FslFastSegmentationBackend
from ...mesh_analysis.exporters import GlbMeshExporter
from ...mesh_analysis.mesh_extractors import MarchingCubesMeshExtractor
from ...mesh_analysis.pipeline import MeshAnalysisPipeline
from ...mesh_analysis.surface_estimators import TrimeshSurfaceEstimator
from ...mesh_analysis.volume_estimators import PveSumVolumeEstimator


class PublicProcessingService:
    """
    Public, volatile processing service for anonymous visitors.

    This service deliberately avoids database subjects/cases and permanent
    project workspaces. Because the current scientific tools are file-based
    (HD-BET, FSL/fslreorient2std, FAST, trimesh export), the upload is staged
    into a TemporaryDirectory, processed there, zipped into memory, and then the
    temporary directory is removed when the request finishes.
    """

    def __init__(self, settings_obj: Settings = project_settings):
        self.settings = settings_obj

    def process_upload_to_zip(self, file_obj: BinaryIO, filename: str | None) -> tuple[bytes, str]:
        safe_filename = self._safe_upload_filename(filename)

        with tempfile.TemporaryDirectory(prefix="mri_public_") as tmp:
            root = Path(tmp)
            incoming_dir = root / "incoming"
            incoming_dir.mkdir(parents=True, exist_ok=True)
            upload_path = incoming_dir / safe_filename

            with upload_path.open("wb") as target:
                shutil.copyfileobj(file_obj, target)

            volatile_settings = self._temporary_settings(root)
            subject_id = self._subject_id_from_filename(safe_filename)
            case = MRICase(
                subject_id=subject_id,
                acquisition_date="1970-01-01",  # Dummy date since some tools require it, but we don't use it for anything.
                raw_path=upload_path,
            )

            workspace_provider = FileSystemWorkspaceProvider(volatile_settings)
            workspace = workspace_provider.create_workspace(case)

            reorientation = FslReorientationBackend(volatile_settings).run(case, workspace)
            skull_strip = HdBetSkullStripBackend(volatile_settings).run(
                reorientation.output_path,
                workspace,
            )
            segmentation = FslFastSegmentationBackend(volatile_settings).run(
                skull_strip.image_path,
                workspace,
            )

            pipeline = MeshAnalysisPipeline(
                workspace=workspace,
                settings=volatile_settings,
                volume_estimator=PveSumVolumeEstimator(),
                mesh_extractor=MarchingCubesMeshExtractor(),
                surface_estimator=TrimeshSurfaceEstimator(),
                mesh_exporter=GlbMeshExporter(),
                log_timings=False,
            )
            result = pipeline.run()

            zip_bytes = self._zip_public_outputs(
                workspace=workspace,
                result=result,
                upload_filename=safe_filename,
                pve_paths=segmentation.pve_paths,
            )
            return zip_bytes, f"{subject_id}_brain_mri_outputs.zip"

    def _temporary_settings(self, root: Path) -> Settings:
        processed_root = root / "processed_mri"
        return replace(
            self.settings,
            input_mri_dir=root / "input_mri",
            processed_mri_dir=processed_root,
            reoriented_dir=processed_root / "reoriented",
            hd_bet_dir=processed_root / "hd_bet",
            fast_dir=processed_root / "fast",
            mesh_dir=processed_root / "meshes",
            overwrite=True,
            skip_existing=False,
        )

    def _zip_public_outputs(
        self,
        *,
        workspace,
        result,
        upload_filename: str,
        pve_paths: dict[str, Path],
    ) -> bytes:
        payload = result.to_dict()
        payload["upload_filename"] = upload_filename
        payload["files"] = {
            "meshes": {tissue: f"meshes/{path.name}" for tissue, path in workspace.mesh_paths.items()},
            "wireframes": {tissue: f"wireframes/{path.name}" for tissue, path in workspace.wireframe_paths.items()},
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("metrics.json", json.dumps(payload, indent=2))

            for tissue, path in workspace.mesh_paths.items():
                self._write_existing_file(archive, path, f"meshes/{path.name}")

            for tissue, path in workspace.wireframe_paths.items():
                self._write_existing_file(archive, path, f"wireframes/{path.name}")

            # Keep these optional but useful for debugging/scientific inspection.
            # They are PVE probability maps, not required by the UI viewer.
            for tissue, path in pve_paths.items():
                self._write_existing_file(archive, path, f"pve/{path.name}")

            archive.writestr(
                "README.txt",
                "Anonymous Brain MRI Processing output.\n"
                "meshes/ contains solid GLB files.\n"
                "wireframes/ contains wireframe GLB files.\n"
                "metrics.json contains volume and surface-area values.\n"
                "pve/ contains FAST probability maps used to create the meshes.\n",
            )

        return buffer.getvalue()

    def _write_existing_file(self, archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Expected public output file was not created: {path}")
        archive.write(path, arcname)

    def _safe_upload_filename(self, filename: str | None) -> str:
        name = (filename or "anonymous_mri.nii.gz").replace("\\", "_").replace("/", "_").strip()
        lower = name.lower()
        if not (lower.endswith(".nii") or lower.endswith(".nii.gz")):
            raise ValueError("Upload must be a .nii or .nii.gz NIfTI file.")
        return name or "anonymous_mri.nii.gz"

    def _subject_id_from_filename(self, filename: str) -> str:
        lower = filename.lower()
        if lower.endswith(".nii.gz"):
            base = filename[:-7]
        elif lower.endswith(".nii"):
            base = filename[:-4]
        else:
            base = filename
        cleaned = base.replace(" ", "_").replace(".", "_")
        return cleaned[:80] or "anonymous_mri"


__all__ = ["PublicProcessingService"]
