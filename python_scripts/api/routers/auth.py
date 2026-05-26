from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request, Response, status

from ...access_control import UserRecord
from ..dependencies import get_auth_service, get_current_user
from ..errors import raise_api_error
from ..schemas import CurrentUserResponse, LoginRequest, LoginResponse, RegisterRequest, UserResponse
from ..services import AuthService

router = APIRouter()

REFRESH_TOKEN_COOKIE = "mri_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/auth"
REFRESH_TOKEN_COOKIE_SAMESITE = os.getenv("MRI_API_REFRESH_COOKIE_SAMESITE", "lax").lower()
if REFRESH_TOKEN_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    REFRESH_TOKEN_COOKIE_SAMESITE = "lax"
REFRESH_TOKEN_COOKIE_SECURE = os.getenv("MRI_API_REFRESH_COOKIE_SECURE", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def user_response(user: UserRecord) -> UserResponse:
    return UserResponse(id=user.id, email=user.email)


def _set_refresh_cookie(response: Response, auth: AuthService, refresh_token: str | None) -> None:
    if not refresh_token:
        return

    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        max_age=auth.token_service.refresh_token_max_age_seconds,
        httponly=True,
        secure=REFRESH_TOKEN_COOKIE_SECURE,
        samesite=REFRESH_TOKEN_COOKIE_SAMESITE,  # type: ignore[arg-type]
        path=REFRESH_TOKEN_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_COOKIE_PATH,
        samesite=REFRESH_TOKEN_COOKIE_SAMESITE,  # type: ignore[arg-type]
    )


def _session_response(session) -> LoginResponse:
    return LoginResponse(
        access_token=session.access_token,
        token_type=session.token_type,
        expires_at=session.expires_at,
        user=user_response(session.user),
    )


@router.post("/register", response_model=LoginResponse)
def register(
    request: RegisterRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
):
    result = auth.register(request.email, request.password)

    if not result.success:
        detail = result.error or "Could not create account."
        status_code = status.HTTP_409_CONFLICT if "Duplicate" in detail or "duplicate" in detail or "UNIQUE" in detail else status.HTTP_400_BAD_REQUEST
        raise_api_error(
            status_code,
            detail,
            code="REGISTER_FAILED",
        )

    session = result.data
    if session is None:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "Could not create account.",
            code="REGISTER_FAILED",
        )

    _set_refresh_cookie(response, auth, session.refresh_token)
    return _session_response(session)


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
):
    result = auth.login(request.email, request.password)

    if not result.success:
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            result.error or "Authentication failed.",
            code="AUTHENTICATION_FAILED",
        )

    session = result.data
    if session is None:
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password.",
            code="INVALID_CREDENTIALS",
        )

    _set_refresh_cookie(response, auth, session.refresh_token)
    return _session_response(session)


@router.post("/refresh", response_model=LoginResponse)
def refresh(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
):
    """
    Rotate the refresh token and return a new access token.

    React should call this after a normal API request receives 401. The refresh
    token is read from an HttpOnly cookie, not from JavaScript-visible storage.
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    result = auth.refresh(refresh_token)

    if not result.success:
        _clear_refresh_cookie(response)
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            result.error or "Could not refresh session.",
            code="REFRESH_FAILED",
        )

    session = result.data
    if session is None:
        _clear_refresh_cookie(response)
        raise_api_error(
            status.HTTP_401_UNAUTHORIZED,
            "Refresh session is missing, expired, revoked, or invalid.",
            code="INVALID_REFRESH_SESSION",
        )

    _set_refresh_cookie(response, auth, session.refresh_token)
    return _session_response(session)


@router.get("/me", response_model=CurrentUserResponse)
def me(
    current_user: UserRecord = Depends(get_current_user),
):
    return CurrentUserResponse(user=user_response(current_user))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
):
    """
    Revoke the current refresh session and clear the refresh cookie.

    React should also delete its access token from memory/localStorage.
    """
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    result = auth.logout(refresh_token)
    _clear_refresh_cookie(response)

    if not result.success:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            result.error or "Could not log out.",
            code="LOGOUT_FAILED",
        )

    return {"logged_out": True}


@router.post("/logout-all")
def logout_all(
    response: Response,
    current_user: UserRecord = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
):
    """
    Revoke all refresh sessions for the logged-in user.

    This is useful for a future "log out from all devices" button.
    """
    result = auth.logout_all(current_user)
    _clear_refresh_cookie(response)

    if not result.success:
        raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            result.error or "Could not log out from all sessions.",
            code="LOGOUT_ALL_FAILED",
        )

    return {"logged_out": True, "all_sessions": True}
