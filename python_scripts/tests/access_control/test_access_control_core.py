from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from python_scripts.access_control.models import (
    SubjectAccessRecord,
    UserRecord,
)
from python_scripts.access_control.password_hashing import PasswordHasher
from python_scripts.access_control.results import AuthResult, DbResult
from python_scripts.access_control.utils import (
    access_from_row,
    auth_session_from_row,
    date_from_db,
    is_valid_email,
    mri_case_from_row,
    normalize_date,
    normalize_email,
    normalize_required_text,
    quote_identifier,
    subject_from_row,
    user_credentials_from_row,
    user_from_row,
)


def test_db_result_factories_store_success_and_failure_payloads():
    # Arrange / Act
    ok = DbResult.ok({"value": 1})
    failed = DbResult.fail("broken")

    # Assert
    assert ok.success is True
    assert ok.data == {"value": 1}
    assert ok.error is None
    assert failed.success is False
    assert failed.data is None
    assert failed.error == "broken"


def test_auth_result_models_authenticated_and_anonymous_outcomes():
    # Arrange / Act
    authenticated = AuthResult(authenticated=True, user_id=7, email="a@b.ro")
    rejected = AuthResult(authenticated=False)

    # Assert
    assert authenticated.user_id == 7
    assert rejected.user_id is None


def test_utils_normalize_validate_and_quote_common_inputs():
    # Arrange / Act / Assert
    assert normalize_email(" USER@Example.COM ") == "user@example.com"
    assert is_valid_email("user@example.com") is True
    assert is_valid_email("missing-at") is False
    assert quote_identifier("subject_access") == "subject_access"
    assert normalize_required_text(" IXI001 ", "subject_id") == "IXI001"

    with pytest.raises(ValueError):
        quote_identifier("subject-access; drop")
    with pytest.raises(ValueError):
        normalize_required_text("   ", "subject_id")


def test_utils_normalize_dates_from_strings_datetimes_and_db_values():
    # Arrange
    value_date = date(2026, 6, 2)
    value_datetime = datetime(2026, 6, 2, 14, 30)

    # Act / Assert
    assert normalize_date("2026-06-02") == value_date
    assert normalize_date(value_date) == value_date
    assert normalize_date(value_datetime) == value_date
    assert date_from_db("2026-06-02") == value_date
    assert date_from_db(value_datetime) == value_date

    with pytest.raises(ValueError):
        normalize_date(object())
    with pytest.raises(ValueError):
        date_from_db(object())


def test_row_mappers_build_typed_records():
    # Arrange
    created_at = datetime(2026, 6, 2, 10, 0)
    expires_at = created_at + timedelta(days=7)

    # Act
    user = user_from_row({"id": "3", "email": "user@example.com"})
    credentials = user_credentials_from_row({"id": 3, "email": "user@example.com", "password_hash": "hash"})
    session = auth_session_from_row({
        "id": 5,
        "user_id": 3,
        "refresh_token_hash": "h",
        "created_at": created_at,
        "expires_at": expires_at,
        "revoked_at": None,
        "last_used_at": None,
    })
    subject = subject_from_row({"id": "IXI001", "name": "Alice", "age": 19, "notes": "n"})
    case = mri_case_from_row({
        "id": 9,
        "subject_id": "IXI001",
        "acquisition_date": "2026-06-02",
        "notes": None,
        "status": "registered",
    })
    access = access_from_row({"user_id": 3, "subject_id": "IXI001"})

    # Assert
    assert user == UserRecord(id=3, email="user@example.com")
    assert credentials.password_hash == "hash"
    assert session.expires_at == expires_at
    assert subject.name == "Alice"
    assert case.case_key == "IXI001_2026-06-02"
    assert access == SubjectAccessRecord(user_id=3, subject_id="IXI001")


def test_password_hasher_hashes_verifies_and_detects_rehash_need():
    # Arrange
    hasher = PasswordHasher(iterations=100_000, salt_bytes=8, dklen=16)

    # Act
    stored = hasher.hash_password("secret")

    # Assert
    assert hasher.verify_password("secret", stored) is True
    assert hasher.verify_password("wrong", stored) is False
    assert hasher.verify_password("secret", "not-a-valid-hash") is False
    assert hasher.needs_rehash(stored) is False
    assert PasswordHasher(iterations=120_000).needs_rehash(stored) is True


def test_password_hasher_rejects_unsafe_configuration_and_empty_password():
    # Arrange / Act / Assert
    with pytest.raises(ValueError):
        PasswordHasher(iterations=99_999)

    with pytest.raises(ValueError):
        PasswordHasher(iterations=100_000).hash_password("")
