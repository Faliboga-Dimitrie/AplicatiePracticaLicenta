from __future__ import annotations

from .config import DatabaseConfig
from .database import MySqlDatabase
from .results import DbResult
from .utils import quote_identifier


class SchemaManager:
    """
    Creates the access-control database and tables if they do not already exist.
    """

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

        with self.db.connect(use_database=False) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"CHARACTER SET {charset} COLLATE {collation}"
            )
            conn.commit()
            cursor.close()

    def ensure_schema_exists(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS app_user (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS auth_session (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                user_id BIGINT NOT NULL,
                refresh_token_hash VARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                revoked_at DATETIME NULL,
                last_used_at DATETIME NULL,
                KEY idx_auth_session_user (user_id),
                KEY idx_auth_session_expires (expires_at),
                CONSTRAINT fk_auth_session_user
                    FOREIGN KEY (user_id) REFERENCES app_user(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS subject (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(255) NULL,
                age INT NULL,
                notes TEXT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS mri_case (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                subject_id VARCHAR(100) NOT NULL,
                acquisition_date DATE NOT NULL,
                notes TEXT NULL,
                status VARCHAR(50) NULL,
                UNIQUE KEY uq_mri_case_subject_date (subject_id, acquisition_date),
                KEY idx_mri_case_date (acquisition_date),
                CONSTRAINT fk_mri_case_subject
                    FOREIGN KEY (subject_id) REFERENCES subject(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS subject_access (
                user_id BIGINT NOT NULL,
                subject_id VARCHAR(100) NOT NULL,
                PRIMARY KEY (user_id, subject_id),
                KEY idx_subject_access_subject (subject_id),
                CONSTRAINT fk_subject_access_user
                    FOREIGN KEY (user_id) REFERENCES app_user(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_subject_access_subject
                    FOREIGN KEY (subject_id) REFERENCES subject(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
        ]

        with self.db.connect(use_database=True) as conn:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            self._drop_legacy_subject_access_level_column(cursor)
            conn.commit()
            cursor.close()

    def _drop_legacy_subject_access_level_column(self, cursor) -> None:
        """Remove the old access-level column when upgrading an existing database."""
        cursor.execute("SHOW COLUMNS FROM subject_access LIKE 'role'")
        if cursor.fetchone() is not None:
            cursor.execute("ALTER TABLE subject_access DROP COLUMN role")


__all__ = ["SchemaManager"]
