from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import DatabaseConfig
from .database import MySqlDatabase
from .models import AuthSessionRecord, MriCaseRecord, SubjectRecord, SubjectSummaryRecord, SubjectWithCases, UserRecord
from .password_hashing import PasswordHasher
from .repositories import (
    AuthSessionRepository,
    MriCaseRepository,
    SubjectAccessRepository,
    SubjectRepository,
    SubjectSearchRepository,
    UserRepository,
)
from .results import AuthResult, DbResult
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


@dataclass(frozen=True)
class AccessControlRepositories:
    """Repository bundle used to inject storage dependencies in tests.

    Production code does not need to construct this object. If no repositories
    are supplied to AccessControlService, the service builds the standard
    MySQL-backed repositories from the configured database helper.
    """

    users: Any
    sessions: Any
    subjects: Any
    cases: Any
    access: Any
    search: Any


def _invalid_subject_age(age: int | None | object) -> bool:
    return age is not UNSET and age is not None and isinstance(age, int) and age < 0

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
        config: DatabaseConfig | None = None,
        *,
        db: Any | None = None,
        schema: Any | None = None,
        repositories: AccessControlRepositories | None = None,
        users: Any | None = None,
        sessions: Any | None = None,
        subjects: Any | None = None,
        cases: Any | None = None,
        access: Any | None = None,
        search: Any | None = None,
        password_hasher: PasswordHasher | None = None,
        workspace_gateway: WorkspaceGateway | None = None,
    ):
        """Build the access-control service.

        The default constructor path is still production-ready: if db, schema,
        and repositories are omitted, the service creates the normal MySQL
        database helper, schema manager, and repository objects.

        Unit tests can inject any dependency they want:
        - db/schema, when testing schema setup without the real connector;
        - individual repositories, when testing service logic with fakes;
        - an AccessControlRepositories bundle, when replacing all repositories;
        - password_hasher/workspace_gateway, for authentication and filesystem
          side-effect tests.
        """
        self.config = config or DatabaseConfig()
        self.password_hasher = password_hasher or PasswordHasher()
        self.workspace_gateway = workspace_gateway

        self.db = db if db is not None else MySqlDatabase(self.config)
        self.schema = schema if schema is not None else SchemaManager(self.db, self.config)

        if repositories is not None:
            self.users = users if users is not None else repositories.users
            self.sessions = sessions if sessions is not None else repositories.sessions
            self.subjects = subjects if subjects is not None else repositories.subjects
            self.cases = cases if cases is not None else repositories.cases
            self.access = access if access is not None else repositories.access
            self.search = search if search is not None else repositories.search
        else:
            self.users = users if users is not None else UserRepository(self.db)
            self.sessions = sessions if sessions is not None else AuthSessionRepository(self.db)
            self.subjects = subjects if subjects is not None else SubjectRepository(self.db)
            self.cases = cases if cases is not None else MriCaseRepository(self.db)
            self.access = access if access is not None else SubjectAccessRepository(self.db)
            self.search = search if search is not None else SubjectSearchRepository(self.db)

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

    def delete_user_account(self, user_id: int) -> DbResult[dict[str, Any]]:
        """Delete a user account and cascade orphaned/unmaintained subjects.

        Rule used by the React settings screen:
        - the user row and all of that user's refresh sessions/access rows are removed;
        - every subject visible to that user is inspected before the user is deleted;
        - if, after removing this user, at least one remaining account still has access,
          the subject is kept;
        - if no remaining account has access, the subject and its cases/workspaces
          are deleted too.
        """
        try:
            user = self.users.get_by_id(user_id)
            if not user.success:
                return DbResult.fail(user.error or "Could not load user before account deletion.")
            if user.data is None:
                return DbResult.ok({
                    "deleted": False,
                    "deleted_subject_ids": [],
                    "kept_subject_ids": [],
                })

            subject_ids_result = self.access.list_subject_ids_for_user(user_id)
            if not subject_ids_result.success:
                return DbResult.fail(subject_ids_result.error or "Could not load user subjects before account deletion.")

            subject_ids = subject_ids_result.data or []
            deleted_subject_ids: list[str] = []
            kept_subject_ids: list[str] = []

            for subject_id in subject_ids:
                remaining_result = self.access.list_for_subject_except_user(subject_id, user_id)
                if not remaining_result.success:
                    return DbResult.fail(remaining_result.error or f"Could not inspect remaining access for subject '{subject_id}'.")

                remaining_access = remaining_result.data or []

                if remaining_access:
                    kept_subject_ids.append(subject_id)
                else:
                    deleted_subject_ids.append(subject_id)

            # Revoking sessions is technically covered by app_user ON DELETE CASCADE,
            # but doing it explicitly makes the account deletion intent obvious.
            sessions = self.revoke_all_auth_sessions_for_user(user_id)
            if not sessions.success:
                return DbResult.fail(sessions.error or "Could not revoke user sessions before account deletion.")

            deleted_user = self.users.delete(user_id)
            if not deleted_user.success:
                return DbResult.fail(deleted_user.error or "Could not delete user account.")
            if not deleted_user.data:
                return DbResult.ok({
                    "deleted": False,
                    "deleted_subject_ids": [],
                    "kept_subject_ids": kept_subject_ids,
                })

            for subject_id in deleted_subject_ids:
                deleted_subject = self.subjects.delete(subject_id)
                if not deleted_subject.success:
                    return DbResult.fail(deleted_subject.error or f"User was deleted, but subject '{subject_id}' could not be deleted.")

                if deleted_subject.data and self.workspace_gateway is not None:
                    self.workspace_gateway.delete_subject_workspaces(subject_id=subject_id)

            return DbResult.ok({
                "deleted": True,
                "deleted_subject_ids": deleted_subject_ids,
                "kept_subject_ids": kept_subject_ids,
            })

        except Exception as exc:
            return DbResult.fail(str(exc))

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
    # refresh-token sessions
    # ------------------------------------------------------------------

    def create_auth_session(
        self,
        *,
        user_id: int,
        refresh_token_hash: str,
        expires_at: Any,
    ) -> DbResult[AuthSessionRecord]:
        return self.sessions.create(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )

    def get_active_auth_session_by_hash(
        self,
        refresh_token_hash: str,
    ) -> DbResult[AuthSessionRecord]:
        return self.sessions.get_active_by_hash(refresh_token_hash)

    def get_active_auth_session_by_id(
        self,
        *,
        session_id: int,
        user_id: int,
    ) -> DbResult[AuthSessionRecord]:
        return self.sessions.get_active_by_id(session_id=session_id, user_id=user_id)

    def rotate_auth_session(
        self,
        *,
        session_id: int,
        old_refresh_token_hash: str,
        new_refresh_token_hash: str,
        new_expires_at: Any,
    ) -> DbResult[bool]:
        return self.sessions.rotate(
            session_id=session_id,
            old_refresh_token_hash=old_refresh_token_hash,
            new_refresh_token_hash=new_refresh_token_hash,
            new_expires_at=new_expires_at,
        )

    def revoke_auth_session_by_hash(self, refresh_token_hash: str) -> DbResult[bool]:
        return self.sessions.revoke_by_hash(refresh_token_hash)

    def revoke_all_auth_sessions_for_user(self, user_id: int) -> DbResult[bool]:
        return self.sessions.revoke_all_for_user(user_id)

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
        if _invalid_subject_age(age):
            return DbResult.fail("Subject age cannot be negative.")
        return self.subjects.update(subject_id, name=name, age=age, notes=notes)

    def update_subject_for_user(
        self,
        user_id: int,
        subject_id: str,
        *,
        name: str | None | object = UNSET,
        age: int | None | object = UNSET,
        notes: str | None | object = UNSET,
    ) -> DbResult[bool]:
        if _invalid_subject_age(age):
            return DbResult.fail("Subject age cannot be negative.")
        access = self.access.get(user_id, subject_id)
        if not access.success:
            return DbResult.fail(access.error or "Could not check subject access.")
        if access.data is None:
            return DbResult.ok(False)

        return self.subjects.update(subject_id, name=name, age=age, notes=notes)

    def delete_subject(self, subject_id: str) -> DbResult[bool]:
        try:
            existing = self.subjects.get(subject_id)
            if not existing.success:
                return DbResult.fail(existing.error or "Could not load subject before delete.")
            if existing.data is None:
                return DbResult.ok(False)

            if self.workspace_gateway is None:
                return DbResult.fail("delete_workspaces=True requires a workspace_gateway.")

            staged_workspace_delete = self.workspace_gateway.stage_subject_workspaces_delete(
                subject_id=subject_id,
            )

            result = self.subjects.delete(subject_id)

            if not result.success or not result.data:
                self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                return result

            self.workspace_gateway.commit_staged_delete(staged_workspace_delete)
            return result

        except Exception as exc:
            return DbResult.fail(str(exc))

    def delete_subject_for_user(self, user_id: int, subject_id: str) -> DbResult[bool]:
        """
        Delete a subject from a normal user-facing flow.

        This mirrors the API's create_for_user flow: the operation is performed
        in the context of a logged-in user, so the user's subject_access row is
        explicitly removed before deleting the subject row itself. That keeps the
        subject_access table clean even when the database schema was created
        before ON DELETE CASCADE was added.
        """
        try:
            subject_id = normalize_required_text(subject_id, "subject_id")

            existing_access = self.access.get(user_id, subject_id)
            if not existing_access.success:
                return DbResult.fail(existing_access.error or "Could not check subject access before delete.")
            if existing_access.data is None:
                return DbResult.ok(False)

            existing = self.subjects.get(subject_id)
            if not existing.success:
                return DbResult.fail(existing.error or "Could not load subject before delete.")
            if existing.data is None:
                return DbResult.ok(False)

            if self.workspace_gateway is None:
                return DbResult.fail("delete_workspaces=True requires a workspace_gateway.")

            staged_workspace_delete = self.workspace_gateway.stage_subject_workspaces_delete(
                subject_id=subject_id,
            )

            revoked = self.access.revoke(user_id, subject_id)
            if not revoked.success:
                self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                return DbResult.fail(revoked.error or "Could not revoke subject access before delete.")

            deleted = self.subjects.delete(subject_id)
            if not deleted.success:
                self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                restored_access = self.access.grant(user_id, subject_id)
                if not restored_access.success:
                    return DbResult.fail(
                        f"Subject delete failed and access rollback also failed: {restored_access.error}"
                    )
                return deleted
            if not deleted.data:
                self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                self.access.grant(user_id, subject_id)
                return deleted

            self.workspace_gateway.commit_staged_delete(staged_workspace_delete)
            return DbResult.ok(True)

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

            try:
                workspace = self._create_workspace(
                    subject_id=subject_id,
                    acquisition_date=acq_date,
                    source_raw_path=source_raw_path,
                )
            except Exception as exc:
                rollback = self.cases.delete(result.data.id)
                if not rollback.success:
                    return DbResult.fail(
                        f"Workspace creation failed after DB case create: {exc}. "
                        f"DB rollback failed: {rollback.error}"
                    )
                return DbResult.fail(
                    f"Workspace creation failed after DB case create; database rollback succeeded. {exc}"
                )

            return DbResult.ok(
                MriCaseRecord(
                    id=result.data.id,
                    subject_id=result.data.subject_id,
                    acquisition_date=result.data.acquisition_date,
                    notes=result.data.notes,
                    status=result.data.status,
                    workspace=workspace,
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_mri_case(self, case_id: int) -> DbResult[MriCaseRecord]:
        result = self.cases.get(case_id)
        if not result.success or result.data is None:
            return result
        return DbResult.ok(self._with_workspace(result.data))


    def get_mri_case_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
    ) -> DbResult[MriCaseRecord]:
        result = self.cases.get_by_subject_date(subject_id, acquisition_date)

        if not result.success or result.data is None:
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
        try:
            current_acq_date = normalize_date(acquisition_date)

            old_case = self.cases.get_by_subject_date(subject_id, current_acq_date)
            if not old_case.success:
                return DbResult.fail(old_case.error or "Could not load MRI case before update.")
            if old_case.data is None:
                return DbResult.ok(False)

            date_is_changing = new_acquisition_date is not UNSET

            if not date_is_changing:
                return self.cases.update_by_subject_date(
                    subject_id,
                    current_acq_date,
                    notes=notes,
                    status=status,
                )

            next_acq_date = normalize_date(new_acquisition_date)

            if next_acq_date == current_acq_date:
                return self.cases.update_by_subject_date(
                    subject_id,
                    current_acq_date,
                    notes=notes,
                    status=status,
                )

            existing_target = self.cases.get_by_subject_date(subject_id, next_acq_date)
            if not existing_target.success:
                return DbResult.fail(existing_target.error or "Could not check target MRI case date.")
            if existing_target.data is not None:
                return DbResult.fail(
                    f"MRI case already exists for subject '{subject_id}' "
                    f"on acquisition date '{next_acq_date.isoformat()}'."
                )

            moved_paths = []

            if self.workspace_gateway is None:
                return DbResult.fail("rename_workspace=True requires a workspace_gateway.")

            moved_paths = self.workspace_gateway.rename_case_workspace(
                subject_id=subject_id,
                old_acquisition_date=current_acq_date,
                new_acquisition_date=next_acq_date,
                overwrite=False,
            )

                
            update_result = self.cases.update_by_subject_date(
                subject_id,
                current_acq_date,
                new_acquisition_date=next_acq_date,
                notes=notes,
                status=status,
            )

            if update_result.success and update_result.data:
                return update_result

            # Rollback filesystem rename if DB update failed.
            if moved_paths:
                try:
                    self.workspace_gateway.rename_case_workspace(
                        subject_id=subject_id,
                        old_acquisition_date=next_acq_date,
                        new_acquisition_date=current_acq_date,
                        overwrite=False,
                    )
                except Exception:
                    pass

            return update_result

        except Exception as exc:
            return DbResult.fail(str(exc))


    def register_mri_case_input(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        source_raw_path: Path,
    ) -> DbResult[MriCaseRecord]:
        """Copy a raw MRI file into an existing case workspace.

        This method is intentionally non-destructive. It is used when the case
        metadata exists but the canonical input file is missing, for example
        after input_mri/ was deleted manually. Processed outputs are preserved.
        """
        try:
            acq_date = normalize_date(acquisition_date)
            existing = self.cases.get_by_subject_date(subject_id, acq_date)
            if not existing.success:
                return DbResult.fail(existing.error or "Could not load MRI case before input registration.")
            if existing.data is None:
                return DbResult.ok(None)

            workspace = self._create_workspace(
                subject_id=subject_id,
                acquisition_date=acq_date,
                source_raw_path=source_raw_path,
            )

            return DbResult.ok(
                MriCaseRecord(
                    id=existing.data.id,
                    subject_id=existing.data.subject_id,
                    acquisition_date=existing.data.acquisition_date,
                    notes=existing.data.notes,
                    status=existing.data.status,
                    workspace=workspace,
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

    def replace_mri_case_input(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        source_raw_path: Path,
    ) -> DbResult[MriCaseRecord]:
        """Replace a case raw MRI and clear all generated case files.

        The database row is kept, because the operation belongs to the existing
        case card. Only the filesystem workspace is replaced and the status is
        reset to ``registered`` so preprocessing can be run again from scratch.
        """
        try:
            acq_date = normalize_date(acquisition_date)
            existing = self.cases.get_by_subject_date(subject_id, acq_date)
            if not existing.success:
                return DbResult.fail(existing.error or "Could not load MRI case before input replacement.")
            if existing.data is None:
                return DbResult.ok(None)

            if self.workspace_gateway is None:
                return DbResult.fail("replace_workspace=True requires a workspace_gateway.")

            staged_workspace_delete = self.workspace_gateway.stage_case_workspace_delete(
                subject_id=existing.data.subject_id,
                acquisition_date=existing.data.acquisition_date,
            )

            try:
                workspace = self._create_workspace(
                    subject_id=existing.data.subject_id,
                    acquisition_date=existing.data.acquisition_date,
                    source_raw_path=source_raw_path,
                )

                updated = self.cases.update_by_subject_date(
                    existing.data.subject_id,
                    existing.data.acquisition_date,
                    status="registered",
                )
                if not updated.success:
                    self.workspace_gateway.delete_case_workspace(
                        subject_id=existing.data.subject_id,
                        acquisition_date=existing.data.acquisition_date,
                    )
                    self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                    return DbResult.fail(updated.error or "Could not reset MRI case status after input replacement.")

            except Exception as exc:
                try:
                    self.workspace_gateway.delete_case_workspace(
                        subject_id=existing.data.subject_id,
                        acquisition_date=existing.data.acquisition_date,
                    )
                finally:
                    self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                return DbResult.fail(str(exc))

            self.workspace_gateway.commit_staged_delete(staged_workspace_delete)

            return DbResult.ok(
                MriCaseRecord(
                    id=existing.data.id,
                    subject_id=existing.data.subject_id,
                    acquisition_date=existing.data.acquisition_date,
                    notes=existing.data.notes,
                    status="registered",
                    workspace=workspace,
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

    def delete_mri_case_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
    ) -> DbResult[bool]:
        try:
            existing = self.cases.get_by_subject_date(subject_id, acquisition_date)

            if not existing.success:
                return DbResult.fail(existing.error or "Could not load case before delete.")

            if existing.data is None:
                return DbResult.ok(False)

            if self.workspace_gateway is None:
                return DbResult.fail("delete_workspace=True requires a workspace_gateway.")

            staged_workspace_delete = self.workspace_gateway.stage_case_workspace_delete(
                subject_id=existing.data.subject_id,
                acquisition_date=existing.data.acquisition_date,
            )

            result = self.cases.delete_by_subject_date(subject_id, acquisition_date)

            if not result.success or not result.data:
                self.workspace_gateway.rollback_staged_delete(staged_workspace_delete)
                return result

            self.workspace_gateway.commit_staged_delete(staged_workspace_delete)
            return result

        except Exception as exc:
            return DbResult.fail(str(exc))

    def list_cases_for_subject(
        self,
        subject_id: str,
    ) -> DbResult[list[MriCaseRecord]]:
        result = self.cases.list_for_subject(subject_id)
        if not result.success:
            return result
        return DbResult.ok([self._with_workspace(case) for case in result.data or []])

    # ------------------------------------------------------------------
    # authorization / subject access
    # ------------------------------------------------------------------

    def grant_subject_access(self, user_id: int, subject_id: str) -> DbResult[bool]:
        return self.access.grant(user_id, subject_id)

    def get_subject_access(self, user_id: int, subject_id: str):
        return self.access.get(user_id, subject_id)

    def user_has_subject_access(
        self,
        user_id: int,
        subject_id: str,
    ) -> DbResult[bool]:
        access = self.access.get(user_id, subject_id)
        if not access.success:
            return DbResult.fail(access.error or "Could not check subject access.")
        return DbResult.ok(access.data is not None)

    def user_has_case_access(
        self,
        user_id: int,
        case_id: int,
    ) -> DbResult[bool]:
        result = self.access.user_has_case_access(user_id, case_id)
        if not result.success:
            return DbResult.fail(result.error or "Could not check case access.")
        return result

    # ------------------------------------------------------------------
    # authorized searches
    # ------------------------------------------------------------------


    def list_accessible_subject_summaries(
        self,
        user_id: int,
    ) -> DbResult[list[SubjectSummaryRecord]]:
        """
        Return visible subjects for list screens without loading full case rows.

        The repository uses COUNT(c.id), so this is cheaper than
        list_accessible_subjects(..., include_cases=True) when the API only
        needs case_count.
        """
        rows = self.search.list_subject_summaries_for_user(user_id)
        if not rows.success:
            return DbResult.fail(rows.error or "Could not load subject summaries.")

        summaries = [
            SubjectSummaryRecord(
                subject=SubjectRecord(
                    id=str(row["subject_id"]),
                    name=row.get("subject_name"),
                    age=row.get("subject_age"),
                    notes=row.get("subject_notes"),
                ),
                case_count=int(row.get("case_count") or 0),
            )
            for row in rows.data or []
        ]

        return DbResult.ok(summaries)

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
    ) -> DbResult[list[SubjectWithCases]]:
        return self.search_subjects_for_user(
            user_id,
            subject_id=subject_id,
            include_cases=include_cases,
        )

    def search_subjects_for_user(
        self,
        user_id: int,
        *,
        subject_id: str | None = None,
        acquisition_date: str | date | None = None,
        include_cases: bool = True,
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
            self._group_subject_search_rows(rows.data or [])
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
    ) -> list[SubjectWithCases]:
        grouped: dict[str, tuple[SubjectRecord, list[MriCaseRecord]]] = {}

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
                    [],
                )

            case_id = row.get("case_id")
            if case_id is not None:
                acq_date = date_from_db(row["case_acquisition_date"])
                workspace = None
                if self.workspace_gateway is not None:
                    workspace = self.workspace_gateway.get_case_workspace(
                        subject_id=str(row["case_subject_id"]),
                        acquisition_date=acq_date,
                    )
                grouped[sid][1].append(
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
            SubjectWithCases(subject=subject, cases=tuple(cases))
            for subject, cases in grouped.values()
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


__all__ = ["AccessControlRepositories", "AccessControlService"]
