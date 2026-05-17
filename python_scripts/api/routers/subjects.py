from __future__ import annotations

from fastapi import APIRouter, Depends

from ...access_control.services import AccessControlService
from ...access_control.utils import UNSET
from ..dependencies import get_access_service
from ..errors import unwrap_bool_result, unwrap_result
from ..schemas import CreateSubjectRequest, UpdateSubjectRequest
from ..serialization import subject_to_dict

router = APIRouter()


@router.get("")
def list_subjects(
    access: AccessControlService = Depends(get_access_service),
):
    result = access.subjects.list_all()

    if not result.success:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=result.error)

    return [subject_to_dict(subject) for subject in result.data or []]


@router.post("")
def create_subject(
    request: CreateSubjectRequest,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.create_subject(
        request.subject_id,
        name=request.name,
        age=request.age,
        notes=request.notes,
    )
    subject = unwrap_result(result)
    return subject_to_dict(subject)


@router.get("/{subject_id}")
def get_subject(
    subject_id: str,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_subject(subject_id)
    subject = unwrap_result(result, not_found_message="Subject not found.")
    return subject_to_dict(subject)


@router.put("/{subject_id}")
def update_subject(
    subject_id: str,
    request: UpdateSubjectRequest,
    access: AccessControlService = Depends(get_access_service),
):
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
    If delete_workspaces=true, this should also delete all filesystem workspaces
    for this subject's MRI cases.
    """
    result = access.delete_subject(subject_id)

    unwrap_bool_result(result, not_found_message="Subject not found.")

    return {
        "deleted": True,
        "subject_id": subject_id,
    }