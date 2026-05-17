from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def unwrap_result(
    result: Any,
    *,
    not_found_message: str = "Resource not found.",
    bad_request_status: int = 400,
):
    if not result.success:
        raise HTTPException(
            status_code=bad_request_status,
            detail=result.error or "Operation failed.",
        )

    if result.data is None:
        raise HTTPException(status_code=404, detail=not_found_message)

    return result.data


def unwrap_bool_result(
    result: Any,
    *,
    not_found_message: str = "Resource not found.",
):
    if not result.success:
        raise HTTPException(
            status_code=400,
            detail=result.error or "Operation failed.",
        )

    if not result.data:
        raise HTTPException(status_code=404, detail=not_found_message)

    return True