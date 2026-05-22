from __future__ import annotations

from datetime import date
from typing import Any

from ..database import MySqlDatabase
from ..models import MriCaseRecord
from ..results import DbResult
from ..utils import UNSET, mri_case_from_row, normalize_date


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
