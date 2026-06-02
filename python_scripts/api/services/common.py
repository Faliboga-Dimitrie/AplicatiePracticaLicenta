from __future__ import annotations

from typing import TYPE_CHECKING

from ...access_control import UserRecord
from .jobs import JobContext

if TYPE_CHECKING:
    from .cases import CaseService


def require_not_cancelled(context: JobContext, message: str) -> None:
    """Raise a RuntimeError when a user has requested job cancellation."""
    if context.cancel_requested:
        raise RuntimeError(message)


def mark_case_status_best_effort(
    *,
    cases: "CaseService",
    user: UserRecord,
    case_id: int,
    status: str,
) -> None:
    """
    Try to update a case status without hiding the original job exception.

    Preprocessing and mesh analysis both need this in their exception handlers:
    the job failure should remain the main error, while the status update is only
    a best-effort cleanup step.
    """
    try:
        cases.set_status_for_user(
            user,
            case_id,
            status,
        )
    except Exception:
        pass


__all__ = ["mark_case_status_best_effort", "require_not_cancelled"]
