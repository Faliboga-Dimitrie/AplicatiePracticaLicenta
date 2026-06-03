from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...access_control import UserRecord
from ...access_control.utils import UNSET
from ..dependencies import get_case_service, get_current_user
from ..errors import raise_api_error, unwrap_result
from ..schemas import MriCaseResponse, UpdateMriCaseRequest
from ..serialization import mri_case_to_dict
from ..services import CaseService
from ..upload_validation import safe_nifti_upload_filename

router = APIRouter()


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
    try:
        filename = safe_nifti_upload_filename(file.filename, default="raw_mri.nii.gz")
    except ValueError as exc:
        raise_api_error(
            400,
            str(exc),
            code="INVALID_UPLOAD_FILE",
        )

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
