from __future__ import annotations

from ..database import MySqlDatabase
from ..models import UserCredentialsRecord, UserRecord
from ..results import DbResult
from ..utils import user_credentials_from_row, user_from_row


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
