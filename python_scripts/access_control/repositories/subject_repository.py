from __future__ import annotations

from typing import Any

from ..database import MySqlDatabase
from ..models import SubjectRecord
from ..results import DbResult
from ..sql_loader import load_sql
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
                load_sql("subject/create.sql"),
                (subject_id, name, age, notes),
            )
            return DbResult.ok(SubjectRecord(id=subject_id, name=name, age=age, notes=notes))
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get(self, subject_id: str) -> DbResult[SubjectRecord]:
        try:
            row = self.db.fetch_one(
                load_sql("subject/get.sql"),
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
            updates.append(load_sql("subject/fragments/set_name.sql"))
            params.append(name)
        if age is not UNSET:
            updates.append(load_sql("subject/fragments/set_age.sql"))
            params.append(age)
        if notes is not UNSET:
            updates.append(load_sql("subject/fragments/set_notes.sql"))
            params.append(notes)

        if not updates:
            return DbResult.ok(False)

        params.append(subject_id)
        statement = load_sql("subject/update.sql").format(assignments=", ".join(updates))
        return self.db.execute_bool(statement, tuple(params))

    def delete(self, subject_id: str) -> DbResult[bool]:
        return self.db.execute_bool(load_sql("subject/delete.sql"), (subject_id,))
