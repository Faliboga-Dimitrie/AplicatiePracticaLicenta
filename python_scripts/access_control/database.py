from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from .config import DatabaseConfig
from .results import DbResult

try:
    import mysql.connector  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - handled at runtime by require_mysql_driver
    mysql = None  # type: ignore[assignment]
else:
    mysql = mysql.connector


def require_mysql_driver() -> None:
    if mysql is None:
        raise RuntimeError(
            "mysql-connector-python is required. Install it with: "
            "pip install mysql-connector-python"
        )


class MySqlDatabase:
    """
    Low-level MySQL helper used by repositories and schema setup.

    It intentionally exposes simple fetch/execute helpers so the higher layers
    remain focused on application logic instead of connection management.
    """

    def __init__(self, config: DatabaseConfig):
        self.config = config

    @contextmanager
    def connect(self, *, use_database: bool = True) -> Iterator[Any]:
        require_mysql_driver()
        kwargs: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "charset": self.config.charset,
            "connection_timeout": self.config.connect_timeout,
        }
        if use_database:
            kwargs["database"] = self.config.database

        conn = mysql.connect(**kwargs)  # type: ignore[union-attr]
        try:
            yield conn
        finally:
            conn.close()

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            row = cursor.fetchone()
            cursor.close()
        return row

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql, params)
            rows = list(cursor.fetchall())
            cursor.close()
        return rows

    def execute_bool(self, sql: str, params: tuple[Any, ...] = ()) -> DbResult[bool]:
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                affected = int(cursor.rowcount)
                conn.commit()
                cursor.close()
            return DbResult.ok(affected > 0)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def execute_lastrowid(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            lastrowid = int(cursor.lastrowid)
            conn.commit()
            cursor.close()
        return lastrowid


__all__ = ["MySqlDatabase", "require_mysql_driver"]
