from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...access_control import UserRecord
from ..dependencies import get_current_user, get_job_service
from ..schemas import JobResponse
from ..serialization import job_to_dict
from ..services import JobService

router = APIRouter()


@router.get("", response_model=list[JobResponse])
def list_jobs(
    case_id: int | None = None,
    current_user: UserRecord = Depends(get_current_user),
    jobs: JobService = Depends(get_job_service),
):
    """
    Return jobs created by the logged-in user.

    React can use this for a small activity/history panel, or filter by case_id
    on a case-details page.
    """
    result = jobs.list_for_user(current_user, case_id=case_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Could not load jobs.")
    return [job_to_dict(job) for job in result.data or []]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    current_user: UserRecord = Depends(get_current_user),
    jobs: JobService = Depends(get_job_service),
):
    """
    Poll one job status.

    This is the endpoint React will call every few seconds after starting a
    preprocessing or mesh-analysis job.
    """
    result = jobs.get_for_user(current_user, job_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Could not load job.")
    if result.data is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job_to_dict(result.data)


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: str,
    current_user: UserRecord = Depends(get_current_user),
    jobs: JobService = Depends(get_job_service),
):
    """
    Soft-cancel a job.

    This only marks cancellation as requested. A running preprocessing/mesh
    service must periodically check job.cancel_requested for true cancellation.
    """
    result = jobs.cancel_for_user(current_user, job_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Could not cancel job.")
    if result.data is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job_to_dict(result.data)
