from fastapi import APIRouter, Depends, HTTPException, status

from ...access_control import UserRecord
from ..dependencies import get_auth_service, get_current_user
from ..schemas import CurrentUserResponse, LoginRequest, LoginResponse, UserResponse
from ..services import AuthService

router = APIRouter()


def user_response(user: UserRecord) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
):
    result = auth.login(request.email, request.password)

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "Authentication failed.",
        )

    session = result.data
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return LoginResponse(
        access_token=session.access_token,
        token_type=session.token_type,
        expires_at=session.expires_at,
        user=user_response(session.user),
    )


@router.get("/me", response_model=CurrentUserResponse)
def me(
    current_user: UserRecord = Depends(get_current_user),
):
    return CurrentUserResponse(user=user_response(current_user))


@router.post("/logout")
def logout():
    """
    Stateless logout.

    Since the backend does not store sessions, React logs out by deleting the
    token from browser state/storage.
    """
    return {"logged_out": True}
