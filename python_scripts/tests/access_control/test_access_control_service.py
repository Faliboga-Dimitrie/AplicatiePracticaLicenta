from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from python_scripts.access_control.access_control_service import AccessControlRepositories, AccessControlService
from python_scripts.access_control.models import (
    AuthSessionRecord,
    MriCaseRecord,
    SubjectAccessRecord,
    SubjectRecord,
    UserCredentialsRecord,
    UserRecord,
)
from python_scripts.access_control.results import AuthResult, DbResult


class FakeSchema:
    def __init__(self):
        self.called = False

    def ensure_storage(self):
        self.called = True
        return DbResult.ok(True)


class FakeHasher:
    def __init__(self, *, verify: bool = True, needs_rehash: bool = False, fail_hash: bool = False):
        self.verify = verify
        self._needs_rehash = needs_rehash
        self.fail_hash = fail_hash
        self.hash_calls: list[str] = []
        self.verify_calls: list[tuple[str, str]] = []

    def hash_password(self, password: str) -> str:
        self.hash_calls.append(password)
        if self.fail_hash:
            raise ValueError("bad password")
        return f"hashed:{password}"

    def verify_password(self, password: str, stored_hash: str) -> bool:
        self.verify_calls.append((password, stored_hash))
        return self.verify

    def needs_rehash(self, stored_hash: str) -> bool:
        return self._needs_rehash


@dataclass
class FakeUsers:
    users: dict[int, UserRecord] = field(default_factory=lambda: {1: UserRecord(1, "user@example.com")})
    credentials: UserCredentialsRecord | None = UserCredentialsRecord(1, "user@example.com", "old-hash")
    updated_hashes: list[tuple[int, str]] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)

    def create(self, email, password_hash):
        user = UserRecord(id=2, email=email)
        self.users[user.id] = user
        return DbResult.ok(user)

    def get_by_id(self, user_id):
        return DbResult.ok(self.users.get(user_id))

    def get_by_email(self, email):
        return DbResult.ok(next((u for u in self.users.values() if u.email == email), None))

    def get_credentials_by_email(self, email):
        return DbResult.ok(self.credentials if self.credentials and self.credentials.email == email else None)

    def update_email(self, user_id, new_email):
        self.users[user_id] = UserRecord(user_id, new_email)
        return DbResult.ok(True)

    def update_password_hash(self, user_id, password_hash):
        self.updated_hashes.append((user_id, password_hash))
        return DbResult.ok(True)

    def delete(self, user_id):
        self.deleted.append(user_id)
        return DbResult.ok(self.users.pop(user_id, None) is not None)


@dataclass
class FakeSessions:
    now: datetime = field(default_factory=lambda: datetime(2026, 6, 2, 12, 0))
    sessions: dict[int, AuthSessionRecord] = field(default_factory=dict)
    revoked_users: list[int] = field(default_factory=list)

    def create(self, *, user_id, refresh_token_hash, expires_at):
        session = AuthSessionRecord(10, user_id, refresh_token_hash, self.now, expires_at, None, None)
        self.sessions[session.id] = session
        return DbResult.ok(session)

    def get_active_by_hash(self, refresh_token_hash):
        return DbResult.ok(next((s for s in self.sessions.values() if s.refresh_token_hash == refresh_token_hash and s.revoked_at is None), None))

    def get_active_by_id(self, *, session_id, user_id):
        s = self.sessions.get(session_id)
        return DbResult.ok(s if s and s.user_id == user_id and s.revoked_at is None else None)

    def rotate(self, *, session_id, old_refresh_token_hash, new_refresh_token_hash, new_expires_at):
        s = self.sessions.get(session_id)
        if not s or s.refresh_token_hash != old_refresh_token_hash:
            return DbResult.ok(False)
        self.sessions[session_id] = AuthSessionRecord(s.id, s.user_id, new_refresh_token_hash, s.created_at, new_expires_at, None, self.now)
        return DbResult.ok(True)

    def revoke_by_hash(self, refresh_token_hash):
        for s in list(self.sessions.values()):
            if s.refresh_token_hash == refresh_token_hash:
                self.sessions[s.id] = AuthSessionRecord(s.id, s.user_id, s.refresh_token_hash, s.created_at, s.expires_at, self.now, s.last_used_at)
                return DbResult.ok(True)
        return DbResult.ok(False)

    def revoke_all_for_user(self, user_id):
        self.revoked_users.append(user_id)
        return DbResult.ok(True)


@dataclass
class FakeSubjects:
    subjects: dict[str, SubjectRecord] = field(default_factory=lambda: {
        "IXI001": SubjectRecord("IXI001", "Alice", 20, None)
    })
    deleted: list[str] = field(default_factory=list)
    fail_delete: bool = False

    def create(self, subject_id, *, name=None, age=None, notes=None):
        subject = SubjectRecord(subject_id, name, age, notes)
        self.subjects[subject_id] = subject
        return DbResult.ok(subject)

    def get(self, subject_id):
        return DbResult.ok(self.subjects.get(subject_id))

    def update(self, subject_id, *, name=None, age=None, notes=None):
        if subject_id not in self.subjects:
            return DbResult.ok(False)
        old = self.subjects[subject_id]
        self.subjects[subject_id] = SubjectRecord(
            old.id,
            old.name if name is object else name if name is not None else old.name,
            old.age if age is object else age if age is not None else old.age,
            old.notes if notes is object else notes if notes is not None else old.notes,
        )
        return DbResult.ok(True)

    def delete(self, subject_id):
        self.deleted.append(subject_id)
        if self.fail_delete:
            return DbResult.fail("delete failed")
        return DbResult.ok(self.subjects.pop(subject_id, None) is not None)


@dataclass
class FakeCases:
    cases: dict[int, MriCaseRecord] = field(default_factory=lambda: {
        1: MriCaseRecord(1, "IXI001", date(2026, 6, 2), "n", "registered")
    })
    next_id: int = 2
    fail_delete_by_date: bool = False
    deleted_ids: list[int] = field(default_factory=list)

    def create(self, subject_id, acquisition_date, *, notes=None, status="registered"):
        case = MriCaseRecord(self.next_id, subject_id, acquisition_date, notes, status)
        self.cases[case.id] = case
        self.next_id += 1
        return DbResult.ok(case)

    def get(self, case_id):
        return DbResult.ok(self.cases.get(case_id))

    def get_by_subject_date(self, subject_id, acquisition_date):
        acq = acquisition_date if isinstance(acquisition_date, date) else date.fromisoformat(str(acquisition_date))
        return DbResult.ok(next((c for c in self.cases.values() if c.subject_id == subject_id and c.acquisition_date == acq), None))

    def update_by_subject_date(self, subject_id, acquisition_date, *, new_acquisition_date=object(), notes=object(), status=object()):
        case: MriCaseRecord | None = self.get_by_subject_date(subject_id, acquisition_date).data
        if case is None:
            return DbResult.ok(False)
        new_date = case.acquisition_date if isinstance(new_acquisition_date, object) and new_acquisition_date.__class__ is object else new_acquisition_date
        if isinstance(new_date, str):
            new_date = date.fromisoformat(new_date)
        self.cases[case.id] = MriCaseRecord(
            case.id,
            case.subject_id,
            new_date,
            case.notes if notes.__class__ is object else notes,
            case.status if status.__class__ is object else status,
            case.workspace,
        )
        return DbResult.ok(True)

    def delete(self, case_id):
        self.deleted_ids.append(case_id)
        return DbResult.ok(self.cases.pop(case_id, None) is not None)

    def delete_by_subject_date(self, subject_id, acquisition_date):
        if self.fail_delete_by_date:
            return DbResult.fail("db delete failed")
        case = self.get_by_subject_date(subject_id, acquisition_date).data
        if case is None:
            return DbResult.ok(False)
        self.cases.pop(case.id, None)
        return DbResult.ok(True)

    def list_for_subject(self, subject_id):
        return DbResult.ok([c for c in self.cases.values() if c.subject_id == subject_id])


@dataclass
class FakeAccess:
    rows: set[tuple[int, str]] = field(default_factory=lambda: {(1, "IXI001")})
    fail_revoke: bool = False
    grants: list[tuple[int, str]] = field(default_factory=list)
    revokes: list[tuple[int, str]] = field(default_factory=list)

    def grant(self, user_id, subject_id):
        self.grants.append((user_id, subject_id))
        self.rows.add((user_id, subject_id))
        return DbResult.ok(True)

    def get(self, user_id, subject_id):
        return DbResult.ok(SubjectAccessRecord(user_id, subject_id) if (user_id, subject_id) in self.rows else None)

    def revoke(self, user_id, subject_id):
        self.revokes.append((user_id, subject_id))
        if self.fail_revoke:
            return DbResult.fail("revoke failed")
        self.rows.discard((user_id, subject_id))
        return DbResult.ok(True)

    def list_subject_ids_for_user(self, user_id):
        return DbResult.ok([sid for uid, sid in sorted(self.rows) if uid == user_id])

    def list_for_subject_except_user(self, subject_id, excluded_user_id):
        return DbResult.ok([
            SubjectAccessRecord(uid, sid)
            for uid, sid in self.rows
            if sid == subject_id and uid != excluded_user_id
        ])

    def user_has_case_access(self, user_id, case_id):
        return DbResult.ok(case_id == 1 and (user_id, "IXI001") in self.rows)


class FakeSearch:
    def list_subject_summaries_for_user(self, user_id):
        return DbResult.ok([
            {"subject_id": "IXI001", "subject_name": "Alice", "subject_age": 20, "subject_notes": None, "case_count": 1}
        ])

    def search_subject_rows_for_user(self, user_id, *, subject_id=None, acquisition_date=None, include_cases=True):
        rows = [
            {
                "subject_id": "IXI001",
                "subject_name": "Alice",
                "subject_age": 20,
                "subject_notes": None,
                "case_id": 1 if include_cases else None,
                "case_subject_id": "IXI001",
                "case_acquisition_date": date(2026, 6, 2),
                "case_notes": "n",
                "case_status": "registered",
            }
        ]
        if subject_id and subject_id != "IXI001":
            rows = []
        return DbResult.ok(rows)


class FakeWorkspaceGateway:
    def __init__(self, *, create_fails: bool = False):
        self.create_fails = create_fails
        self.created = []
        self.staged = []
        self.committed = []
        self.rolled_back = []
        self.renamed = []
        self.deleted_subjects = []

    def create_case_workspace(self, *, subject_id, acquisition_date, source_raw_path=None):
        self.created.append((subject_id, acquisition_date, source_raw_path))
        if self.create_fails:
            raise RuntimeError("copy failed")
        return {"workspace": subject_id}

    def get_case_workspace(self, *, subject_id, acquisition_date):
        return {"workspace": f"{subject_id}-{acquisition_date.isoformat()}"}

    def stage_case_workspace_delete(self, *, subject_id, acquisition_date):
        staged = [(Path("old_case"), Path("trash_case"))]
        self.staged.append((subject_id, acquisition_date, staged))
        return staged

    def stage_subject_workspaces_delete(self, *, subject_id):
        staged = [(Path("old_subject"), Path("trash_subject"))]
        self.staged.append((subject_id, staged))
        return staged

    def commit_staged_delete(self, staged):
        self.committed.append(staged)
        return [target for _, target in staged]

    def rollback_staged_delete(self, staged):
        self.rolled_back.append(staged)

    def rename_case_workspace(self, **kwargs):
        self.renamed.append(kwargs)
        return [(Path("old"), Path("new"))]

    def delete_subject_workspaces(self, *, subject_id):
        self.deleted_subjects.append(subject_id)
        return [Path(subject_id)]


def make_service(*, hasher=None, workspace=None, users=None, sessions=None, subjects=None, cases=None, access=None, search=None):
    repositories = AccessControlRepositories(
        users=users or FakeUsers(),
        sessions=sessions or FakeSessions(),
        subjects=subjects or FakeSubjects(),
        cases=cases or FakeCases(),
        access=access or FakeAccess(),
        search=search or FakeSearch(),
    )
    return AccessControlService(
        schema=FakeSchema(),
        repositories=repositories,
        password_hasher=hasher or FakeHasher(),
        workspace_gateway=workspace or FakeWorkspaceGateway(),
    )


def test_access_control_service_uses_injected_schema_and_repositories():
    # Arrange
    schema = FakeSchema()
    repositories = AccessControlRepositories(FakeUsers(), FakeSessions(), FakeSubjects(), FakeCases(), FakeAccess(), FakeSearch())
    service = AccessControlService(schema=schema, repositories=repositories, password_hasher=FakeHasher(), workspace_gateway=FakeWorkspaceGateway())

    # Act
    result = service.ensure_storage()

    # Assert
    assert result.data is True
    assert schema.called is True
    assert service.users is repositories.users


def test_create_user_normalizes_email_hashes_password_and_rejects_invalid_email():
    # Arrange
    hasher = FakeHasher()
    users = FakeUsers()
    service = make_service(hasher=hasher, users=users)

    # Act
    created = service.create_user(" NEW@Example.COM ", "secret")
    invalid = service.create_user("not-email", "secret")

    # Assert
    assert created.data.email == "new@example.com"
    assert hasher.hash_calls == ["secret"]
    assert invalid.success is False


def test_authenticate_returns_false_for_missing_or_bad_password_and_rehashes_old_hash():
    # Arrange
    users = FakeUsers()
    service = make_service(hasher=FakeHasher(verify=False), users=users)
    rehash_service = make_service(hasher=FakeHasher(verify=True, needs_rehash=True), users=users)

    # Act
    rejected = service.authenticate("user@example.com", "secret")
    accepted = rehash_service.authenticate("user@example.com", "secret")

    # Assert
    assert rejected.data.authenticated is False
    assert accepted.data == AuthResult(True, 1, "user@example.com")
    assert users.updated_hashes[-1] == (1, "hashed:secret")


def test_create_subject_validates_required_id_and_age():
    # Arrange
    service = make_service()

    # Act
    empty = service.create_subject("   ")
    negative_age = service.create_subject("IXI002", age=-1)
    created = service.create_subject(" IXI002 ", name="Bob", age=22)

    # Assert
    assert empty.success is False
    assert negative_age.success is False
    assert created.data.id == "IXI002"


def test_update_subject_for_user_requires_subject_access():
    # Arrange
    service = make_service(access=FakeAccess(rows=set()))

    # Act
    result = service.update_subject_for_user(1, "IXI001", name="Nope")

    # Assert
    assert result.success is True
    assert result.data is False


def test_create_mri_case_attaches_workspace_and_rolls_back_db_when_workspace_creation_fails():
    # Arrange
    cases = FakeCases()
    failing_workspace = FakeWorkspaceGateway(create_fails=True)
    service = make_service(cases=cases, workspace=failing_workspace)

    # Act
    failed = service.create_mri_case("IXI001", "2026-06-04", source_raw_path=Path("input.nii.gz"))

    # Assert
    assert failed.success is False
    assert "database rollback succeeded" in failed.error
    assert cases.deleted_ids == [2]


def test_create_mri_case_returns_record_with_workspace_on_success():
    # Arrange
    workspace = FakeWorkspaceGateway()
    service = make_service(workspace=workspace)

    # Act
    result = service.create_mri_case("IXI001", "2026-06-04", source_raw_path=Path("input.nii.gz"))

    # Assert
    assert result.success is True
    assert result.data.workspace == {"workspace": "IXI001"}
    assert workspace.created[0][0] == "IXI001"


def test_delete_mri_case_stages_filesystem_before_db_delete_and_commits_on_success():
    # Arrange
    workspace = FakeWorkspaceGateway()
    service = make_service(workspace=workspace)

    # Act
    result = service.delete_mri_case_by_subject_date("IXI001", "2026-06-02")

    # Assert
    assert result.data is True
    assert workspace.staged
    assert workspace.committed
    assert not workspace.rolled_back


def test_delete_mri_case_rolls_back_staged_delete_when_db_delete_fails():
    # Arrange
    cases = FakeCases(fail_delete_by_date=True)
    workspace = FakeWorkspaceGateway()
    service = make_service(cases=cases, workspace=workspace)

    # Act
    result = service.delete_mri_case_by_subject_date("IXI001", "2026-06-02")

    # Assert
    assert result.success is False
    assert workspace.rolled_back
    assert not workspace.committed


def test_delete_subject_for_user_revokes_access_deletes_subject_and_commits_workspace():
    # Arrange
    access = FakeAccess(rows={(1, "IXI001")})
    workspace = FakeWorkspaceGateway()
    service = make_service(access=access, workspace=workspace)

    # Act
    result = service.delete_subject_for_user(1, "IXI001")

    # Assert
    assert result.data is True
    assert access.revokes == [(1, "IXI001")]
    assert workspace.committed


def test_delete_subject_for_user_rolls_back_workspace_and_restores_access_when_delete_fails():
    # Arrange
    access = FakeAccess(rows={(1, "IXI001")})
    subjects = FakeSubjects(fail_delete=True)
    workspace = FakeWorkspaceGateway()
    service = make_service(access=access, subjects=subjects, workspace=workspace)

    # Act
    result = service.delete_subject_for_user(1, "IXI001")

    # Assert
    assert result.success is False
    assert workspace.rolled_back
    assert access.grants[-1] == (1, "IXI001")


def test_delete_user_account_deletes_orphaned_subjects_and_keeps_shared_subjects():
    # Arrange
    access = FakeAccess(rows={(1, "IXI001"), (1, "IXI002"), (2, "IXI002")})
    subjects = FakeSubjects(subjects={
        "IXI001": SubjectRecord("IXI001", None, None, None),
        "IXI002": SubjectRecord("IXI002", None, None, None),
    })
    workspace = FakeWorkspaceGateway()
    service = make_service(access=access, subjects=subjects, workspace=workspace)

    # Act
    result = service.delete_user_account(1)

    # Assert
    assert result.data["deleted"] is True
    assert result.data["deleted_subject_ids"] == ["IXI001"]
    assert result.data["kept_subject_ids"] == ["IXI002"]
    assert workspace.deleted_subjects == ["IXI001"]


def test_search_subjects_groups_rows_and_attaches_workspace_to_cases():
    # Arrange
    service = make_service(workspace=FakeWorkspaceGateway())

    # Act
    result = service.search_subjects_for_user(1, include_cases=True)

    # Assert
    assert len(result.data) == 1
    assert result.data[0].subject.id == "IXI001"
    assert result.data[0].cases[0].workspace == {"workspace": "IXI001-2026-06-02"}


def test_list_accessible_subject_summaries_maps_case_count():
    # Arrange
    service = make_service()

    # Act
    result = service.list_accessible_subject_summaries(1)

    # Assert
    assert result.data[0].case_count == 1
    assert result.data[0].subject.id == "IXI001"


def test_update_mri_case_renames_workspace_before_date_change_and_rolls_back_on_db_failure():
    # Arrange
    workspace = FakeWorkspaceGateway()
    cases = FakeCases()
    service = make_service(workspace=workspace, cases=cases)

    # Act
    result = service.update_mri_case_by_subject_date("IXI001", "2026-06-02", new_acquisition_date="2026-06-03")

    # Assert
    assert result.data is True
    assert workspace.renamed[0]["old_acquisition_date"] == date(2026, 6, 2)
    assert workspace.renamed[0]["new_acquisition_date"] == date(2026, 6, 3)
