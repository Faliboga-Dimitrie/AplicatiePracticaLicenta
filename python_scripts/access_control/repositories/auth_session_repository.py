from __future__ import annotations

from datetime import datetime

from ..database import MySqlDatabase
from ..models import AuthSessionRecord
from ..results import DbResult
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
                """
                INSERT INTO auth_session (
                    user_id, refresh_token_hash, created_at, expires_at
                )
                VALUES (%s, %s, UTC_TIMESTAMP(), %s)
                """,
                (user_id, refresh_token_hash, expires_at),
            )
            return self.get_by_id(session_id)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_by_id(self, session_id: int) -> DbResult[AuthSessionRecord]:
        try:
            row = self.db.fetch_one(
                """
                SELECT
                    id, user_id, refresh_token_hash, created_at, expires_at,
                    revoked_at, last_used_at
                FROM auth_session
                WHERE id = %s
                """,
                (session_id,),
            )
            return DbResult.ok(auth_session_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))


    def get_active_by_id(self, *, session_id: int, user_id: int) -> DbResult[AuthSessionRecord]:
        try:
            row = self.db.fetch_one(
                """
                SELECT
                    id, user_id, refresh_token_hash, created_at, expires_at,
                    revoked_at, last_used_at
                FROM auth_session
                WHERE id = %s
                  AND user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > UTC_TIMESTAMP()
                """,
                (session_id, user_id),
            )
            return DbResult.ok(auth_session_from_row(row) if row else None)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def get_active_by_hash(self, refresh_token_hash: str) -> DbResult[AuthSessionRecord]:
        try:
            row = self.db.fetch_one(
                """
                SELECT
                    id, user_id, refresh_token_hash, created_at, expires_at,
                    revoked_at, last_used_at
                FROM auth_session
                WHERE refresh_token_hash = %s
                  AND revoked_at IS NULL
                  AND expires_at > UTC_TIMESTAMP()
                """,
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
            """
            UPDATE auth_session
            SET refresh_token_hash = %s,
                expires_at = %s,
                last_used_at = UTC_TIMESTAMP()
            WHERE id = %s
              AND refresh_token_hash = %s
              AND revoked_at IS NULL
              AND expires_at > UTC_TIMESTAMP()
            """,
            (new_refresh_token_hash, new_expires_at, session_id, old_refresh_token_hash),
        )

    def revoke_by_hash(self, refresh_token_hash: str) -> DbResult[bool]:
        return self.db.execute_bool(
            """
            UPDATE auth_session
            SET revoked_at = UTC_TIMESTAMP()
            WHERE refresh_token_hash = %s
              AND revoked_at IS NULL
            """,
            (refresh_token_hash,),
        )

    def revoke_all_for_user(self, user_id: int) -> DbResult[bool]:
        return self.db.execute_bool(
            """
            UPDATE auth_session
            SET revoked_at = UTC_TIMESTAMP()
            WHERE user_id = %s
              AND revoked_at IS NULL
            """,
            (user_id,),
        )


__all__ = ["AuthSessionRepository"]
