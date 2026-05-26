from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..dependencies import get_public_processing_service
from ..errors import raise_api_error
from ..services.public_processing import PublicProcessingService

router = APIRouter()


@router.post("/process", response_class=Response)
async def process_public_mri(
    file: UploadFile = File(...),
    public_processing: PublicProcessingService = Depends(get_public_processing_service),
):
    """
    Anonymous, volatile MRI processing endpoint.

    The uploaded file is processed in a temporary directory, packaged as a ZIP,
    and returned directly. No user, subject, case, or permanent workspace is
    created for this route.
    """
    try:
        await file.seek(0)
        zip_bytes, filename = await run_in_threadpool(
            public_processing.process_upload_to_zip,
            file.file,
            file.filename,
        )
    except ValueError as exc:
        raise_api_error(status.HTTP_400_BAD_REQUEST, str(exc), code="INVALID_UPLOAD")
    except Exception as exc:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            str(exc),
            code="PUBLIC_PROCESSING_FAILED",
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
