from __future__ import annotations

from datetime import date, datetime, timedelta

from python_scripts.access_control.results import DbResult
from python_scripts.access_control.repositories.auth_session_repository import AuthSessionRepository
from python_scripts.access_control.repositories.mri_case_repository import MriCaseRepository
from python_scripts.access_control.repositories.subject_access_repository import SubjectAccessRepository
from python_scripts.access_control.repositories.subject_repository import SubjectRepository
from python_scripts.access_control.repositories.subject_search_repository import SubjectSearchRepository
from python_scripts.access_control.repositories.user_repository import UserRepository
from python_scripts.access_control.utils import UNSET


class FakeDb:
    def __init__(self):
        self.lastrowid = 1
        self.fetch_one_result = None
        self.fetch_all_result = []
        self.bool_result = DbResult.ok(True)
        self.calls: list[tuple[str, str, tuple]] = []

    def execute_lastrowid(self, sql, params=()):
        self.calls.append(("lastrowid", sql, tuple(params)))
        return self.lastrowid

    def fetch_one(self, sql, params=()):
        self.calls.append(("fetch_one", sql, tuple(params)))
        return self.fetch_one_result

    def fetch_all(self, sql, params=()):
        self.calls.append(("fetch_all", sql, tuple(params)))
        return self.fetch_all_result

    def execute_bool(self, sql, params=()):
        self.calls.append(("bool", sql, tuple(params)))
        return self.bool_result


def test_user_repository_creates_reads_updates_and_deletes_users():
    # Arrange
    db = FakeDb()
    repo = UserRepository(db)
    db.fetch_one_result = {"id": 7, "email": "a@b.ro", "password_hash": "hash"}

    # Act
    created = repo.create("a@b.ro", "hash")
    by_id = repo.get_by_id(7)
    credentials = repo.get_credentials_by_email("a@b.ro")
    updated = repo.update_email(7, "new@b.ro")
    deleted = repo.delete(7)

    # Assert
    assert created.data.id == 1
    assert by_id.data.email == "a@b.ro"
    assert credentials.data.password_hash == "hash"
    assert updated.data is True
    assert deleted.data is True
    assert [call[0] for call in db.calls].count("bool") == 2


def test_subject_repository_update_builds_only_requested_fields():
    # Arrange
    db = FakeDb()
    repo = SubjectRepository(db)

    # Act
    no_changes = repo.update("IXI001")
    changed = repo.update("IXI001", name="New", notes=None)

    # Assert
    assert no_changes.data is False
    assert changed.data is True
    assert "name = %s" in db.calls[-1][1]
    assert "notes = %s" in db.calls[-1][1]
    assert "age = %s" not in db.calls[-1][1]
    assert db.calls[-1][2] == ("New", None, "IXI001")


def test_subject_repository_create_get_and_delete_map_results():
    # Arrange
    db = FakeDb()
    repo = SubjectRepository(db)
    db.fetch_one_result = {"id": "IXI001", "name": "A", "age": 20, "notes": "n"}

    # Act
    created = repo.create("IXI001", name="A", age=20, notes="n")
    loaded = repo.get("IXI001")
    deleted = repo.delete("IXI001")

    # Assert
    assert created.data.id == "IXI001"
    assert loaded.data.age == 20
    assert deleted.data is True


def test_mri_case_repository_maps_case_rows_and_dynamic_updates():
    # Arrange
    db = FakeDb()
    repo = MriCaseRepository(db)
    db.lastrowid = 44
    db.fetch_one_result = {
        "id": 44,
        "subject_id": "IXI001",
        "acquisition_date": "2026-06-02",
        "notes": "old",
        "status": "registered",
    }

    # Act
    created = repo.create("IXI001", date(2026, 6, 2), notes="old")
    loaded = repo.get_by_subject_date("IXI001", "2026-06-02")
    no_changes = repo.update_by_subject_date("IXI001", "2026-06-02")
    changed = repo.update_by_subject_date(
        "IXI001",
        "2026-06-02",
        new_acquisition_date="2026-06-03",
        notes=None,
        status="preprocessed",
    )

    # Assert
    assert created.data.id == 44
    assert loaded.data.acquisition_date == date(2026, 6, 2)
    assert no_changes.data is False
    assert changed.data is True
    assert "acquisition_date = %s" in db.calls[-1][1]
    assert db.calls[-1][2][-2:] == ("IXI001", date(2026, 6, 2))


def test_mri_case_repository_lists_and_deletes_by_subject_date():
    # Arrange
    db = FakeDb()
    repo = MriCaseRepository(db)
    db.fetch_all_result = [
        {"id": 1, "subject_id": "IXI001", "acquisition_date": date(2026, 6, 2), "notes": None, "status": "registered"},
        {"id": 2, "subject_id": "IXI001", "acquisition_date": date(2026, 6, 3), "notes": "n", "status": "done"},
    ]

    # Act
    listed = repo.list_for_subject("IXI001")
    deleted = repo.delete_by_subject_date("IXI001", "2026-06-02")

    # Assert
    assert [case.id for case in listed.data] == [1, 2]
    assert deleted.data is True


def test_subject_access_repository_grants_revokes_and_checks_access():
    # Arrange
    db = FakeDb()
    repo = SubjectAccessRepository(db)
    db.fetch_one_result = {"user_id": 9, "subject_id": "IXI001"}
    db.fetch_all_result = [{"subject_id": "IXI001"}, {"subject_id": "IXI002"}]

    # Act
    granted = repo.grant(9, "IXI001")
    access = repo.get(9, "IXI001")
    subject_ids = repo.list_subject_ids_for_user(9)
    revoked = repo.revoke(9, "IXI001")

    # Assert
    assert granted.data is True
    assert access.data.subject_id == "IXI001"
    assert subject_ids.data == ["IXI001", "IXI002"]
    assert revoked.data is True


def test_subject_access_repository_maps_remaining_access_and_case_access():
    # Arrange
    db = FakeDb()
    repo = SubjectAccessRepository(db)
    db.fetch_all_result = [{"user_id": 2, "subject_id": "IXI001"}]
    db.fetch_one_result = {"has_access": 1}

    # Act
    remaining = repo.list_for_subject_except_user("IXI001", 1)
    has_case_access = repo.user_has_case_access(2, 7)

    # Assert
    assert remaining.data[0].user_id == 2
    assert has_case_access.data is True


def test_subject_search_repository_builds_filters_and_summary_queries():
    # Arrange
    db = FakeDb()
    repo = SubjectSearchRepository(db)
    db.fetch_all_result = [{"subject_id": "IXI001", "case_count": 2}]

    # Act
    rows = repo.search_subject_rows_for_user(
        3,
        subject_id="IXI001",
        acquisition_date="2026-06-02",
        include_cases=False,
    )
    summaries = repo.list_subject_summaries_for_user(3)

    # Assert
    assert rows.data == db.fetch_all_result
    assert summaries.data == db.fetch_all_result
    assert "s.id = %s" in db.calls[0][1]
    assert "c.acquisition_date = %s" in db.calls[0][1]
    assert db.calls[0][2] == (3, "IXI001", date(2026, 6, 2))


def test_auth_session_repository_creates_rotates_and_revokes_sessions():
    # Arrange
    db = FakeDb()
    repo = AuthSessionRepository(db)
    now = datetime(2026, 6, 2)
    db.lastrowid = 12
    db.fetch_one_result = {
        "id": 12,
        "user_id": 4,
        "refresh_token_hash": "hash",
        "created_at": now,
        "expires_at": now + timedelta(days=7),
        "revoked_at": None,
        "last_used_at": None,
    }

    # Act
    created = repo.create(user_id=4, refresh_token_hash="hash", expires_at=now + timedelta(days=7))
    active_by_hash = repo.get_active_by_hash("hash")
    active_by_id = repo.get_active_by_id(session_id=12, user_id=4)
    rotated = repo.rotate(session_id=12, old_refresh_token_hash="hash", new_refresh_token_hash="new", new_expires_at=now)
    revoked = repo.revoke_all_for_user(4)

    # Assert
    assert created.data.id == 12
    assert active_by_hash.data.user_id == 4
    assert active_by_id.data.refresh_token_hash == "hash"
    assert rotated.data is True
    assert revoked.data is True
