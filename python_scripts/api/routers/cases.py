from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...access_control.services import AccessControlService
from ...access_control.utils import UNSET
from ..dependencies import get_access_service
from ..errors import unwrap_bool_result, unwrap_result
from ..schemas import CreateMriCaseRequest, UpdateMriCaseRequest
from ..serialization import mri_case_to_dict

router = APIRouter()


@router.get("")
def list_cases(
    subject_id: str | None = None,
    access: AccessControlService = Depends(get_access_service),
):
    """
    Test/admin endpoint.

    If subject_id is given, this uses the service method.
    Without subject_id, it queries all MRI cases directly for testing.
    Later, move full list_cases() into AccessControlService.
    """
    if subject_id is not None:
        result = access.list_cases_for_subject(subject_id)

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        return [mri_case_to_dict(case) for case in result.data or []]

    try:
        rows = access.db.fetch_all(
            """
            SELECT id, subject_id, acquisition_date, notes, status
            FROM mri_case
            ORDER BY subject_id, acquisition_date
            """
        )
        return rows
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("")
def create_case(
    request: CreateMriCaseRequest,
    access: AccessControlService = Depends(get_access_service),
):
    if request.source_raw_path is None:
        raise HTTPException(
            status_code=400,
            detail="source_raw_path is required.",
        )

    duplicate_check = access.get_mri_case_by_subject_date(
        request.subject_id,
        request.acquisition_date,
    )
    if duplicate_check.success and duplicate_check.data is not None:
        raise HTTPException(
            status_code=400,
            detail="MRI case with this subject ID and acquisition date already exists.",
        )

    result = access.create_mri_case(
        subject_id=request.subject_id,
        acquisition_date=request.acquisition_date,
        notes=request.notes,
        status=request.status,
        source_raw_path=request.source_raw_path,
    )

    case = unwrap_result(result)

    return {
        "created": True,
        "case": mri_case_to_dict(case),
    }


@router.get("/by-subject/{subject_id}")
def get_case(
    subject_id: str,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_first_mri_case_for_subject(subject_id)

    case = unwrap_result(result, not_found_message="MRI case not found.")
    return mri_case_to_dict(case)


@router.get("/by-subject-date/{subject_id}/{acquisition_date}")
def get_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_mri_case_by_subject_date(
        subject_id,
        acquisition_date,
    )

    case = unwrap_result(result, not_found_message="MRI case not found.")
    return mri_case_to_dict(case)


@router.put("/subjects/{subject_id}/cases/{acquisition_date}")
def update_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    request: UpdateMriCaseRequest,
    access: AccessControlService = Depends(get_access_service),
):
    payload = request.model_dump(exclude_unset=True)

    result = access.update_mri_case_by_subject_date(
        subject_id,
        acquisition_date,
        new_acquisition_date=payload.get("acquisition_date", UNSET),
        notes=payload.get("notes", UNSET),
        status=payload.get("status", UNSET),
    )

    unwrap_bool_result(
        result,
        not_found_message="MRI case not found or nothing changed.",
    )

    refreshed_date = payload.get("acquisition_date", acquisition_date)

    refreshed = access.get_mri_case_by_subject_date(
        subject_id,
        refreshed_date,
    )

    case = unwrap_result(
        refreshed,
        not_found_message="MRI case not found after update.",
    )

    return {
        "updated": True,
        "case": mri_case_to_dict(case),
    }


@router.delete("/by-subject-date/{subject_id}/{acquisition_date}")
def delete_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.delete_mri_case_by_subject_date(
        subject_id,
        acquisition_date,
    )

    unwrap_bool_result(result, not_found_message="MRI case not found.")

    return {
        "deleted": True,
        "subject_id": subject_id,
        "acquisition_date": acquisition_date,
    }