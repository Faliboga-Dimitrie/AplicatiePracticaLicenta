from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from ...access_control import UserRecord
from ..dependencies import (
    get_current_user,
    get_mesh_analysis_service,
    get_preprocessing_service,
    get_statistics_service,
)
from ..errors import raise_api_error, unwrap_result
from ..schemas import JobResponse
from ..serialization import job_to_dict
from ..services import MeshAnalysisService, PreprocessingService, StatisticsService

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
    if not result.success and result.error == preprocessing.ACTIVE_JOB_MESSAGE:
        raise_api_error(409, result.error, code="ACTIVE_JOB_EXISTS")

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
    if not result.success and result.error == mesh_analysis.ACTIVE_JOB_MESSAGE:
        raise_api_error(409, result.error, code="ACTIVE_JOB_EXISTS")

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


@router.get("/subjects/{subject_id}/evolution/dates")
def list_evolution_dates(
    subject_id: str,
    current_user: UserRecord = Depends(get_current_user),
    statistics: StatisticsService = Depends(get_statistics_service),
):
    """Return dates and readiness flags for a subject time-comparison UI."""
    result = statistics.evolution_dates_for_subject(current_user, subject_id)
    return unwrap_result(
        result,
        not_found_message="Subject not found or not authorized.",
    )


@router.get("/subjects/{subject_id}/evolution")
def build_evolution_report(
    subject_id: str,
    start_date: str,
    end_date: str,
    current_user: UserRecord = Depends(get_current_user),
    statistics: StatisticsService = Depends(get_statistics_service),
):
    """Return JSON volume/surface comparison for one subject across time."""
    result = statistics.evolution_report_for_subject(
        current_user,
        subject_id,
        start_date=start_date,
        end_date=end_date,
    )
    return unwrap_result(
        result,
        not_found_message="Subject not found or not enough metric-ready dates.",
    )

@router.get("/subjects/{subject_id}/evolution/visual")
def build_evolution_visual(
    subject_id: str,
    start_date: str,
    end_date: str,
    target_date: str | None = None,
    tissues: list[str] | None = Query(default=None),
    comparison_method: str = "pve",
    pve_threshold: float = 0.2,
    distance_threshold_mm: float = 1.0,
    baseline_color: str = "#508cff",
    target_color: str = "#b9c4d2",
    changed_color: str = "#ff2d2d",
    include_changed_wireframe: bool = False,
    marching_cubes_step_size: int = 1,
    wireframe_step_size: int | None = 3,
    current_user: UserRecord = Depends(get_current_user),
    statistics: StatisticsService = Depends(get_statistics_service),
):
    """Return an in-memory GLB comparing baseline and target PVE maps."""
    result = statistics.evolution_visual_for_subject(
        current_user,
        subject_id,
        start_date=start_date,
        end_date=end_date,
        target_date=target_date,
        tissues=tissues,
        comparison_method=comparison_method,
        pve_threshold=pve_threshold,
        distance_threshold_mm=distance_threshold_mm,
        baseline_color=baseline_color,
        target_color=target_color,
        changed_color=changed_color,
        include_changed_wireframe=include_changed_wireframe,
        marching_cubes_step_size=marching_cubes_step_size,
        wireframe_step_size=wireframe_step_size,
    )
    glb_bytes = unwrap_result(
        result,
        not_found_message="Subject not found or not enough visual-ready dates.",
    )
    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={
            "Content-Disposition": f'attachment; filename="{subject_id}_{start_date}_to_{target_date or end_date}_comparison.glb"'
        },
    )

