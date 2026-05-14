from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseConfig:
    """
    MySQL connection settings for the access-control module.

    The module uses one local MySQL database as lightweight metadata storage for:
    - users;
    - subjects;
    - MRI acquisitions;
    - subject-level access rights.
    """

    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = ""
    database: str = "brain_mri_app"
    charset: str = "utf8mb4"
    collation: str = "utf8mb4_unicode_ci"
    connect_timeout: int = 10


__all__ = ["DatabaseConfig"]
