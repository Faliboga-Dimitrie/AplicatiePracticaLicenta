from __future__ import annotations

import io
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from starlette.datastructures import UploadFile

from python_scripts.access_control import DbResult, MriCaseRecord, SubjectRecord, SubjectSummaryRecord, SubjectWithCases, UserRecord
from python_scripts.api.routers import artifacts as artifact_router
from python_scripts.api.routers import auth as auth_router
from python_scripts.api.routers import cases as case_router
from python_scripts.api.routers import health, jobs as job_router, processing as processing_router, public as public_router, subjects as subject_router
from python_scripts.api.schemas import (
    AccountDeletionResponse,
    ApiMessage,
    ArtifactResponse,
    AuthorizedSubjectResponse,
    CaseArtifactsResponse,
    CreateMriCaseRequest,
    CreateSubjectRequest,
    CurrentUserResponse,
    JobResponse,
    LoginRequest,
    LoginResponse,
    MriCaseResponse,
    RegisterRequest,
    SubjectResponse,
    UpdateMriCaseRequest,
    UpdateSubjectRequest,
    UserResponse,
)
from python_scripts.api.services.artifacts import ArtifactFile, CaseArtifactBundle
from python_scripts.api.services.auth import AuthenticatedSession, TokenService
from python_scripts.api.services.jobs import JobRecord, JobStatus
from python_scripts.project_core.artifacts import ArtifactKind, ArtifactRef


USER = UserRecord(1, "user@example.com")
CASE = MriCaseRecord(5, "IXI001", date(2026, 6, 2), "notes", "registered")
SUBJECT = SubjectRecord("IXI001", "Alice", 20, None)
SUBJECT_WITH_CASES = SubjectWithCases(SUBJECT, (CASE,))


def make_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        access_token="access",
        token_type="bearer",
        expires_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
        user=USER,
        refresh_token="refresh",
        refresh_expires_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
    )


class FakeAuthRouterService:
    def __init__(self, result=None):
        self.token_service = TokenService(secret_key="secret")
        self.result = result or DbResult.ok(make_session())
        self.deleted = DbResult.ok({"deleted": True, "deleted_subject_ids": ["IXI001"], "kept_subject_ids": []})

    def register(self, email, password):
        return self.result

    def login(self, email, password):
        return self.result

    def refresh(self, refresh_token):
        return self.result

    def logout(self, refresh_token):
        return DbResult.ok(True)

    def logout_all(self, user):
        return DbResult.ok(True)

    def delete_account(self, user):
        return self.deleted


class CookieRequest:
    def __init__(self, refresh="refresh"):
        self.cookies = {auth_router.REFRESH_TOKEN_COOKIE: refresh}


class FakeSubjectRouterService:
    def list_summaries_for_user(self, user):
        return DbResult.ok([SubjectSummaryRecord(SUBJECT, 1)])

    def get_for_user(self, user, subject_id, *, include_cases=True):
        return DbResult.ok(SUBJECT_WITH_CASES)

    def list_cases_for_subject(self, user, subject_id):
        return DbResult.ok([CASE])

    def create_for_user(self, user, **kwargs):
        return DbResult.ok(SUBJECT_WITH_CASES)

    def update_subject_for_user(self, user, subject_id, **kwargs):
        return DbResult.ok(True)

    def delete_for_user(self, user, subject_id):
        return DbResult.ok(True)


class FakeCaseRouterService:
    def __init__(self):
        self.created_source = None

    def create_for_user(self, user, **kwargs):
        self.created_source = kwargs.get("source_raw_path")
        return DbResult.ok(CASE)

    def get_for_user(self, user, case_id):
        return DbResult.ok(CASE)

    def update_for_user(self, user, case_id, **kwargs):
        return DbResult.ok(CASE)

    def delete_for_user(self, user, case_id):
        return DbResult.ok(CASE)


class FakeJobsRouterService:
    def __init__(self):
        self.job = JobRecord(id="j", type="preprocessing", status=JobStatus.QUEUED, user_id=1, case_id=5, metadata={})

    def list_for_user(self, user, *, case_id=None):
        return DbResult.ok([self.job])

    def get_for_user(self, user, job_id):
        return DbResult.ok(self.job if job_id == "j" else None)

    def cancel_for_user(self, user, job_id):
        return DbResult.ok(self.job if job_id == "j" else None)


class FakeProcessingService:
    ACTIVE_JOB_MESSAGE = "active"

    def __init__(self, result=None):
        self.result = result or DbResult.ok(JobRecord(id="j", type="preprocessing", status=JobStatus.QUEUED, user_id=1, case_id=5, metadata={}))

    def start_for_case(self, user, case_id):
        return self.result


class FakeStatisticsRouterService:
    def metrics_for_case(self, user, case_id):
        return DbResult.ok({"case_id": case_id})

    def evolution_dates_for_subject(self, user, subject_id):
        return DbResult.ok({"subject_id": subject_id, "dates": []})

    def evolution_report_for_subject(self, user, subject_id, *, start_date, end_date):
        return DbResult.ok({"subject_id": subject_id, "start_date": start_date, "end_date": end_date})

    def evolution_visual_for_subject(self, user, subject_id, **kwargs):
        return DbResult.ok(b"glb")


class FakeArtifactRouterService:
    def __init__(self, path):
        artifact = ArtifactFile(ArtifactRef("metrics.json", ArtifactKind.METRICS, "/url", mime_type="application/json"), path, 2)
        self.bundle = CaseArtifactBundle(5, "IXI001", date(2026, 6, 2), "IXI001_2026-06-02", (artifact,))
        self.artifact = artifact

    def list_for_case(self, user, case_id):
        return DbResult.ok(self.bundle)

    def get_file_for_case(self, user, case_id, artifact_name):
        return DbResult.ok(self.artifact if artifact_name == "metrics.json" else None)


@pytest.mark.parametrize(
    "model, kwargs",
    [
        (LoginRequest, {"email": "a@b.ro", "password": "pw"}),
        (RegisterRequest, {"email": "a@b.ro", "password": "pw"}),
        (UserResponse, {"id": 1, "email": "a@b.ro"}),
        (LoginResponse, {"access_token": "a", "expires_at": datetime(2026, 6, 2), "user": {"id": 1, "email": "a@b.ro"}}),
        (CurrentUserResponse, {"user": {"id": 1, "email": "a@b.ro"}}),
        (AccountDeletionResponse, {"deleted": True}),
        (ApiMessage, {"message": "ok"}),
        (CreateSubjectRequest, {"subject_id": "IXI001"}),
        (UpdateSubjectRequest, {"name": "Alice"}),
        (SubjectResponse, {"id": "IXI001"}),
        (MriCaseResponse, {"id": 1, "subject_id": "IXI001", "acquisition_date": date(2026, 6, 2)}),
        (AuthorizedSubjectResponse, {"id": "IXI001", "case_count": 0}),
        (CreateMriCaseRequest, {"subject_id": "IXI001", "acquisition_date": date(2026, 6, 2)}),
        (UpdateMriCaseRequest, {"notes": "n"}),
        (JobResponse, {"id": "j", "type": "t", "status": "queued", "user_id": 1, "created_at": datetime(2026, 6, 2), "metadata": {}}),
        (ArtifactResponse, {"name": "a", "kind": "metrics", "url": "/a", "size_bytes": 1}),
        (CaseArtifactsResponse, {"case_id": 1, "case_key": "k", "subject_id": "IXI001", "acquisition_date": date(2026, 6, 2), "artifacts": []}),
    ],
)
def test_pydantic_schemas_accept_expected_payloads(model, kwargs):
    # Arrange / Act
    instance = model(**kwargs)

    # Assert
    assert instance is not None


def test_auth_router_success_paths_set_and_clear_refresh_cookie():
    # Arrange
    auth = FakeAuthRouterService()
    response = Response()

    # Act
    registered = auth_router.register(RegisterRequest(email="a@b.ro", password="pw"), response, auth)
    logged_in = auth_router.login(LoginRequest(email="a@b.ro", password="pw"), Response(), auth)
    refreshed = auth_router.refresh(CookieRequest(), Response(), auth)
    me = auth_router.me(USER)
    logged_out = auth_router.logout(CookieRequest(), Response(), auth)
    all_out = auth_router.logout_all(Response(), USER, auth)
    deleted = auth_router.delete_account(Response(), USER, auth)

    # Assert
    assert registered.access_token == "access"
    assert logged_in.user.email == USER.email
    assert refreshed.token_type == "bearer"
    assert me.user.id == 1
    assert logged_out == {"logged_out": True}
    assert all_out == {"logged_out": True, "all_sessions": True}
    assert deleted.deleted_subject_ids == ["IXI001"]


def test_auth_router_raises_for_failed_register_login_refresh_and_logout():
    # Arrange
    response = Response()

    # Act / Assert
    with pytest.raises(HTTPException):
        auth_router.register(RegisterRequest(email="a@b.ro", password="pw"), response, FakeAuthRouterService(DbResult.fail("Duplicate")))
    with pytest.raises(HTTPException):
        auth_router.login(LoginRequest(email="a@b.ro", password="pw"), response, FakeAuthRouterService(DbResult.ok(None)))
    with pytest.raises(HTTPException):
        auth_router.refresh(CookieRequest(), response, FakeAuthRouterService(DbResult.ok(None)))

    failing_auth = FakeAuthRouterService()
    failing_auth.logout = lambda token: DbResult.fail("logout failed")
    with pytest.raises(HTTPException):
        auth_router.logout(CookieRequest(), response, failing_auth)


def test_subject_router_success_and_failure_paths():
    # Arrange
    service = FakeSubjectRouterService()

    # Act
    listed = subject_router.list_subjects(USER, service)
    loaded = subject_router.get_subject("IXI001", USER, service)
    cases = subject_router.list_subject_cases("IXI001", USER, service)
    created = subject_router.create_subject(CreateSubjectRequest(subject_id="IXI001"), USER, service)
    updated = subject_router.update_subject("IXI001", UpdateSubjectRequest(name="New"), USER, service)
    deleted = subject_router.delete_subject("IXI001", USER, service)

    # Assert
    assert listed[0]["id"] == "IXI001"
    assert loaded["case_count"] == 1
    assert cases[0]["id"] == 5
    assert created["id"] == "IXI001"
    assert updated["updated"] is True
    assert deleted == {"deleted": True, "subject_id": "IXI001"}

    service.get_for_user = Mock(return_value=DbResult.ok(None))
    with pytest.raises(HTTPException):
        subject_router.get_subject("missing", USER, service)


def test_case_router_success_paths_and_upload(tmp_path):
    # Arrange
    service = FakeCaseRouterService()
    upload = UploadFile(filename="scan.nii.gz", file=io.BytesIO(b"nii"))

    # Act
    created_upload = case_router.create_case_with_upload(
        subject_id="IXI001",
        acquisition_date=date(2026, 6, 2),
        notes="n",
        status="registered",
        file=upload,
        current_user=USER,
        cases=service,
    )
    loaded = case_router.get_case(5, USER, service)
    updated = case_router.update_case(5, UpdateMriCaseRequest(notes="n"), USER, service)
    deleted = case_router.delete_case(5, USER, service)

    # Assert
    assert created_upload["created"] is True
    assert service.created_source is not None
    assert loaded["id"] == 5
    assert updated["updated"] is True
    assert deleted["deleted"] is True


def test_case_router_rejects_invalid_upload_filename():
    # Arrange
    service = FakeCaseRouterService()
    upload = UploadFile(filename="scan.png", file=io.BytesIO(b"png"))

    # Act / Assert
    with pytest.raises(HTTPException):
        case_router.create_case_with_upload(
            subject_id="IXI001",
            acquisition_date=date(2026, 6, 2),
            file=upload,
            current_user=USER,
            cases=service,
        )


def test_job_router_lists_gets_and_cancels_jobs():
    # Arrange
    jobs = FakeJobsRouterService()

    # Act
    listed = job_router.list_jobs(case_id=5, current_user=USER, jobs=jobs)
    loaded = job_router.get_job("j", USER, jobs)
    cancelled = job_router.cancel_job("j", USER, jobs)

    # Assert
    assert listed[0]["id"] == "j"
    assert loaded["id"] == "j"
    assert cancelled["id"] == "j"

    with pytest.raises(HTTPException):
        job_router.get_job("missing", USER, jobs)


def test_artifact_router_lists_metrics_and_returns_file_response(tmp_path):
    # Arrange
    path = tmp_path / "metrics.json"
    path.write_text("{}")
    service = FakeArtifactRouterService(path)
    stats = FakeStatisticsRouterService()

    # Act
    listed = artifact_router.list_case_artifacts(5, USER, service)
    metrics = artifact_router.get_case_metrics(5, USER, stats)
    file_response = artifact_router.get_case_artifact(5, "metrics.json", USER, service)

    # Assert
    assert listed["case_id"] == 5
    assert listed["artifacts"][0]["name"] == "metrics.json"
    assert metrics == {"case_id": 5}
    assert file_response.path == path


def test_health_and_public_router_behaviour():
    # Arrange / Act
    api_info = health.api_info()
    health_status = health.health_check()

    # Assert
    assert api_info["docs"] == "/docs"
    assert health_status == {"status": "ok"}
