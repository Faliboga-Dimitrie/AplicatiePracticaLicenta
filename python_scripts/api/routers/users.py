from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...access_control.services import AccessControlService
from ..dependencies import get_access_service
from ..errors import unwrap_bool_result, unwrap_result
from ..schemas import CreateUserRequest, UpdateUserRequest
from ..serialization import user_to_dict

router = APIRouter()


@router.get("")
def list_users(
    access: AccessControlService = Depends(get_access_service),
):
    """
    Test/admin endpoint.

    Your service does not currently expose list_users(), so for testing we query
    the DB directly here. Later, move this into AccessControlService.
    """
    try:
        rows = access.db.fetch_all("SELECT id, email FROM app_user ORDER BY id")
        return rows
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("")
def create_user(
    request: CreateUserRequest,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.create_user(request.email, request.password)
    user = unwrap_result(result)
    return user_to_dict(user)


@router.get("/by-email/{email}")
def get_user_by_email(
    email: str,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_user_by_email(email)
    user = unwrap_result(result, not_found_message="User not found.")
    return user_to_dict(user)


@router.get("/{user_id}")
def get_user(
    user_id: int,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.get_user_by_id(user_id)
    user = unwrap_result(result, not_found_message="User not found.")
    return user_to_dict(user)


@router.put("/{user_id}")
def update_user(
    user_id: int,
    request: UpdateUserRequest,
    access: AccessControlService = Depends(get_access_service),
):
    changed: dict[str, bool] = {}

    if request.email is not None:
        result = access.update_user_email(user_id, request.email)
        unwrap_bool_result(result, not_found_message="User not found.")
        changed["email"] = True

    if request.password is not None:
        result = access.update_user_password(user_id, request.password)
        unwrap_bool_result(result, not_found_message="User not found.")
        changed["password"] = True

    if not changed:
        raise HTTPException(
            status_code=400,
            detail="Nothing to update. Send email and/or password.",
        )

    refreshed = access.get_user_by_id(user_id)
    user = unwrap_result(refreshed, not_found_message="User not found after update.")

    return {
        "updated": True,
        "changed": changed,
        "user": user_to_dict(user),
    }


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.delete_user(user_id)
    unwrap_bool_result(result, not_found_message="User not found.")

    return {
        "deleted": True,
        "user_id": user_id,
    }