from __future__ import annotations

from datetime import date
from pathlib import Path

from ...access_control import AccessControlService, DbResult, MriCaseRecord, UserRecord
from ...access_control.utils import UNSET


class CaseService:
    """
    Web-facing MRI case service.

    Case routes should not read MRI cases directly from the database, because a
    case belongs to a subject and subject access is what authorizes the user.
    This service keeps that rule in one place:

    - reading a case requires at least viewer access;
    - creating/updating/deleting a case requires at least editor access.

    Later, the preprocessing and mesh job services can also depend on this class
    before starting expensive work.
    """

    def __init__(self, access: AccessControlService):
        self.access = access

    def list_for_user(self, user: UserRecord) -> DbResult[list[MriCaseRecord]]:
        """Return all MRI cases belonging to subjects visible to this user."""
        result = self.access.list_accessible_subjects(
            user.id,
            include_cases=True,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not load authorized cases.")

        cases: list[MriCaseRecord] = []
        for subject_with_cases in result.data or []:
            cases.extend(subject_with_cases.cases)

        return DbResult.ok(cases)

    def list_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[list[MriCaseRecord]]:
        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role="viewer",
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.list_cases_for_subject(subject_id)

    def get_for_user(
        self,
        user: UserRecord,
        case_id: int,
        *,
        minimum_role: str = "viewer",
    ) -> DbResult[MriCaseRecord]:
        allowed = self._user_has_case_access(
            user,
            case_id,
            minimum_role=minimum_role,
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check case access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.get_mri_case(case_id)

    def get_first_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[MriCaseRecord]:
        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role="viewer",
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.get_first_mri_case_for_subject(subject_id)

    def get_by_subject_date(
        self,
        user: UserRecord,
        subject_id: str,
        acquisition_date: str | date,
        *,
        minimum_role: str = "viewer",
    ) -> DbResult[MriCaseRecord]:
        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role=minimum_role,
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        return self.access.get_mri_case_by_subject_date(subject_id, acquisition_date)

    def create_for_user(
        self,
        user: UserRecord,
        *,
        subject_id: str,
        acquisition_date: str | date,
        notes: str | None = None,
        status: str | None = "registered",
        source_raw_path: Path | None = None,
    ) -> DbResult[MriCaseRecord]:
        if source_raw_path is None:
            return DbResult.fail("source_raw_path is required until the upload endpoint is implemented.")

        allowed = self._user_has_subject_access(
            user,
            subject_id,
            minimum_role="editor",
        )
        if not allowed.success:
            return DbResult.fail(allowed.error or "Could not check subject access.")
        if not allowed.data:
            return DbResult.ok(None)

        duplicate = self.access.get_mri_case_by_subject_date(subject_id, acquisition_date)
        if not duplicate.success:
            return DbResult.fail(duplicate.error or "Could not check duplicate MRI case.")
        if duplicate.data is not None:
            return DbResult.fail("MRI case with this subject ID and acquisition date already exists.")

        return self.access.create_mri_case(
            subject_id=subject_id,
            acquisition_date=acquisition_date,
            notes=notes,
            status=status,
            source_raw_path=source_raw_path,
        )

    def update_for_user(
        self,
        user: UserRecord,
        case_id: int,
        *,
        new_acquisition_date: str | date | object = UNSET,
        notes: str | None | object = UNSET,
        status: str | None | object = UNSET,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_for_user(user, case_id, minimum_role="editor")
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before update.")
        if current.data is None:
            return DbResult.ok(None)

        result = self.access.update_mri_case_by_subject_date(
            current.data.subject_id,
            current.data.acquisition_date,
            new_acquisition_date=new_acquisition_date,
            notes=notes,
            status=status,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not update MRI case.")
        if not result.data:
            return DbResult.fail("No MRI case fields were changed.")

        refreshed_date = (
            new_acquisition_date
            if new_acquisition_date is not UNSET
            else current.data.acquisition_date
        )
        return self.access.get_mri_case_by_subject_date(
            current.data.subject_id,
            refreshed_date,
        )

    def update_by_subject_date_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        acquisition_date: str | date,
        *,
        new_acquisition_date: str | date | object = UNSET,
        notes: str | None | object = UNSET,
        status: str | None | object = UNSET,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_by_subject_date(
            user,
            subject_id,
            acquisition_date,
            minimum_role="editor",
        )
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before update.")
        if current.data is None:
            return DbResult.ok(None)

        return self.update_for_user(
            user,
            current.data.id,
            new_acquisition_date=new_acquisition_date,
            notes=notes,
            status=status,
        )

    def delete_for_user(
        self,
        user: UserRecord,
        case_id: int,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_for_user(user, case_id, minimum_role="editor")
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before delete.")
        if current.data is None:
            return DbResult.ok(None)

        result = self.access.delete_mri_case_by_subject_date(
            current.data.subject_id,
            current.data.acquisition_date,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not delete MRI case.")
        if not result.data:
            return DbResult.ok(None)

        return DbResult.ok(current.data)

    def delete_by_subject_date_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        acquisition_date: str | date,
    ) -> DbResult[MriCaseRecord]:
        current = self.get_by_subject_date(
            user,
            subject_id,
            acquisition_date,
            minimum_role="editor",
        )
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before delete.")
        if current.data is None:
            return DbResult.ok(None)

        return self.delete_for_user(user, current.data.id)

    def set_status_for_user(
        self,
        user: UserRecord,
        case_id: int,
        status: str,
        *,
        minimum_role: str = "editor",
    ) -> DbResult[MriCaseRecord]:
        """
        Update only the status of a case the user may edit.

        This is intentionally tolerant of setting the same status twice, because
        background jobs may retry a transition or restart after a previous run.
        """
        current = self.get_for_user(user, case_id, minimum_role=minimum_role)
        if not current.success:
            return DbResult.fail(current.error or "Could not load MRI case before status update.")
        if current.data is None:
            return DbResult.ok(None)

        if current.data.status == status:
            return DbResult.ok(current.data)

        result = self.access.update_mri_case_by_subject_date(
            current.data.subject_id,
            current.data.acquisition_date,
            status=status,
        )
        if not result.success:
            return DbResult.fail(result.error or "Could not update MRI case status.")

        refreshed = self.access.get_mri_case(current.data.id)
        if not refreshed.success:
            return DbResult.fail(refreshed.error or "Could not reload MRI case after status update.")

        return refreshed

    def _user_has_subject_access(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        minimum_role: str,
    ) -> DbResult[bool]:
        return self.access.user_has_subject_access(
            user.id,
            subject_id,
            minimum_role=minimum_role,
        )

    def _user_has_case_access(
        self,
        user: UserRecord,
        case_id: int,
        *,
        minimum_role: str,
    ) -> DbResult[bool]:
        return self.access.user_has_case_access(
            user.id,
            case_id,
            minimum_role=minimum_role,
        )


__all__ = ["CaseService"]
