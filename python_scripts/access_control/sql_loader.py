from __future__ import annotations

from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=None)
def load_sql(relative_path: str) -> str:
    """Load a SQL statement or fragment from access_control/sql.

    Repositories pass only file names/relative paths. Keeping the actual SQL in
    package files makes the Python layer responsible for parameters and mapping,
    while SQL stays readable and versionable on its own.
    """
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("SQL relative_path must not be empty")

    sql_root = resources.files(__package__).joinpath("sql")
    target = sql_root
    for part in normalized.split("/"):
        if part in {"", ".", ".."}:
            raise ValueError(f"Invalid SQL path segment: {part!r}")
        target = target.joinpath(part)

    return target.read_text(encoding="utf-8").strip()


__all__ = ["load_sql"]
