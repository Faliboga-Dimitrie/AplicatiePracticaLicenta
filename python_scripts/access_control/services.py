from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .config import DatabaseConfig
from .database import MySqlDatabase
from .models import MriCaseRecord, SubjectRecord, SubjectWithCases, UserRecord
from .password_hashing import PasswordHasher
from .repositories import (
    MriCaseRepository,
    SubjectAccessRepository,
    SubjectRepository,
    SubjectSearchRepository,
    UserRepository,
)
from .results import AuthResult, DbResult
from .roles import ROLE_LEVELS, is_known_role, role_allows
from .schema import SchemaManager
from .utils import (
    UNSET,
    date_from_db,
    is_valid_email,
    normalize_date,
    normalize_email,
    normalize_required_text,
)
from .workspace_gateway import WorkspaceGateway


class AccessControlService:
    """
    Authentication, authorization, and metadata service for the MRI application.

    Responsibilities:
    - ensure the MySQL database/schema exists;
    - CRUD for users, subjects, MRI cases, and subject access;
    - authenticate users by email/password;
    - authorize access to subjects/cases;
    - search only within the subjects a user is allowed to access.

    The API layer should decide how to handle sessions, HTTP errors, and UI state.
    """

    def __init__(
        self,
        config: DatabaseConfig,
        *,
        password_hasher: PasswordHasher | None = None,
        workspace_gateway: WorkspaceGateway | None = None,
    ):
        self.config = config
        self.password_hasher = password_hasher or PasswordHasher()
        self.workspace_gateway = workspace_gateway

        self.db = MySqlDatabase(config)
        self.schema = SchemaManager(self.db, config)
        self.users = UserRepository(self.db)
        self.subjects = SubjectRepository(self.db)
        self.cases = MriCaseRepository(self.db)
        self.access = SubjectAccessRepository(self.db)
        self.search = SubjectSearchRepository(self.db)

    # ------------------------------------------------------------------
    # database/schema setup
    # ------------------------------------------------------------------

    def ensure_storage(self) -> DbResult[bool]:
        """Create the database and tables if they do not already exist."""
        return self.schema.ensure_storage()

    # ------------------------------------------------------------------
    # user CRUD + authentication
    # ------------------------------------------------------------------

    def create_user(self, email: str, password: str) -> DbResult[UserRecord]:
        email = normalize_email(email)
        if not is_valid_email(email):
            return DbResult.fail("Invalid email address.")

        try:
            password_hash = self.password_hasher.hash_password(password)
        except Exception as exc:
            return DbResult.fail(str(exc))

        return self.users.create(email, password_hash)

    def get_user_by_id(self, user_id: int) -> DbResult[UserRecord]:
        return self.users.get_by_id(user_id)

    def get_user_by_email(self, email: str) -> DbResult[UserRecord]:
        return self.users.get_by_email(normalize_email(email))

    def update_user_email(self, user_id: int, new_email: str) -> DbResult[bool]:
        new_email = normalize_email(new_email)
        if not is_valid_email(new_email):
            return DbResult.fail("Invalid email address.")
        return self.users.update_email(user_id, new_email)

    def update_user_password(self, user_id: int, new_password: str) -> DbResult[bool]:
        try:
            password_hash = self.password_hasher.hash_password(new_password)
        except Exception as exc:
            return DbResult.fail(str(exc))
        return self.users.update_password_hash(user_id, password_hash)

    def delete_user(self, user_id: int) -> DbResult[bool]:
        return self.users.delete(user_id)

    def authenticate(self, email: str, password: str) -> DbResult[AuthResult]:
        """Verify credentials. This does not create sessions or tokens."""
        credentials = self.users.get_credentials_by_email(normalize_email(email))
        if not credentials.success:
            return DbResult.fail(credentials.error or "Could not load user credentials.")
        if credentials.data is None:
            return DbResult.ok(AuthResult(authenticated=False))

        stored_hash = credentials.data.password_hash
        if not self.password_hasher.verify_password(password, stored_hash):
            return DbResult.ok(AuthResult(authenticated=False))

        if self.password_hasher.needs_rehash(stored_hash):
            new_hash = self.password_hasher.hash_password(password)
            self.users.update_password_hash(credentials.data.id, new_hash)

        return DbResult.ok(
            AuthResult(
                authenticated=True,
                user_id=credentials.data.id,
                email=credentials.data.email,
            )
        )

    # ------------------------------------------------------------------
    # subject CRUD
    # ------------------------------------------------------------------

    def create_subject(
        self,
        subject_id: str,
        *,
        name: str | None = None,
        age: int | None = None,
        notes: str | None = None,
    ) -> DbResult[SubjectRecord]:
        try:
            subject_id = normalize_required_text(subject_id, "subject_id")
        except Exception as exc:
            return DbResult.fail(str(exc))

        if age is not None and age < 0:
            return DbResult.fail("Subject age cannot be negative.")

        return self.subjects.create(subject_id, name=name, age=age, notes=notes)

    def get_subject(self, subject_id: str) -> DbResult[SubjectRecord]:
        return self.subjects.get(subject_id)

    def update_subject(
        self,
        subject_id: str,
        *,
        name: str | None | object = UNSET,
        age: int | None | object = UNSET,
        notes: str | None | object = UNSET,
    ) -> DbResult[bool]:
        if age is not UNSET and age is not None and int(age) < 0:
            return DbResult.fail("Subject age cannot be negative.")
        return self.subjects.update(subject_id, name=name, age=age, notes=notes)

    def delete_subject(self, subject_id: str) -> DbResult[bool]:
        try:
            result = self.subjects.delete(subject_id)

            if not result.success or not result.data:
                return result

            if self.workspace_gateway is None:
                    raise RuntimeError("delete_workspaces=True requires a workspace_gateway.")

            self.workspace_gateway.delete_subject_workspaces(
                subject_id=subject_id,
            ) 

            return result

        except Exception as exc:
            return DbResult.fail(str(exc))

    # ------------------------------------------------------------------
    # MRI case CRUD
    # ------------------------------------------------------------------

    def create_mri_case(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        notes: str | None = None,
        status: str | None = "registered",
        source_raw_path: Path | None = None,
    ) -> DbResult[MriCaseRecord]:
        try:
            acq_date = normalize_date(acquisition_date)
            result = self.cases.create(subject_id, acq_date, notes=notes, status=status)
            if not result.success or result.data is None:
                return result

            workspace = self._create_workspace(
                    subject_id=subject_id,
                    acquisition_date=acq_date,
                    source_raw_path=source_raw_path,
                )
            result = DbResult.ok(
                MriCaseRecord(
                    id=result.data.id,
                    subject_id=result.data.subject_id,
                    acquisition_date=result.data.acquisition_date,
                    notes=result.data.notes,
                    status=result.data.status,
                    workspace=workspace,
                )
            )

            return result
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_mri_case(self, case_id: int, *, include_workspace: bool = False) -> DbResult[MriCaseRecord]:
        result = self.cases.get(case_id)
        if not result.success or result.data is None or not include_workspace:
            return result
        return DbResult.ok(self._with_workspace(result.data))

    def get_first_mri_case_for_subject(
        self,
        subject_id: str,
        *,
        include_workspace: bool = False,
    ) -> DbResult[MriCaseRecord]:
        result = self.cases.get_first_for_subject(subject_id)

        if not result.success or result.data is None or not include_workspace:
            return result

        return DbResult.ok(self._with_workspace(result.data))


    def get_mri_case_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        include_workspace: bool = False,
    ) -> DbResult[MriCaseRecord]:
        result = self.cases.get_by_subject_date(subject_id, acquisition_date)

        if not result.success or result.data is None or not include_workspace:
            return result

        return DbResult.ok(self._with_workspace(result.data))


    def update_mri_case_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        new_acquisition_date: str | date | object = UNSET,
        notes: str | None | object = UNSET,
        status: str | None | object = UNSET,
    ) -> DbResult[bool]:
        return self.cases.update_by_subject_date(
            subject_id,
            acquisition_date,
            new_acquisition_date=new_acquisition_date,
            notes=notes,
            status=status,
        )


    def delete_mri_case_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        delete_workspace: bool = False,
    ) -> DbResult[bool]:
        try:
            existing = self.cases.get_by_subject_date(subject_id, acquisition_date)

            if not existing.success:
                return DbResult.fail(existing.error or "Could not load case before delete.")

            if existing.data is None:
                return DbResult.ok(False)

            result = self.cases.delete_by_subject_date(subject_id, acquisition_date)

            if result.success and result.data and delete_workspace:
                self._delete_workspace(existing.data)

            return result

        except Exception as exc:
            return DbResult.fail(str(exc))

    def list_cases_for_subject(
        self,
        subject_id: str,
        *,
        include_workspace: bool = False,
    ) -> DbResult[list[MriCaseRecord]]:
        result = self.cases.list_for_subject(subject_id)
        if not result.success or not include_workspace:
            return result
        return DbResult.ok([self._with_workspace(case) for case in result.data or []])

    # ------------------------------------------------------------------
    # authorization / subject access
    # ------------------------------------------------------------------

    def grant_subject_access(self, user_id: int, subject_id: str, role: str = "viewer") -> DbResult[bool]:
        if not is_known_role(role):
            return DbResult.fail(f"Unknown role '{role}'. Expected one of: {sorted(ROLE_LEVELS)}")
        return self.access.grant(user_id, subject_id, role)

    def revoke_subject_access(self, user_id: int, subject_id: str) -> DbResult[bool]:
        return self.access.revoke(user_id, subject_id)

    def set_subject_role(self, user_id: int, subject_id: str, role: str) -> DbResult[bool]:
        if not is_known_role(role):
            return DbResult.fail(f"Unknown role '{role}'. Expected one of: {sorted(ROLE_LEVELS)}")
        return self.access.set_role(user_id, subject_id, role)

    def get_subject_access(self, user_id: int, subject_id: str):
        return self.access.get(user_id, subject_id)

    def user_has_subject_access(
        self,
        user_id: int,
        subject_id: str,
        *,
        minimum_role: str = "viewer",
    ) -> DbResult[bool]:
        if not is_known_role(minimum_role):
            return DbResult.fail(f"Unknown minimum_role '{minimum_role}'.")

        access = self.access.get(user_id, subject_id)
        if not access.success:
            return DbResult.fail(access.error or "Could not check subject access.")
        if access.data is None:
            return DbResult.ok(False)
        return DbResult.ok(role_allows(access.data.role, minimum_role))

    def user_has_case_access(
        self,
        user_id: int,
        case_id: int,
        *,
        minimum_role: str = "viewer",
    ) -> DbResult[bool]:
        if not is_known_role(minimum_role):
            return DbResult.fail(f"Unknown minimum_role '{minimum_role}'.")

        result = self.access.user_case_role(user_id, case_id)
        if not result.success:
            return DbResult.fail(result.error or "Could not check case access.")
        if result.data is None:
            return DbResult.ok(False)
        return DbResult.ok(role_allows(result.data, minimum_role))

    # ------------------------------------------------------------------
    # authorized searches
    # ------------------------------------------------------------------

    def list_accessible_subjects(
        self,
        user_id: int,
        *,
        include_cases: bool = True,
    ) -> DbResult[list[SubjectWithCases]]:
        return self.search_subjects_for_user(user_id, include_cases=include_cases)

    def search_by_subject_id(
        self,
        user_id: int,
        subject_id: str,
        *,
        include_cases: bool = True,
        include_workspace: bool = False,
    ) -> DbResult[list[SubjectWithCases]]:
        return self.search_subjects_for_user(
            user_id,
            subject_id=subject_id,
            include_cases=include_cases,
            include_workspace=include_workspace,
        )

    def search_by_date(
        self,
        user_id: int,
        acquisition_date: str | date,
        *,
        include_workspace: bool = False,
    ) -> DbResult[list[SubjectWithCases]]:
        return self.search_subjects_for_user(
            user_id,
            acquisition_date=acquisition_date,
            include_cases=True,
            include_workspace=include_workspace,
        )

    def search_subjects_for_user(
        self,
        user_id: int,
        *,
        subject_id: str | None = None,
        acquisition_date: str | date | None = None,
        include_cases: bool = True,
        include_workspace: bool = False,
    ) -> DbResult[list[SubjectWithCases]]:
        """
        Search only inside the subjects visible to a given user.

        This is the method the API should use for UI search screens. It enforces
        authorization by joining through subject_access first.
        """
        rows = self.search.search_subject_rows_for_user(
            user_id,
            subject_id=subject_id,
            acquisition_date=acquisition_date,
            include_cases=include_cases,
        )
        if not rows.success:
            return DbResult.fail(rows.error or "Search failed.")
        return DbResult.ok(
            self._group_subject_search_rows(
                rows.data or [],
                include_workspace=include_workspace,
            )
        )

    # ------------------------------------------------------------------
    # internal workspace/search helpers
    # ------------------------------------------------------------------

    def _with_workspace(self, case: MriCaseRecord) -> MriCaseRecord:
        workspace = None
        if self.workspace_gateway is not None:
            workspace = self.workspace_gateway.get_case_workspace(
                subject_id=case.subject_id,
                acquisition_date=case.acquisition_date,
            )
        return MriCaseRecord(
            id=case.id,
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
            notes=case.notes,
            status=case.status,
            workspace=workspace,
        )

    def _group_subject_search_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        include_workspace: bool,
    ) -> list[SubjectWithCases]:
        grouped: dict[str, tuple[SubjectRecord, str, list[MriCaseRecord]]] = {}

        for row in rows:
            sid = str(row["subject_id"])
            if sid not in grouped:
                grouped[sid] = (
                    SubjectRecord(
                        id=sid,
                        name=row.get("subject_name"),
                        age=row.get("subject_age"),
                        notes=row.get("subject_notes"),
                    ),
                    str(row["access_role"]),
                    [],
                )

            case_id = row.get("case_id")
            if case_id is not None:
                acq_date = date_from_db(row["case_acquisition_date"])
                workspace = None
                if include_workspace and self.workspace_gateway is not None:
                    workspace = self.workspace_gateway.get_case_workspace(
                        subject_id=str(row["case_subject_id"]),
                        acquisition_date=acq_date,
                    )
                grouped[sid][2].append(
                    MriCaseRecord(
                        id=int(case_id),
                        subject_id=str(row["case_subject_id"]),
                        acquisition_date=acq_date,
                        notes=row.get("case_notes"),
                        status=row.get("case_status"),
                        workspace=workspace,
                    )
                )

        return [
            SubjectWithCases(subject=subject, role=role, cases=tuple(cases))
            for subject, role, cases in grouped.values()
        ]

    def _create_workspace(
        self,
        *,
        subject_id: str,
        acquisition_date: date,
        source_raw_path: Path | None,
    ) -> Any:
        if self.workspace_gateway is None:
            raise RuntimeError("create_workspace=True requires a workspace_gateway.")
        return self.workspace_gateway.create_case_workspace(
            subject_id=subject_id,
            acquisition_date=acquisition_date,
            source_raw_path=source_raw_path,
        )

    def _delete_workspace(self, case: MriCaseRecord) -> None:
        if self.workspace_gateway is None:
            raise RuntimeError("delete_workspace=True requires a workspace_gateway.")
        self.workspace_gateway.delete_case_workspace(
            subject_id=case.subject_id,
            acquisition_date=case.acquisition_date,
        )

    def _delete_workspaces_for_cases(self, cases: list[MriCaseRecord]) -> None:
        for case in cases:
            self._delete_workspace(case)


__all__ = ["AccessControlService"]
