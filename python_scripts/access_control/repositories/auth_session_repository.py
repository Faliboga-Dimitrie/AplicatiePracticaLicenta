from __future__ import annotations

from datetime import datetime

from ..database import MySqlDatabase
from ..models import AuthSessionRecord
from ..results import DbResult
from ..sql_loader import load_sql
from ..utils import auth_session_from_row


class AuthSessionRepository:
    def __init__(self, db: MySqlDatabase):
        self.db = db

    def create(
        self,
        *,
        user_id: int,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> DbResult[AuthSessionRecord]:
        try:
            session_id = self.db.execute_lastrowid(
                load_sql("auth_session/create.sql"),
                (user_id, refresh_token_hash, expires_at),
            )
            return self.get_by_id(session_id)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_by_id(self, session_id: int) -> DbResult[AuthSessionRecord]:
        try:
            row = self.db.fetch_one(
                load_sql("auth_session/get_by_id.sql"),
                (session_id,),
            )
            return DbResult.ok(auth_session_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_active_by_id(self, *, session_id: int, user_id: int) -> DbResult[AuthSessionRecord]:
        try:
            row = self.db.fetch_one(
                load_sql("auth_session/get_active_by_id.sql"),
                (session_id, user_id),
            )
            return DbResult.ok(auth_session_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_active_by_hash(self, refresh_token_hash: str) -> DbResult[AuthSessionRecord]:
        try:
            row = self.db.fetch_one(
                load_sql("auth_session/get_active_by_hash.sql"),
                (refresh_token_hash,),
            )
            return DbResult.ok(auth_session_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def rotate(
        self,
        *,
        session_id: int,
        old_refresh_token_hash: str,
        new_refresh_token_hash: str,
        new_expires_at: datetime,
    ) -> DbResult[bool]:
        return self.db.execute_bool(
            load_sql("auth_session/rotate.sql"),
            (new_refresh_token_hash, new_expires_at, session_id, old_refresh_token_hash),
        )

    def revoke_by_hash(self, refresh_token_hash: str) -> DbResult[bool]:
        return self.db.execute_bool(
            load_sql("auth_session/revoke_by_hash.sql"),
            (refresh_token_hash,),
        )

    def revoke_all_for_user(self, user_id: int) -> DbResult[bool]:
        return self.db.execute_bool(
            load_sql("auth_session/revoke_all_for_user.sql"),
            (user_id,),
        )


__all__ = ["AuthSessionRepository"]
