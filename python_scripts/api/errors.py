from __future__ import annotations

from typing import Any, NoReturn, Protocol, TypeVar, cast

from fastapi import HTTPException

T = TypeVar("T")


class ResultLike(Protocol[T]):
    success: bool
    data: T | None
    error: str | None


def error_code_for_status(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
    }.get(status_code, "API_ERROR")


def error_payload(
    message: str,
    *,
    code: str | None = None,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code or "API_ERROR",
            "message": message,
        }
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def normalize_error_detail(detail: Any, *, status_code: int) -> dict[str, Any]:
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        return detail

    if isinstance(detail, str):
        return error_payload(
            detail,
            code=error_code_for_status(status_code),
        )

    return error_payload(
        "Request failed.",
        code=error_code_for_status(status_code),
        details=detail,
    )


def raise_api_error(
    status_code: int,
    message: str,
    *,
    code: str | None = None,
    details: Any | None = None,
) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail=error_payload(
            message,
            code=code or error_code_for_status(status_code),
            details=details,
        ),
    )


def unwrap_result(
    result: ResultLike[T],
    *,
    not_found_message: str = "Resource not found.",
    bad_request_status: int = 400,
) -> T:
    if not result.success:
        raise_api_error(
            bad_request_status,
            result.error or "Operation failed.",
        )

    if result.data is None:
        raise_api_error(404, not_found_message, code="NOT_FOUND")

    return cast(T, result.data)


def unwrap_bool_result(
    result: ResultLike[bool],
    *,
    not_found_message: str = "Resource not found.",
) -> bool:
    if not result.success:
        raise_api_error(400, result.error or "Operation failed.")

    if not result.data:
        raise_api_error(404, not_found_message, code="NOT_FOUND")

    return True
