from __future__ import annotations

from datetime import date
from typing import Any

from ..database import MySqlDatabase
from ..results import DbResult
from ..sql_loader import load_sql
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
            where = [load_sql("subject_search/fragments/filter_user_id.sql")]

            if subject_id is not None:
                where.append(load_sql("subject_search/fragments/filter_subject_id.sql"))
                params.append(subject_id)

            if acquisition_date is not None:
                where.append(load_sql("subject_search/fragments/filter_acquisition_date.sql"))
                params.append(normalize_date(acquisition_date))

            if include_cases:
                case_columns = load_sql("subject_search/fragments/case_columns_with_cases.sql")
                order_clause = load_sql("subject_search/fragments/order_with_cases.sql")
            else:
                case_columns = load_sql("subject_search/fragments/case_columns_without_cases.sql")
                order_clause = load_sql("subject_search/fragments/order_without_cases.sql")

            statement = load_sql("subject_search/search_subject_rows_for_user.sql").format(
                case_columns=case_columns,
                where_clause=" AND ".join(where),
                order_clause=order_clause,
            )

            return DbResult.ok(self.db.fetch_all(statement, tuple(params)))
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
            return DbResult.ok(
                self.db.fetch_all(
                    load_sql("subject_search/list_subject_summaries_for_user.sql"),
                    (user_id,),
                )
            )
        except Exception as exc:
            return DbResult.fail(str(exc))
