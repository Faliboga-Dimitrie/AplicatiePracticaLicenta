from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_access_service
from ..schemas import LoginRequest, LoginResponse
from ...access_control import AccessControlService

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    access: AccessControlService = Depends(get_access_service),
):
    result = access.authenticate(request.email, request.password)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)

    auth = result.data
    if auth is None or not auth.authenticated:
        return LoginResponse(authenticated=False)

    return LoginResponse(
        authenticated=True,
        user_id=auth.user_id,
        email=auth.email,
    )