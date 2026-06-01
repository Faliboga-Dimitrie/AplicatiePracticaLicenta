from __future__ import annotations

from typing import Any

from ..database import MySqlDatabase
from ..models import SubjectRecord
from ..results import DbResult
from ..utils import UNSET, subject_from_row


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
