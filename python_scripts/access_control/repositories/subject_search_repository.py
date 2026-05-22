from __future__ import annotations

from datetime import date
from typing import Any

from ..database import MySqlDatabase
from ..results import DbResult
from ..utils import normalize_date


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

    def list_subject_summaries_for_user(
        self,
        user_id: int,
    ) -> DbResult[list[dict[str, Any]]]:
        """
        Return one row per subject visible to the user, with case_count computed
        by SQL instead of loading every case row.
        """
        try:
            sql = """
                SELECT
                    s.id AS subject_id,
                    s.name AS subject_name,
                    s.age AS subject_age,
                    s.notes AS subject_notes,
                    sa.role AS access_role,
                    COUNT(c.id) AS case_count
                FROM subject_access sa
                JOIN subject s ON s.id = sa.subject_id
                LEFT JOIN mri_case c ON c.subject_id = s.id
                WHERE sa.user_id = %s
                GROUP BY
                    s.id,
                    s.name,
                    s.age,
                    s.notes,
                    sa.role
                ORDER BY s.id
            """

            return DbResult.ok(self.db.fetch_all(sql, (user_id,)))
        except Exception as exc:
            return DbResult.fail(str(exc))

