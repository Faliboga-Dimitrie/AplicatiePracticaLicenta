from __future__ import annotations

from datetime import date
from typing import Any

from .database import MySqlDatabase
from .models import (
    MriCaseRecord,
    SubjectAccessRecord,
    SubjectRecord,
    UserCredentialsRecord,
    UserRecord,
)
from .results import DbResult
from .utils import (
    UNSET,
    access_from_row,
    mri_case_from_row,
    normalize_date,
    subject_from_row,
    user_credentials_from_row,
    user_from_row,
)


class UserRepository:
    def __init__(self, db: MySqlDatabase):
        self.db = db

    def create(self, email: str, password_hash: str) -> DbResult[UserRecord]:
        try:
            user_id = self.db.execute_lastrowid(
                "INSERT INTO app_user (email, password_hash) VALUES (%s, %s)",
                (email, password_hash),
            )
            return DbResult.ok(UserRecord(id=user_id, email=email))
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_by_id(self, user_id: int) -> DbResult[UserRecord]:
        try:
            row = self.db.fetch_one(
                "SELECT id, email FROM app_user WHERE id = %s",
                (user_id,),
            )
            return DbResult.ok(user_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_by_email(self, email: str) -> DbResult[UserRecord]:
        try:
            row = self.db.fetch_one(
                "SELECT id, email FROM app_user WHERE email = %s",
                (email,),
            )
            return DbResult.ok(user_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_credentials_by_email(self, email: str) -> DbResult[UserCredentialsRecord]:
        try:
            row = self.db.fetch_one(
                "SELECT id, email, password_hash FROM app_user WHERE email = %s",
                (email,),
            )
            return DbResult.ok(user_credentials_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def update_email(self, user_id: int, new_email: str) -> DbResult[bool]:
        return self.db.execute_bool(
            "UPDATE app_user SET email = %s WHERE id = %s",
            (new_email, user_id),
        )

    def update_password_hash(self, user_id: int, password_hash: str) -> DbResult[bool]:
        return self.db.execute_bool(
            "UPDATE app_user SET password_hash = %s WHERE id = %s",
            (password_hash, user_id),
        )

    def delete(self, user_id: int) -> DbResult[bool]:
        return self.db.execute_bool("DELETE FROM app_user WHERE id = %s", (user_id,))


class SubjectRepository:
    def __init__(self, db: MySqlDatabase):
        self.db = db

    def create(
        self,
        subject_id: str,
        *,
        name: str | None = None,
        age: int | None = None,
        notes: str | None = None,
    ) -> DbResult[SubjectRecord]:
        try:
            self.db.execute_lastrowid(
                "INSERT INTO subject (id, name, age, notes) VALUES (%s, %s, %s, %s)",
                (subject_id, name, age, notes),
            )
            return DbResult.ok(SubjectRecord(id=subject_id, name=name, age=age, notes=notes))
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get(self, subject_id: str) -> DbResult[SubjectRecord]:
        try:
            row = self.db.fetch_one(
                "SELECT id, name, age, notes FROM subject WHERE id = %s",
                (subject_id,),
            )
            return DbResult.ok(subject_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def update(
        self,
        subject_id: str,
        *,
        name: str | None | object = UNSET,
        age: int | None | object = UNSET,
        notes: str | None | object = UNSET,
    ) -> DbResult[bool]:
        updates: list[str] = []
        params: list[Any] = []

        if name is not UNSET:
            updates.append("name = %s")
            params.append(name)
        if age is not UNSET:
            updates.append("age = %s")
            params.append(age)
        if notes is not UNSET:
            updates.append("notes = %s")
            params.append(notes)

        if not updates:
            return DbResult.ok(False)

        params.append(subject_id)
        return self.db.execute_bool(
            f"UPDATE subject SET {', '.join(updates)} WHERE id = %s",
            tuple(params),
        )

    def delete(self, subject_id: str) -> DbResult[bool]:
        return self.db.execute_bool("DELETE FROM subject WHERE id = %s", (subject_id,))

    def list_all(self) -> DbResult[list[SubjectRecord]]:
        try:
            rows = self.db.fetch_all(
                "SELECT id, name, age, notes FROM subject ORDER BY id",
            )
            return DbResult.ok([subject_from_row(row) for row in rows])
        except Exception as exc:
            return DbResult.fail(str(exc))


class MriCaseRepository:
    def __init__(self, db: MySqlDatabase):
        self.db = db

    def create(
        self,
        subject_id: str,
        acquisition_date: date,
        *,
        notes: str | None = None,
        status: str | None = "registered",
    ) -> DbResult[MriCaseRecord]:
        try:
            acq_date = normalize_date(acquisition_date)

            case_id = self.db.execute_lastrowid(
                """
                INSERT INTO mri_case (subject_id, acquisition_date, notes, status)
                VALUES (%s, %s, %s, %s)
                """,
                (subject_id, acq_date, notes, status),
            )

            return DbResult.ok(
                MriCaseRecord(
                    id=case_id,
                    subject_id=subject_id,
                    acquisition_date=acq_date,
                    notes=notes,
                    status=status,
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))

    # ------------------------------------------------------------------
    # Internal DB-id access
    # ------------------------------------------------------------------

    def get(self, case_id: int) -> DbResult[MriCaseRecord]:
        """
        Internal lookup by database id.

        Useful inside repositories/services, but the API should usually prefer
        subject_id + acquisition_date.
        """
        try:
            row = self.db.fetch_one(
                """
                SELECT id, subject_id, acquisition_date, notes, status
                FROM mri_case
                WHERE id = %s
                """,
                (case_id,),
            )
            return DbResult.ok(mri_case_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def delete(self, case_id: int) -> DbResult[bool]:
        """
        Internal delete by database id.

        Keep this for implementation convenience, but prefer delete_by_subject_date
        from API routes.
        """
        return self.db.execute_bool(
            "DELETE FROM mri_case WHERE id = %s",
            (case_id,),
        )

    # ------------------------------------------------------------------
    # Public/application-style access
    # ------------------------------------------------------------------

    def get_first_for_subject(self, subject_id: str) -> DbResult[MriCaseRecord]:
        """
        Return the first case for a subject.

        I am using acquisition_date ASC here so 'first' means the earliest
        recorded acquisition. Without ORDER BY, SQL does not guarantee order.
        """
        try:
            row = self.db.fetch_one(
                """
                SELECT id, subject_id, acquisition_date, notes, status
                FROM mri_case
                WHERE subject_id = %s
                ORDER BY acquisition_date ASC
                LIMIT 1
                """,
                (subject_id,),
            )
            return DbResult.ok(mri_case_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
    ) -> DbResult[MriCaseRecord]:
        acq_date = normalize_date(acquisition_date)

        try:
            row = self.db.fetch_one(
                """
                SELECT id, subject_id, acquisition_date, notes, status
                FROM mri_case
                WHERE subject_id = %s AND acquisition_date = %s
                """,
                (subject_id, acq_date),
            )
            return DbResult.ok(mri_case_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def update_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
        *,
        new_acquisition_date: str | date | object = UNSET,
        notes: str | None | object = UNSET,
        status: str | None | object = UNSET,
    ) -> DbResult[bool]:
        current_acq_date = normalize_date(acquisition_date)

        updates: list[str] = []
        params: list[Any] = []

        if new_acquisition_date is not UNSET:
            updates.append("acquisition_date = %s")
            params.append(normalize_date(new_acquisition_date))

        if notes is not UNSET:
            updates.append("notes = %s")
            params.append(notes)

        if status is not UNSET:
            updates.append("status = %s")
            params.append(status)

        if not updates:
            return DbResult.ok(False)

        params.extend([subject_id, current_acq_date])

        return self.db.execute_bool(
            f"""
            UPDATE mri_case
            SET {', '.join(updates)}
            WHERE subject_id = %s AND acquisition_date = %s
            """,
            tuple(params),
        )

    def delete_by_subject_date(
        self,
        subject_id: str,
        acquisition_date: str | date,
    ) -> DbResult[bool]:
        acq_date = normalize_date(acquisition_date)

        return self.db.execute_bool(
            """
            DELETE FROM mri_case
            WHERE subject_id = %s AND acquisition_date = %s
            """,
            (subject_id, acq_date),
        )

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    def list_for_subject(self, subject_id: str) -> DbResult[list[MriCaseRecord]]:
        try:
            rows = self.db.fetch_all(
                """
                SELECT id, subject_id, acquisition_date, notes, status
                FROM mri_case
                WHERE subject_id = %s
                ORDER BY acquisition_date ASC
                """,
                (subject_id,),
            )
            return DbResult.ok([mri_case_from_row(row) for row in rows])
        except Exception as exc:
            return DbResult.fail(str(exc))

    def list_all(self) -> DbResult[list[MriCaseRecord]]:
        try:
            rows = self.db.fetch_all(
                """
                SELECT id, subject_id, acquisition_date, notes, status
                FROM mri_case
                ORDER BY subject_id ASC, acquisition_date ASC
                """
            )
            return DbResult.ok([mri_case_from_row(row) for row in rows])
        except Exception as exc:
            return DbResult.fail(str(exc))


class SubjectAccessRepository:
    def __init__(self, db: MySqlDatabase):
        self.db = db

    def grant(self, user_id: int, subject_id: str, role: str = "viewer") -> DbResult[bool]:
        return self.db.execute_bool(
            """
            INSERT INTO subject_access (user_id, subject_id, role)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE role = VALUES(role)
            """,
            (user_id, subject_id, role),
        )

    def revoke(self, user_id: int, subject_id: str) -> DbResult[bool]:
        return self.db.execute_bool(
            "DELETE FROM subject_access WHERE user_id = %s AND subject_id = %s",
            (user_id, subject_id),
        )

    def set_role(self, user_id: int, subject_id: str, role: str) -> DbResult[bool]:
        return self.db.execute_bool(
            "UPDATE subject_access SET role = %s WHERE user_id = %s AND subject_id = %s",
            (role, user_id, subject_id),
        )

    def get(self, user_id: int, subject_id: str) -> DbResult[SubjectAccessRecord]:
        try:
            row = self.db.fetch_one(
                """
                SELECT user_id, subject_id, role
                FROM subject_access
                WHERE user_id = %s AND subject_id = %s
                """,
                (user_id, subject_id),
            )
            return DbResult.ok(access_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def user_case_role(self, user_id: int, case_id: int) -> DbResult[str]:
        try:
            row = self.db.fetch_one(
                """
                SELECT sa.role
                FROM mri_case c
                JOIN subject_access sa ON sa.subject_id = c.subject_id
                WHERE c.id = %s AND sa.user_id = %s
                """,
                (case_id, user_id),
            )
            return DbResult.ok(str(row["role"]) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))


class SubjectSearchRepository:
    def __init__(self, db: MySqlDatabase):
        self.db = db

    def search_subject_rows_for_user(
        self,
        user_id: int,
        *,
        subject_id: str | None = None,
        acquisition_date: str | date | None = None,
        include_cases: bool = True,
    ) -> DbResult[list[dict[str, Any]]]:
        try:
            params: list[Any] = [user_id]
            where = ["sa.user_id = %s"]

            if subject_id is not None:
                where.append("s.id = %s")
                params.append(subject_id)

            if acquisition_date is not None:
                where.append("c.acquisition_date = %s")
                params.append(normalize_date(acquisition_date))

            if include_cases:
                case_columns = """
                    c.id AS case_id,
                    c.subject_id AS case_subject_id,
                    c.acquisition_date AS case_acquisition_date,
                    c.notes AS case_notes,
                    c.status AS case_status
                """
                order = "ORDER BY s.id, c.acquisition_date"
            else:
                case_columns = """
                    NULL AS case_id,
                    NULL AS case_subject_id,
                    NULL AS case_acquisition_date,
                    NULL AS case_notes,
                    NULL AS case_status
                """
                order = "ORDER BY s.id"

            sql = f"""
                SELECT
                    s.id AS subject_id,
                    s.name AS subject_name,
                    s.age AS subject_age,
                    s.notes AS subject_notes,
                    sa.role AS access_role,
                    {case_columns}
                FROM subject_access sa
                JOIN subject s ON s.id = sa.subject_id
                LEFT JOIN mri_case c ON c.subject_id = s.id
                WHERE {' AND '.join(where)}
                {order}
            """

            return DbResult.ok(self.db.fetch_all(sql, tuple(params)))
        except Exception as exc:
            return DbResult.fail(str(exc))


__all__ = [
    "MriCaseRepository",
    "SubjectAccessRepository",
    "SubjectRepository",
    "SubjectSearchRepository",
    "UserRepository",
]
