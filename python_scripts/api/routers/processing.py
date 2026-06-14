from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from ...access_control import UserRecord
from ..dependencies import (
    get_current_user,
    get_full_processing_service,
    get_statistics_service,
)
from ..errors import raise_api_error, unwrap_result
from ..schemas import JobResponse
from ..serialization import job_to_dict
from ..services import FullProcessingService, StatisticsService

router = APIRouter()


@router.post("/cases/{case_id}/processing-jobs", response_model=JobResponse)
def start_processing_job(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    processing: FullProcessingService = Depends(get_full_processing_service),
):
    """Start the complete user-facing MRI processing workflow for one case."""
    result = processing.start_for_case(current_user, case_id)
    if not result.success and result.error == processing.ACTIVE_JOB_MESSAGE:
        raise_api_error(409, result.error, code="ACTIVE_JOB_EXISTS")

    job = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to process it.",
    )
    return job_to_dict(job)


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
    changed_color: str = "#ff2d2d",
    marching_cubes_step_size: int = 1,
    visual_mode: str = "changed_unchanged",
    current_user: UserRecord = Depends(get_current_user),
    statistics: StatisticsService = Depends(get_statistics_service),
):
    """Return an in-memory GLB for one time-comparison visualization."""
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
        changed_color=changed_color,
        marching_cubes_step_size=marching_cubes_step_size,
        visual_mode=visual_mode,
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

