from __future__ import annotations


ROLE_LEVELS: dict[str, int] = {
    "viewer": 1,
    "editor": 2,
    "admin": 3,
    "owner": 4,
}


def is_known_role(role: str) -> bool:
    return role in ROLE_LEVELS


def role_allows(actual_role: str, minimum_role: str) -> bool:
    return ROLE_LEVELS.get(actual_role, 0) >= ROLE_LEVELS.get(minimum_role, 0)


__all__ = ["ROLE_LEVELS", "is_known_role", "role_allows"]
