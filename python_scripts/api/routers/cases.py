from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...access_control import UserRecord
from ...access_control.utils import UNSET
from ..dependencies import get_case_service, get_current_user
from ..errors import raise_api_error, unwrap_result
from ..schemas import CreateMriCaseRequest, MriCaseResponse, UpdateMriCaseRequest
from ..serialization import mri_case_to_dict
from ..services import CaseService

router = APIRouter()


@router.get("", response_model=list[MriCaseResponse])
def list_cases(
    subject_id: str | None = None,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    """
    React-facing endpoint.

    Without subject_id, return all cases belonging to subjects visible to the
    logged-in user. With subject_id, return cases only for that authorized
    subject.
    """
    if subject_id is None:
        result = cases.list_for_user(current_user)
    else:
        result = cases.list_for_subject(current_user, subject_id)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Could not load MRI cases.")
    if result.data is None:
        raise HTTPException(status_code=404, detail="Subject not found or not authorized.")

    return [mri_case_to_dict(case) for case in result.data]


@router.post("")
def create_case(
    request: CreateMriCaseRequest,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    """
    Create a case for a subject the logged-in user can edit.

    This server-side-path endpoint is useful for backend tests and scripts.
    React should usually use POST /cases/upload instead, because browsers send
    file bytes instead of local Windows/Linux paths.
    """
    result = cases.create_for_user(
        current_user,
        subject_id=request.subject_id,
        acquisition_date=request.acquisition_date,
        notes=request.notes,
        status=request.status,
        source_raw_path=request.source_raw_path,
    )

    case = unwrap_result(
        result,
        not_found_message="Subject not found or not enough permissions to create a case.",
    )

    return {
        "created": True,
        "case": mri_case_to_dict(case),
    }


def _safe_upload_filename(filename: str | None) -> str:
    name = Path(filename or "raw_mri.nii.gz").name.strip()
    if not name:
        name = "raw_mri.nii.gz"

    lower = name.lower()
    if not (lower.endswith(".nii") or lower.endswith(".nii.gz")):
        raise_api_error(
            400,
            "Raw MRI upload must be a NIfTI file ending in .nii or .nii.gz.",
            code="INVALID_UPLOAD_FILE",
        )

    return name


@router.post("/upload")
def create_case_with_upload(
    subject_id: str = Form(...),
    acquisition_date: date = Form(...),
    notes: str | None = Form(None),
    status: str | None = Form("registered"),
    file: UploadFile = File(...),
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    """Create an MRI case from a browser multipart upload.

    React sends file bytes here, not a local filesystem path. The API writes the
    upload to a temporary file, then reuses CaseService.create_for_user so the
    same authorization, duplicate-date check and workspace-copy logic still run.
    """
    filename = _safe_upload_filename(file.filename)

    with tempfile.TemporaryDirectory(prefix="mri_api_upload_") as tmpdir:
        temp_path = Path(tmpdir) / filename
        with temp_path.open("wb") as target:
            file.file.seek(0)
            shutil.copyfileobj(file.file, target)

        result = cases.create_for_user(
            current_user,
            subject_id=subject_id,
            acquisition_date=acquisition_date,
            notes=notes,
            status=status,
            source_raw_path=temp_path,
        )

    case = unwrap_result(
        result,
        not_found_message="Subject not found or not enough permissions to create a case.",
    )

    return {
        "created": True,
        "case": mri_case_to_dict(case),
    }

@router.get("/by-subject/{subject_id}", response_model=MriCaseResponse)
def get_first_case_for_subject(
    subject_id: str,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    result = cases.get_first_for_subject(current_user, subject_id)
    case = unwrap_result(
        result,
        not_found_message="MRI case not found or not authorized.",
    )
    return mri_case_to_dict(case)


@router.get("/by-subject-date/{subject_id}/{acquisition_date}", response_model=MriCaseResponse)
def get_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    result = cases.get_by_subject_date(
        current_user,
        subject_id,
        acquisition_date,
    )

    case = unwrap_result(
        result,
        not_found_message="MRI case not found or not authorized.",
    )
    return mri_case_to_dict(case)


@router.put("/by-subject-date/{subject_id}/{acquisition_date}")
def update_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    request: UpdateMriCaseRequest,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    payload = request.model_dump(exclude_unset=True)

    result = cases.update_by_subject_date_for_user(
        current_user,
        subject_id,
        acquisition_date,
        new_acquisition_date=payload.get("acquisition_date", UNSET),
        notes=payload.get("notes", UNSET),
        status=payload.get("status", UNSET),
    )

    case = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to update it.",
    )

    return {
        "updated": True,
        "case": mri_case_to_dict(case),
    }


@router.delete("/by-subject-date/{subject_id}/{acquisition_date}")
def delete_case_by_subject_date(
    subject_id: str,
    acquisition_date: str,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    result = cases.delete_by_subject_date_for_user(
        current_user,
        subject_id,
        acquisition_date,
    )

    deleted_case = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to delete it.",
    )

    return {
        "deleted": True,
        "case": mri_case_to_dict(deleted_case),
    }


@router.get("/{case_id}", response_model=MriCaseResponse)
def get_case(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    """Return one MRI case by database id, but only if the user can view it."""
    result = cases.get_for_user(current_user, case_id)
    case = unwrap_result(
        result,
        not_found_message="MRI case not found or not authorized.",
    )
    return mri_case_to_dict(case)


@router.put("/{case_id}")
def update_case(
    case_id: int,
    request: UpdateMriCaseRequest,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    """Update one MRI case by database id, but only if the user can edit it."""
    payload = request.model_dump(exclude_unset=True)

    result = cases.update_for_user(
        current_user,
        case_id,
        new_acquisition_date=payload.get("acquisition_date", UNSET),
        notes=payload.get("notes", UNSET),
        status=payload.get("status", UNSET),
    )

    case = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to update it.",
    )

    return {
        "updated": True,
        "case": mri_case_to_dict(case),
    }


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    current_user: UserRecord = Depends(get_current_user),
    cases: CaseService = Depends(get_case_service),
):
    """Delete one MRI case by database id, including its filesystem workspace."""
    result = cases.delete_for_user(current_user, case_id)

    deleted_case = unwrap_result(
        result,
        not_found_message="MRI case not found or not enough permissions to delete it.",
    )

    return {
        "deleted": True,
        "case": mri_case_to_dict(deleted_case),
    }
