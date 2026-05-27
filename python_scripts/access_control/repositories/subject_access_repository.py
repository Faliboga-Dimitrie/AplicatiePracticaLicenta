from __future__ import annotations

from ..database import MySqlDatabase
from ..models import SubjectAccessRecord
from ..results import DbResult
from ..utils import access_from_row


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



    def list_subject_ids_for_user(self, user_id: int) -> DbResult[list[str]]:
        """Return subject ids linked to a user before account deletion cascades run."""
        try:
            rows = self.db.fetch_all(
                """
                SELECT subject_id
                FROM subject_access
                WHERE user_id = %s
                ORDER BY subject_id
                """,
                (user_id,),
            )
            return DbResult.ok([str(row["subject_id"]) for row in rows])
        except Exception as exc:
            return DbResult.fail(str(exc))

    def list_for_subject_except_user(self, subject_id: str, excluded_user_id: int) -> DbResult[list[SubjectAccessRecord]]:
        """Return access rows that would remain for a subject after one user is removed."""
        try:
            rows = self.db.fetch_all(
                """
                SELECT user_id, subject_id, role
                FROM subject_access
                WHERE subject_id = %s AND user_id <> %s
                ORDER BY user_id
                """,
                (subject_id, excluded_user_id),
            )
            return DbResult.ok([access_from_row(row) for row in rows])
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
