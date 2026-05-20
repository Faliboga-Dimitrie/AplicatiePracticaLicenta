from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...access_control import UserRecord
from ...access_control.services import AccessControlService
from ...access_control.utils import UNSET
from ..dependencies import get_access_service, get_current_user, get_subject_service
from ..errors import unwrap_bool_result, unwrap_result
from ..schemas import (
    AuthorizedSubjectResponse,
    CreateSubjectRequest,
    MriCaseResponse,
    UpdateSubjectRequest,
)
from ..serialization import mri_case_to_dict, subject_to_dict, subject_with_cases_to_dict
from ..services import SubjectService

router = APIRouter()


@router.get("", response_model=list[AuthorizedSubjectResponse])
def list_subjects(
    current_user: UserRecord = Depends(get_current_user),
    subjects: SubjectService = Depends(get_subject_service),
):
    """
    React-facing endpoint.

    Return only the subjects the logged-in user is allowed to see. The router
    does not know how authorization works; it asks SubjectService for the
    current user's visible subjects.
    """
    result = subjects.list_for_user(current_user, include_cases=True)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or "Could not load subjects.")

    return [
        subject_with_cases_to_dict(subject_with_cases, include_cases=False)
        for subject_with_cases in result.data or []
    ]


@router.get("/{subject_id}", response_model=AuthorizedSubjectResponse)
def get_subject(
    subject_id: str,
    current_user: UserRecord = Depends(get_current_user),
    subjects: SubjectService = Depends(get_subject_service),
):
    """
    React-facing endpoint.

    Return one subject, including its MRI cases, but only if the logged-in user
    has access to that subject.
    """
    result = subjects.get_for_user(current_user, subject_id, include_cases=True)
    subject_with_cases = unwrap_result(
        result,
        not_found_message="Subject not found or not authorized.",
    )
    return subject_with_cases_to_dict(subject_with_cases, include_cases=True)


@router.get("/{subject_id}/cases", response_model=list[MriCaseResponse])
def list_subject_cases(
    subject_id: str,
    current_user: UserRecord = Depends(get_current_user),
    subjects: SubjectService = Depends(get_subject_service),
):
    """
    React-facing endpoint.

    Used after the user selects a subject in the UI. It returns the cases for
    that subject only if the user has at least viewer access.
    """
    result = subjects.list_cases_for_subject(current_user, subject_id)
    cases = unwrap_result(
        result,
        not_found_message="Subject not found or not authorized.",
    )
    return [mri_case_to_dict(case) for case in cases]


# -----------------------------------------------------------------------------
# User-facing subject creation + temporary admin/test update/delete
# -----------------------------------------------------------------------------

@router.post("", response_model=AuthorizedSubjectResponse)
def create_subject(
    request: CreateSubjectRequest,
    current_user: UserRecord = Depends(get_current_user),
    subjects: SubjectService = Depends(get_subject_service),
):
    """
    React-facing endpoint.

    Create a new subject and immediately grant the logged-in user owner access.
    Without this subject_access row, the newly created subject would not appear
    in GET /subjects for the same user.
    """
    result = subjects.create_for_user(
        current_user,
        subject_id=request.subject_id,
        name=request.name,
        age=request.age,
        notes=request.notes,
    )
    subject_with_cases = unwrap_result(result, not_found_message="Subject could not be created.")
    return subject_with_cases_to_dict(subject_with_cases, include_cases=True)


@router.put("/{subject_id}")
def update_subject(
    subject_id: str,
    request: UpdateSubjectRequest,
    access: AccessControlService = Depends(get_access_service),
):
    """Temporary test/admin endpoint."""
    payload = request.model_dump(exclude_unset=True)

    result = access.update_subject(
        subject_id,
        name=payload.get("name", UNSET),
        age=payload.get("age", UNSET),
        notes=payload.get("notes", UNSET),
    )

    unwrap_bool_result(result, not_found_message="Subject not found or nothing changed.")

    refreshed = access.get_subject(subject_id)
    subject = unwrap_result(refreshed, not_found_message="Subject not found after update.")

    return {
        "updated": True,
        "subject": subject_to_dict(subject),
    }


@router.delete("/{subject_id}")
def delete_subject(
    subject_id: str,
    access: AccessControlService = Depends(get_access_service),
):
    """
    Temporary test/admin endpoint.

    This may also delete filesystem workspaces through AccessControlService's
    workspace gateway.
    """
    result = access.delete_subject(subject_id)

    unwrap_bool_result(result, not_found_message="Subject not found.")

    return {
        "deleted": True,
        "subject_id": subject_id,
    }
