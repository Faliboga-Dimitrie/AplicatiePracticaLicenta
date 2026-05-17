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
    include_workspace: bool = False,
    access: AccessControlService = Depends(get_access_service),
):
    """
    Test/admin endpoint.

    If subject_id is given, this uses the service method.
    Without subject_id, it queries all MRI cases directly for testing.
    Later, move full list_cases() into AccessControlService.
    """
    if subject_id is not None:
        result = access.list_cases_for_subject(
            subject_id,
            include_workspace=include_workspace,
        )

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


@router.get("/{case_id}")
def get_case(
    case_id: int,
    include_workspace: bool = True,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_mri_case(
        case_id,
        include_workspace=include_workspace,
    )

    case = unwrap_result(result, not_found_message="MRI case not found.")
    return mri_case_to_dict(case)


@router.get("/by-subject-date/{subject_id}/{acquisition_date}")
def get_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    include_workspace: bool = True,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_mri_case_by_subject_date(
        subject_id,
        acquisition_date,
        include_workspace=include_workspace,
    )

    case = unwrap_result(result, not_found_message="MRI case not found.")
    return mri_case_to_dict(case)


@router.put("/{case_id}")
def update_case(
    case_id: int,
    request: UpdateMriCaseRequest,
    access: AccessControlService = Depends(get_access_service),
):
    payload = request.model_dump(exclude_unset=True)

    result = access.update_mri_case(
        case_id,
        acquisition_date=payload.get("acquisition_date", UNSET),
        notes=payload.get("notes", UNSET),
        status=payload.get("status", UNSET),
    )

    unwrap_bool_result(result, not_found_message="MRI case not found or nothing changed.")

    refreshed = access.get_mri_case(case_id, include_workspace=True)
    case = unwrap_result(refreshed, not_found_message="MRI case not found after update.")

    return {
        "updated": True,
        "warning": (
            "This updates the database only. If you changed acquisition_date, "
            "the filesystem workspace folders are not automatically renamed."
        ),
        "case": mri_case_to_dict(case),
    }


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    access: AccessControlService = Depends(get_access_service),
):
    """
    If delete_workspace=true, this should also delete the filesystem workspace
    for this MRI case.
    """
    result = access.delete_mri_case(case_id)

    unwrap_bool_result(result, not_found_message="MRI case not found.")

    return {
        "deleted": True,
        "case_id": case_id,
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