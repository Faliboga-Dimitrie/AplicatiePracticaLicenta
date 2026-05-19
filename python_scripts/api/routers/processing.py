from __future__ import annotations

from fastapi import APIRouter, Depends

from ...access_control import UserRecord
from ..dependencies import (
    get_current_user,
    get_mesh_analysis_service,
    get_preprocessing_service,
)
from ..errors import unwrap_result
from ..schemas import JobResponse
from ..serialization import job_to_dict
from ..services import MeshAnalysisService, PreprocessingService

router = APIRouter()


@router.post("/cases/{case_id}/preprocessing-jobs", response_model=JobResponse)
def start_preprocessing_job(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    preprocessing: PreprocessingService = Depends(get_preprocessing_service),
):
    """
    Start preprocessing for one authorized MRI case and return immediately.

    React should not wait for HD-BET/FAST inside this request. It receives the
    job id here, then polls GET /jobs/{job_id} until the status becomes
    completed or failed.
    """
    result = preprocessing.start_for_case(current_user, case_id)
    job = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to preprocess it.",
    )
    return job_to_dict(job)


@router.post("/cases/{case_id}/mesh-analysis-jobs", response_model=JobResponse)
def start_mesh_analysis_job(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    mesh_analysis: MeshAnalysisService = Depends(get_mesh_analysis_service),
):
    """
    Start mesh analysis for one authorized MRI case and return immediately.

    React receives the job id here, then polls GET /jobs/{job_id}. When the job
    is completed, the result contains metrics and frontend-safe artifact URLs
    for the generated GLB files/metrics JSON.
    """
    result = mesh_analysis.start_for_case(current_user, case_id)
    job = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to run mesh analysis.",
    )
    return job_to_dict(job)


@router.post("/{case_id}/preprocess", response_model=JobResponse)
def preprocess_case_legacy_path(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    preprocessing: PreprocessingService = Depends(get_preprocessing_service),
):
    """
    Compatibility alias for the old testing endpoint.

    The old endpoint used to block until preprocessing finished. It now follows
    the web/backend contract and returns a JobResponse immediately.
    """
    return start_preprocessing_job(
        case_id=case_id,
        current_user=current_user,
        preprocessing=preprocessing,
    )


@router.post("/{case_id}/mesh", response_model=JobResponse)
def mesh_case_legacy_path(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    mesh_analysis: MeshAnalysisService = Depends(get_mesh_analysis_service),
):
    """
    Compatibility alias for a simple mesh-analysis testing endpoint.
    """
    return start_mesh_analysis_job(
        case_id=case_id,
        current_user=current_user,
        mesh_analysis=mesh_analysis,
    )
