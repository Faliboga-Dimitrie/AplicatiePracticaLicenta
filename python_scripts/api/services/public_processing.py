from __future__ import annotations

import io
import json
import shutil
import tempfile
import uuid
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, BinaryIO

from ...project_core.config import Settings, settings as project_settings
from ...project_core.domain import MRICase
from ...project_core.workspace import FileSystemWorkspaceProvider
from ...mri_preprocessing.reorient import FslReorientationBackend
from ...mri_preprocessing.skull_strip import HdBetSkullStripBackend
from ...mri_preprocessing.segmentation import FslFastSegmentationBackend
from ...mesh_analysis.exporters import GlbMeshExporter
from ...mesh_analysis.mesh_extractors import MarchingCubesMeshExtractor
from ...mesh_analysis.analysis import MeshAnalysisPipeline
from ...mesh_analysis.surface_estimators import TrimeshSurfaceEstimator
from ...mesh_analysis.volume_estimators import PveSumVolumeEstimator
from ..upload_validation import safe_nifti_upload_filename


class PublicProcessingStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    TERMINAL = {COMPLETED, FAILED}


@dataclass(frozen=True)
class PublicProcessingJobRecord:
    id: str
    status: str
    message: str
    progress: float
    created_at: datetime
    filename: str
    download_filename: str | None = None
    finished_at: datetime | None = None
    error: str | None = None


class PublicProcessingService:
    """
    Public, volatile processing service for anonymous visitors.

    Public processing now runs as a short-lived anonymous background job so the
    React welcome page can show real backend progress instead of simulating it.
    The final output is kept in memory until the API process restarts; no user,
    subject, case, or permanent workspace is created for this route.
    """

    def __init__(self, settings_obj: Settings = project_settings, *, max_workers: int = 1):
        self.settings = settings_obj
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = RLock()
        self._jobs: dict[str, PublicProcessingJobRecord] = {}
        self._outputs: dict[str, tuple[bytes, str]] = {}
        self._futures: dict[str, Future[Any]] = {}

    def start_upload_job(self, file_obj: BinaryIO, filename: str | None) -> PublicProcessingJobRecord:
        """Stage the upload and start processing it in the background."""
        safe_filename = safe_nifti_upload_filename(filename, default="anonymous_mri.nii.gz")
        subject_id = self._subject_id_from_filename(safe_filename)
        job_id = uuid.uuid4().hex
        download_filename = f"{subject_id}_brain_mri_outputs.zip"

        root = Path(tempfile.mkdtemp(prefix="mri_public_job_"))
        incoming_dir = root / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        upload_path = incoming_dir / safe_filename

        with upload_path.open("wb") as target:
            shutil.copyfileobj(file_obj, target)

        record = PublicProcessingJobRecord(
            id=job_id,
            status=PublicProcessingStatus.QUEUED,
            message="Your MRI is waiting to be processed.",
            progress=2.0,
            created_at=datetime.now(timezone.utc),
            filename=safe_filename,
            download_filename=download_filename,
        )

        with self._lock:
            self._jobs[job_id] = record

        future = self._executor.submit(
            self._run_public_job,
            job_id,
            root,
            upload_path,
            safe_filename,
            subject_id,
            download_filename,
        )
        with self._lock:
            self._futures[job_id] = future

        return record

    def get_job(self, job_id: str) -> PublicProcessingJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_completed_output(self, job_id: str) -> tuple[bytes, str] | None:
        job = self.get_job(job_id)
        if job is None or job.status != PublicProcessingStatus.COMPLETED:
            return None
        with self._lock:
            return self._outputs.get(job_id)

    def process_upload_to_zip(self, file_obj: BinaryIO, filename: str | None) -> tuple[bytes, str]:
        """
        Synchronous compatibility path for the older /public/process endpoint.

        The frontend now uses /public/process-jobs for real progress, but this
        method is kept for direct API usage and older tests.
        """
        safe_filename = safe_nifti_upload_filename(filename, default="anonymous_mri.nii.gz")

        with tempfile.TemporaryDirectory(prefix="mri_public_") as tmp:
            root = Path(tmp)
            incoming_dir = root / "incoming"
            incoming_dir.mkdir(parents=True, exist_ok=True)
            upload_path = incoming_dir / safe_filename

            with upload_path.open("wb") as target:
                shutil.copyfileobj(file_obj, target)

            zip_bytes = self._process_staged_upload(
                root=root,
                upload_path=upload_path,
                safe_filename=safe_filename,
                progress_callback=None,
            )
            subject_id = self._subject_id_from_filename(safe_filename)
            return zip_bytes, f"{subject_id}_brain_mri_outputs.zip"

    def _run_public_job(
        self,
        job_id: str,
        root: Path,
        upload_path: Path,
        safe_filename: str,
        subject_id: str,
        download_filename: str,
    ) -> None:
        def report(progress: float) -> None:
            self._update_job(
                job_id,
                status=PublicProcessingStatus.RUNNING,
                message="Your MRI is being processed. Keep this page open until the result is ready.",
                progress=progress,
            )

        try:
            self._update_job(
                job_id,
                status=PublicProcessingStatus.RUNNING,
                message="Your MRI is being processed. Keep this page open until the result is ready.",
                progress=5.0,
            )
            zip_bytes = self._process_staged_upload(
                root=root,
                upload_path=upload_path,
                safe_filename=safe_filename,
                progress_callback=report,
            )
            with self._lock:
                self._outputs[job_id] = (zip_bytes, download_filename)

            self._update_job(
                job_id,
                status=PublicProcessingStatus.COMPLETED,
                message="Processing complete. Your result is ready to download.",
                progress=100.0,
                finished_at=datetime.now(timezone.utc),
                download_filename=download_filename,
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status=PublicProcessingStatus.FAILED,
                message="We could not process this MRI. Check the file and try again.",
                progress=100.0,
                finished_at=datetime.now(timezone.utc),
                error=str(exc),
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _process_staged_upload(
        self,
        *,
        root: Path,
        upload_path: Path,
        safe_filename: str,
        progress_callback,
    ) -> bytes:
        def progress(value: float) -> None:
            if progress_callback is not None:
                progress_callback(value)

        volatile_settings = self._temporary_settings(root)
        subject_id = self._subject_id_from_filename(safe_filename)
        case = MRICase(
            subject_id=subject_id,
            acquisition_date="1970-01-01",  # Dummy date; public processing is not persisted as a real case.
            raw_path=upload_path,
        )

        workspace_provider = FileSystemWorkspaceProvider(volatile_settings)
        workspace = workspace_provider.create_workspace(case)

        progress(12.0)
        reorientation = FslReorientationBackend(volatile_settings).run(case, workspace)

        progress(30.0)
        skull_strip = HdBetSkullStripBackend(volatile_settings).run(
            reorientation.output_path,
            workspace,
        )

        progress(55.0)
        segmentation = FslFastSegmentationBackend(volatile_settings).run(
            skull_strip.image_path,
            workspace,
        )

        progress(75.0)
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

        progress(94.0)
        zip_bytes = self._zip_public_outputs(
            workspace=workspace,
            result=result,
            upload_filename=safe_filename,
        )
        progress(98.0)
        return zip_bytes

    def _update_job(self, job_id: str, **changes: Any) -> PublicProcessingJobRecord:
        with self._lock:
            current = self._jobs[job_id]
            if "progress" in changes and changes["progress"] is not None:
                changes["progress"] = max(0.0, min(100.0, float(changes["progress"])))
            updated = replace(current, **changes)
            self._jobs[job_id] = updated
            return updated

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
    ) -> bytes:
        payload = result.to_dict()
        payload["upload_filename"] = upload_filename
        payload["files"] = {
            "meshes": {tissue: f"meshes/{path.name}" for tissue, path in workspace.mesh_paths.items()},
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("metrics.json", json.dumps(payload, indent=2))

            for tissue, path in workspace.mesh_paths.items():
                self._write_existing_file(archive, path, f"meshes/{path.name}")

        return buffer.getvalue()

    def _write_existing_file(self, archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Expected public output file was not created: {path}")

        lower = path.name.lower()
        if not (lower.endswith(".glb") or lower.endswith(".json")):
            raise ValueError(f"Public downloads may contain only GLB and JSON files: {path.name}")

        archive.write(path, arcname)

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


def public_processing_job_to_dict(job: PublicProcessingJobRecord) -> dict[str, Any]:
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "progress": job.progress,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "filename": job.filename,
        "download_filename": job.download_filename,
        "error": job.error,
    }


__all__ = [
    "PublicProcessingJobRecord",
    "PublicProcessingService",
    "PublicProcessingStatus",
    "public_processing_job_to_dict",
]
