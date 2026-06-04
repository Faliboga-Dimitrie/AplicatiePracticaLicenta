from __future__ import annotations

from .config import DatabaseConfig
from .database import MySqlDatabase
from .results import DbResult
from .sql_loader import load_sql
from .utils import quote_identifier


class SchemaManager:
    """
    Creates the access-control database and tables if they do not already exist.
    """

    _SCHEMA_STATEMENTS = (
        "schema/create_app_user.sql",
        "schema/create_auth_session.sql",
        "schema/create_subject.sql",
        "schema/create_mri_case.sql",
        "schema/create_subject_access.sql",
    )

    def __init__(self, db: MySqlDatabase, config: DatabaseConfig):
        self.db = db
        self.config = config

    def ensure_storage(self) -> DbResult[bool]:
        try:
            self.ensure_database_exists()
            self.ensure_schema_exists()
            return DbResult.ok(True)
        except Exception as exc:
            return DbResult.fail(str(exc))

    def ensure_database_exists(self) -> None:
        db_name = quote_identifier(self.config.database)
        charset = quote_identifier(self.config.charset)
        collation = quote_identifier(self.config.collation)
        statement = load_sql("schema/create_database.sql").format(
            database=db_name,
            charset=charset,
            collation=collation,
        )

        with self.db.connect(use_database=False) as conn:
            cursor = conn.cursor()
            cursor.execute(statement)
            conn.commit()
            cursor.close()

    def ensure_schema_exists(self) -> None:
        with self.db.connect(use_database=True) as conn:
            cursor = conn.cursor()
            for statement_path in self._SCHEMA_STATEMENTS:
                cursor.execute(load_sql(statement_path))
            self._drop_legacy_subject_access_level_column(cursor)
            conn.commit()
            cursor.close()

    def _drop_legacy_subject_access_level_column(self, cursor) -> None:
        """Remove the old access-level column when upgrading an existing database."""
        cursor.execute(load_sql("schema/find_legacy_subject_access_role_column.sql"))
        if cursor.fetchone() is not None:
            cursor.execute(load_sql("schema/drop_legacy_subject_access_role_column.sql"))


__all__ = ["SchemaManager"]
