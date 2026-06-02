from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from python_scripts.access_control import AuthResult, AuthSessionRecord, DbResult, UserRecord
from python_scripts.api.errors import (
    error_code_for_status,
    error_payload,
    normalize_error_detail,
    raise_api_error,
    unwrap_bool_result,
    unwrap_result,
)
from python_scripts.api.services.auth import AuthError, AuthService, AuthenticatedSession, TokenService
from python_scripts.api.services.common import mark_case_status_best_effort, require_not_cancelled
from python_scripts.api.services.jobs import JobContext, JobService, JobStatus
from python_scripts.api.upload_validation import safe_nifti_upload_filename


class FakeAccessForAuth:
    def __init__(self):
        self.user = UserRecord(1, "user@example.com")
        self.session = AuthSessionRecord(
            id=11,
            user_id=1,
            refresh_token_hash="initial-hash",
            created_at=datetime(2026, 6, 2),
            expires_at=datetime(2026, 6, 9),
            revoked_at=None,
            last_used_at=None,
        )
        self.rotated: tuple | None = None
        self.revoked_hashes: list[str] = []
        self.revoked_users: list[int] = []
        self.deleted_accounts: list[int] = []
        self.authenticated = True

    def create_user(self, email, password):
        return DbResult.ok(UserRecord(2, email.strip().lower()))

    def authenticate(self, email, password):
        return DbResult.ok(AuthResult(self.authenticated, 1 if self.authenticated else None, "user@example.com" if self.authenticated else None))

    def get_user_by_id(self, user_id):
        return DbResult.ok(self.user if user_id == 1 else None)

    def create_auth_session(self, *, user_id, refresh_token_hash, expires_at):
        self.session = AuthSessionRecord(11, user_id, refresh_token_hash, datetime(2026, 6, 2), expires_at, None, None)
        return DbResult.ok(self.session)

    def get_active_auth_session_by_hash(self, refresh_token_hash):
        return DbResult.ok(self.session if refresh_token_hash == self.session.refresh_token_hash else None)

    def get_active_auth_session_by_id(self, *, session_id, user_id):
        return DbResult.ok(self.session if session_id == self.session.id and user_id == self.session.user_id else None)

    def rotate_auth_session(self, *, session_id, old_refresh_token_hash, new_refresh_token_hash, new_expires_at):
        if old_refresh_token_hash != self.session.refresh_token_hash:
            return DbResult.ok(False)
        self.rotated = (session_id, old_refresh_token_hash, new_refresh_token_hash, new_expires_at)
        self.session = AuthSessionRecord(session_id, self.session.user_id, new_refresh_token_hash, self.session.created_at, new_expires_at, None, datetime(2026, 6, 2))
        return DbResult.ok(True)

    def revoke_auth_session_by_hash(self, refresh_token_hash):
        self.revoked_hashes.append(refresh_token_hash)
        return DbResult.ok(True)

    def revoke_all_auth_sessions_for_user(self, user_id):
        self.revoked_users.append(user_id)
        return DbResult.ok(True)

    def delete_user_account(self, user_id):
        self.deleted_accounts.append(user_id)
        return DbResult.ok({"deleted": True})


def test_token_service_creates_and_verifies_access_tokens():
    # Arrange
    token_service = TokenService(secret_key="secret", access_token_minutes=30)
    user = UserRecord(1, "user@example.com")

    # Act
    token, expires_at = token_service.create_access_token(user, session_id=9)
    payload = token_service.verify_access_token(token)

    # Assert
    assert payload.user_id == 1
    assert payload.email == "user@example.com"
    assert payload.session_id == 9
    assert expires_at > datetime.now(timezone.utc)


def test_token_service_rejects_invalid_signature_issuer_and_expired_tokens():
    # Arrange
    token_service = TokenService(secret_key="secret", access_token_minutes=1)
    token, _ = token_service.create_access_token(UserRecord(1, "user@example.com"), session_id=9)
    header, payload, signature = token.split(".")
    decoded_payload = json.loads(base64.urlsafe_b64decode(payload + "==").decode("utf-8"))
    decoded_payload["iss"] = "someone-else"
    bad_issuer_payload = token_service._b64url_encode(json.dumps(decoded_payload).encode("utf-8"))
    bad_issuer_token = f"{header}.{bad_issuer_payload}.{token_service._sign(f'{header}.{bad_issuer_payload}'.encode('ascii'))}"

    # Act / Assert
    with pytest.raises(AuthError, match="Invalid token signature"):
        token_service.verify_access_token(f"{header}.{payload}.bad")
    with pytest.raises(AuthError, match="Invalid token issuer"):
        token_service.verify_access_token(bad_issuer_token)
    with pytest.raises(AuthError, match="Invalid token format"):
        token_service.verify_access_token("not-a-jwt")

    expired_service = TokenService(secret_key="secret", access_token_minutes=1)
    old_payload = dict(decoded_payload, iss=expired_service.issuer, exp=1, sub="1", email="user@example.com", sid="9")
    old_payload_part = expired_service._b64url_encode(json.dumps(old_payload).encode("utf-8"))
    old_header_part = expired_service._encode_json({"alg": "HS256", "typ": "JWT"})
    old_token = f"{old_header_part}.{old_payload_part}.{expired_service._sign(f'{old_header_part}.{old_payload_part}'.encode('ascii'))}"
    with pytest.raises(AuthError, match="Token expired"):
        expired_service.verify_access_token(old_token)


def test_token_service_refresh_hash_is_stable_and_config_is_validated():
    # Arrange
    token_service = TokenService(secret_key="secret", refresh_token_days=2)

    # Act
    raw, hashed, expires_at = token_service.create_refresh_token()

    # Assert
    assert token_service.hash_refresh_token(raw) == hashed
    assert expires_at > datetime.now(timezone.utc)
    assert token_service.refresh_token_max_age_seconds == 2 * 24 * 60 * 60
    with pytest.raises(ValueError):
        TokenService(secret_key="")
    with pytest.raises(ValueError):
        TokenService(secret_key="secret", access_token_minutes=0)
    with pytest.raises(ValueError):
        TokenService(secret_key="secret", refresh_token_days=0)


def test_auth_service_register_login_refresh_logout_and_current_user():
    # Arrange
    access = FakeAccessForAuth()
    token_service = TokenService(secret_key="secret")
    service = AuthService(access, token_service)

    # Act
    registered = service.register("new@example.com", "pw")
    logged_in = service.login("user@example.com", "pw")
    access.session = AuthSessionRecord(11, 1, token_service.hash_refresh_token(logged_in.data.refresh_token), datetime(2026, 6, 2), datetime(2026, 6, 9), None, None)
    refreshed = service.refresh(logged_in.data.refresh_token)
    current = service.get_current_user(logged_in.data.access_token)
    logged_out = service.logout(refreshed.data.refresh_token)
    all_logged_out = service.logout_all(access.user)
    deleted = service.delete_account(access.user)

    # Assert
    assert isinstance(registered.data, AuthenticatedSession)
    assert logged_in.data.user.email == "user@example.com"
    assert refreshed.data.refresh_token != logged_in.data.refresh_token
    assert current.data == access.user
    assert logged_out.data is True
    assert all_logged_out.data is True
    assert deleted.data == {"deleted": True}


def test_auth_service_returns_none_for_bad_login_or_missing_refresh_token():
    # Arrange
    access = FakeAccessForAuth()
    access.authenticated = False
    service = AuthService(access, TokenService(secret_key="secret"))

    # Act
    login = service.login("user@example.com", "bad")
    refresh = service.refresh(None)
    logout = service.logout(None)

    # Assert
    assert login.data is None
    assert refresh.data is None
    assert logout.data is False


def test_auth_service_current_user_rejects_stale_email_and_inactive_session():
    # Arrange
    access = FakeAccessForAuth()
    token_service = TokenService(secret_key="secret")
    token, _ = token_service.create_access_token(UserRecord(1, "old@example.com"), session_id=11)
    service = AuthService(access, token_service)

    # Act
    stale = service.get_current_user(token)
    invalid = service.get_current_user("not-a-token")

    # Assert
    assert stale.success is False
    assert "stale" in stale.error
    assert invalid.success is False


def test_job_service_runs_successful_jobs_and_records_progress():
    # Arrange
    jobs = JobService(max_workers=1)
    user = UserRecord(1, "user@example.com")
    events = []
    jobs._listeners.append(events.append)

    def handler(context):
        context.checkpoint("half", progress=55)
        return {"ok": True}

    # Act
    started = jobs.start(user=user, job_type="mesh", case_id=4, handler=handler)
    jobs._futures[started.data.id].result(timeout=5)
    finished = jobs.get(started.data.id)

    # Assert
    assert finished.status == JobStatus.COMPLETED
    assert finished.result == {"ok": True}
    assert finished.progress == 100.0
    assert events[0].status == JobStatus.QUEUED
    assert jobs.active_for_case_type(case_id=4, job_type="mesh").data is None


def test_job_service_tracks_active_jobs_and_allows_cancellation():
    # Arrange
    jobs = JobService(max_workers=1)
    user = UserRecord(1, "user@example.com")

    def handler(context):
        while not context.cancel_requested:
            time.sleep(0.01)
        raise RuntimeError("cancelled by test")

    # Act
    started = jobs.start(user=user, job_type="preprocessing", case_id=7, handler=handler)
    active = jobs.active_for_case_type(case_id=7, job_type="preprocessing")
    cancelled = jobs.cancel_for_user(user, started.data.id)
    jobs._futures[started.data.id].result(timeout=5)
    final = jobs.get_for_user(user, started.data.id)

    # Assert
    assert active.data.id == started.data.id
    assert cancelled.data.cancel_requested is True
    assert final.data.status == JobStatus.CANCELLED


def test_job_service_rejects_empty_job_type_and_marks_failed_handlers():
    # Arrange
    jobs = JobService(max_workers=1)
    user = UserRecord(1, "user@example.com")

    # Act
    invalid = jobs.start(user=user, job_type="   ", handler=lambda ctx: None)
    failed = jobs.start(user=user, job_type="bad", handler=lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))
    jobs._futures[failed.data.id].result(timeout=5)
    final = jobs.get(failed.data.id)

    # Assert
    assert invalid.success is False
    assert final.status == JobStatus.FAILED
    assert final.error == "boom"


def test_common_helpers_raise_on_cancellation_and_best_effort_status_ignores_errors():
    # Arrange
    context = Mock(cancel_requested=True)
    cases = Mock()
    cases.set_status_for_user.side_effect = RuntimeError("ignored")

    # Act / Assert
    with pytest.raises(RuntimeError, match="stop"):
        require_not_cancelled(context, "stop")

    mark_case_status_best_effort(cases=cases, user=UserRecord(1, "u@e.ro"), case_id=1, status="failed")
    cases.set_status_for_user.assert_called_once()


def test_error_helpers_normalize_and_raise_http_errors():
    # Arrange / Act
    payload = error_payload("Broken", code="BAD", details={"x": 1})
    normalized_string = normalize_error_detail("Missing", status_code=404)
    normalized_dict = normalize_error_detail(payload, status_code=400)

    # Assert
    assert error_code_for_status(409) == "CONFLICT"
    assert error_code_for_status(499) == "API_ERROR"
    assert payload["error"]["details"] == {"x": 1}
    assert normalized_string["error"]["code"] == "NOT_FOUND"
    assert normalized_dict is payload

    with pytest.raises(HTTPException) as exc:
        raise_api_error(400, "Bad")
    assert exc.value.detail["error"]["message"] == "Bad"


def test_unwrap_result_and_bool_result_raise_http_exceptions_for_failures():
    # Arrange / Act / Assert
    assert unwrap_result(DbResult.ok("value")) == "value"
    assert unwrap_bool_result(DbResult.ok(True)) is True

    with pytest.raises(HTTPException) as failed:
        unwrap_result(DbResult.fail("nope"))
    assert failed.value.status_code == 400

    with pytest.raises(HTTPException) as missing:
        unwrap_result(DbResult.ok(None), not_found_message="Gone")
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as false_result:
        unwrap_bool_result(DbResult.ok(False))
    assert false_result.value.status_code == 404


def test_upload_filename_helper_flattens_paths_and_rejects_non_nifti():
    # Arrange / Act / Assert
    assert safe_nifti_upload_filename("folder\\scan.nii.gz", default="x.nii.gz") == "folder_scan.nii.gz"
    assert safe_nifti_upload_filename("../scan.nii", default="x.nii.gz") == ".._scan.nii"
    assert safe_nifti_upload_filename("   ", default="default.nii.gz") == "default.nii.gz"
    with pytest.raises(ValueError):
        safe_nifti_upload_filename("image.png", default="x.nii.gz")
