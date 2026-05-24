from __future__ import annotations

from ...access_control import (
    AccessControlService,
    DbResult,
    MriCaseRecord,
    SubjectRecord,
    SubjectSummaryRecord,
    SubjectWithCases,
    UserRecord,
)
from ...access_control.utils import UNSET


class SubjectService:
    """
    Web-facing subject service.

    The API should not list every subject from the database. For the React UI,
    subjects are always loaded through the authenticated user, so authorization
    stays in one place instead of being repeated in every router function.
    """

    def __init__(self, access: AccessControlService):
        self.access = access


    def list_summaries_for_user(
        self,
        user: UserRecord,
    ) -> DbResult[list[SubjectSummaryRecord]]:
        """
        Lightweight subject list for React.

        This returns one row per visible subject, with case_count computed by SQL,
        instead of loading all cases and then dropping them from the response.
        """
        return self.access.list_accessible_subject_summaries(user.id)

    def list_for_user(
        self,
        user: UserRecord,
        *,
        include_cases: bool = True,
    ) -> DbResult[list[SubjectWithCases]]:
        return self.access.list_accessible_subjects(
            user.id,
            include_cases=include_cases,
        )

    def get_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        include_cases: bool = True,
    ) -> DbResult[SubjectWithCases]:
        result = self.access.search_by_subject_id(
            user.id,
            subject_id,
            include_cases=include_cases,
        )

        if not result.success:
            return DbResult.fail(result.error or "Could not load authorized subject.")

        subjects = result.data or []
        if not subjects:
            return DbResult.ok(None)

        return DbResult.ok(subjects[0])


    def get_subject(
        self,
        subject_id: str,
    ) -> DbResult[SubjectRecord]:
        return self.access.get_subject(subject_id)

    def update_subject(
        self,
        subject_id: str,
        *,
        name: str | None | object = UNSET,
        age: int | None | object = UNSET,
        notes: str | None | object = UNSET,
    ) -> DbResult[bool]:
        return self.access.update_subject(
            subject_id,
            name=name,
            age=age,
            notes=notes,
        )
    
    def update_subject_for_user(
        self,
        user: UserRecord,
        subject_id: str,
        *,
        name: str | None | object = UNSET,
        age: int | None | object = UNSET,
        notes: str | None | object = UNSET,
    ) -> DbResult[bool]:
        """
        Update subject metadata, but only if the user has access to that subject.

        This is the user-facing alternative to the old admin/test CRUD route. The
        important rule is that the same operation updates the subject row and
        checks the subject_access row, otherwise a user would be able to update
        subjects they don't have access to by guessing their IDs.
        """
        return self.access.update_subject_for_user(
            user.id,
            subject_id,
            name=name,
            age=age,
            notes=notes,
        )

    def delete_for_user(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[bool]:
        return self.access.delete_subject_for_user(user.id, subject_id)

    def list_cases_for_subject(
        self,
        user: UserRecord,
        subject_id: str,
    ) -> DbResult[list[MriCaseRecord]]:
        result = self.get_for_user(
            user,
            subject_id,
            include_cases=True,
        )

        if not result.success:
            return DbResult.fail(result.error or "Could not load subject cases.")
        if result.data is None:
            return DbResult.ok(None)

        return DbResult.ok(list(result.data.cases))

    def create_for_user(
        self,
        user: UserRecord,
        *,
        subject_id: str,
        name: str | None = None,
        age: int | None = None,
        notes: str | None = None,
        owner_role: str = "owner",
    ) -> DbResult[SubjectWithCases]:
        """
        Create a subject from the normal web UI and give the creator access.

        This is the user-facing alternative to the old admin/test CRUD route. The
        important rule is that the same operation creates the subject row and the
        subject_access row, otherwise the creator would not see the subject when
        React calls GET /subjects.
        """
        existing = self.access.get_subject(subject_id)
        if not existing.success:
            return DbResult.fail(existing.error or "Could not check whether subject exists.")

        if existing.data is not None:
            access = self.access.get_subject_access(user.id, subject_id)
            if not access.success:
                return DbResult.fail(access.error or "Could not check existing subject access.")
            if access.data is not None:
                return DbResult.fail("Subject already exists and is already visible to this user.")
            return DbResult.fail("Subject already exists. Ask an administrator to grant access instead of claiming it from the UI.")

        created = self.access.create_subject(
            subject_id,
            name=name,
            age=age,
            notes=notes,
        )
        if not created.success:
            return DbResult.fail(created.error or "Could not create subject.")
        if created.data is None:
            return DbResult.fail("Could not create subject.")

        granted = self.access.grant_subject_access(
            user.id,
            created.data.id,
            role=owner_role,
        )
        if not granted.success:
            # Best-effort rollback: the subject has no cases yet because it was
            # just created through this endpoint. If rollback fails, keep the
            # original error because that is what broke the user flow.
            self.access.delete_subject(created.data.id)
            return DbResult.fail(granted.error or "Subject was created, but access could not be granted.")

        return self.get_for_user(user, created.data.id, include_cases=True)


__all__ = ["SubjectService"]
