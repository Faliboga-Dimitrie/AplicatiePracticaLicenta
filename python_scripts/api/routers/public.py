from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..dependencies import get_public_processing_service
from ..errors import raise_api_error
from ..schemas import PublicProcessingJobResponse
from ..services.public_processing import PublicProcessingService, public_processing_job_to_dict

router = APIRouter()


@router.post("/process-jobs", response_model=PublicProcessingJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_public_processing_job(
    file: UploadFile = File(...),
    public_processing: PublicProcessingService = Depends(get_public_processing_service),
):
    """
    Start anonymous, volatile MRI processing and return a public job id.

    The frontend polls GET /public/process-jobs/{job_id} to show real backend
    progress, then downloads the ZIP from /public/process-jobs/{job_id}/download.
    """
    try:
        await file.seek(0)
        job = await run_in_threadpool(
            public_processing.start_upload_job,
            file.file,
            file.filename,
        )
    except ValueError as exc:
        raise_api_error(status.HTTP_400_BAD_REQUEST, str(exc), code="INVALID_UPLOAD")
    except Exception as exc:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            str(exc),
            code="PUBLIC_PROCESSING_START_FAILED",
        )

    return public_processing_job_to_dict(job)


@router.get("/process-jobs/{job_id}", response_model=PublicProcessingJobResponse)
def get_public_processing_job(
    job_id: str,
    public_processing: PublicProcessingService = Depends(get_public_processing_service),
):
    job = public_processing.get_job(job_id)
    if job is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "Processing job not found.", code="PUBLIC_JOB_NOT_FOUND")
    return public_processing_job_to_dict(job)


@router.get("/process-jobs/{job_id}/download", response_class=Response)
def download_public_processing_result(
    job_id: str,
    public_processing: PublicProcessingService = Depends(get_public_processing_service),
):
    job = public_processing.get_job(job_id)
    if job is None:
        raise_api_error(status.HTTP_404_NOT_FOUND, "Processing job not found.", code="PUBLIC_JOB_NOT_FOUND")
    if job.status == "failed":
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            job.error or "This MRI could not be processed.",
            code="PUBLIC_PROCESSING_FAILED",
        )

    output = public_processing.get_completed_output(job_id)
    if output is None:
        raise_api_error(
            status.HTTP_409_CONFLICT,
            "The result is not ready yet.",
            code="PUBLIC_RESULT_NOT_READY",
        )

    zip_bytes, filename = output
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
