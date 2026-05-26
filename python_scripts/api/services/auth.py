from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ...access_control import AccessControlService, DbResult, UserRecord


class AuthError(RuntimeError):
    """Raised when a bearer token is missing, malformed, expired, or invalid."""


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    email: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    access_token: str
    token_type: str
    expires_at: datetime
    user: UserRecord
    refresh_token: str | None = None
    refresh_expires_at: datetime | None = None


class TokenService:
    """
    Small HS256 bearer-token service plus refresh-token helpers.

    Access tokens are signed, stateless bearer tokens used on normal API calls.
    Refresh tokens are random opaque strings. The raw refresh token is sent only
    to the browser as an HttpOnly cookie; the database stores only an HMAC hash.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        issuer: str = "brain-mri-api",
        access_token_minutes: int = 8 * 60,
        refresh_token_days: int = 7,
    ):
        if not secret_key:
            raise ValueError("secret_key must not be empty.")
        if access_token_minutes <= 0:
            raise ValueError("access_token_minutes must be positive.")
        if refresh_token_days <= 0:
            raise ValueError("refresh_token_days must be positive.")

        self.secret_key = secret_key.encode("utf-8")
        self.issuer = issuer
        self.access_token_minutes = access_token_minutes
        self.refresh_token_days = refresh_token_days

    @property
    def refresh_token_max_age_seconds(self) -> int:
        return int(timedelta(days=self.refresh_token_days).total_seconds())

    def create_access_token(self, user: UserRecord) -> tuple[str, datetime]:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.access_token_minutes)

        header = {
            "alg": "HS256",
            "typ": "JWT",
        }
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": self.issuer,
        }

        header_part = self._encode_json(header)
        payload_part = self._encode_json(payload)
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        signature_part = self._sign(signing_input)

        return f"{header_part}.{payload_part}.{signature_part}", expires_at

    def verify_access_token(self, token: str) -> TokenPayload:
        try:
            header_part, payload_part, signature_part = token.split(".", 2)
        except ValueError as exc:
            raise AuthError("Invalid token format.") from exc

        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected_signature = self._sign(signing_input)

        if not hmac.compare_digest(signature_part, expected_signature):
            raise AuthError("Invalid token signature.")

        header = self._decode_json(header_part)
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise AuthError("Unsupported token header.")

        payload = self._decode_json(payload_part)

        if payload.get("iss") != self.issuer:
            raise AuthError("Invalid token issuer.")

        try:
            user_id = int(payload["sub"])
            email = str(payload["email"])
            exp = int(payload["exp"])
        except Exception as exc:
            raise AuthError("Invalid token payload.") from exc

        expires_at = datetime.fromtimestamp(exp, timezone.utc)
        if datetime.now(timezone.utc) >= expires_at:
            raise AuthError("Token expired.")

        return TokenPayload(
            user_id=user_id,
            email=email,
            expires_at=expires_at,
        )

    def create_refresh_token(self) -> tuple[str, str, datetime]:
        """Return raw refresh token, database hash, and UTC expiration."""
        raw_token = secrets.token_urlsafe(64)
        token_hash = self.hash_refresh_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_days)
        return raw_token, token_hash, expires_at

    def hash_refresh_token(self, refresh_token: str) -> str:
        digest = hmac.new(
            self.secret_key,
            refresh_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest

    def _sign(self, signing_input: bytes) -> str:
        digest = hmac.new(self.secret_key, signing_input, hashlib.sha256).digest()
        return self._b64url_encode(digest)

    def _encode_json(self, value: dict[str, Any]) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return self._b64url_encode(raw)

    def _decode_json(self, value: str) -> dict[str, Any]:
        try:
            raw = self._b64url_decode(value)
            decoded = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise AuthError("Invalid token JSON.") from exc

        if not isinstance(decoded, dict):
            raise AuthError("Invalid token JSON payload.")
        return decoded

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))


class AuthService:
    """
    Web-facing authentication service.

    AccessControlService remains responsible for checking email/password and
    storing refresh sessions. AuthService handles web auth semantics: access
    token creation, refresh-token rotation, and current-user loading.
    """

    def __init__(
        self,
        access: AccessControlService,
        token_service: TokenService,
    ):
        self.access = access
        self.token_service = token_service


    def register(self, email: str, password: str) -> DbResult[AuthenticatedSession]:
        created = self.access.create_user(email, password)
        if not created.success:
            return DbResult.fail(created.error or "Could not create user.")
        if created.data is None:
            return DbResult.fail("User was not created.")
        return self._create_session_for_user(created.data)

    def login(self, email: str, password: str) -> DbResult[AuthenticatedSession]:
        auth_result = self.access.authenticate(email, password)
        if not auth_result.success:
            return DbResult.fail(auth_result.error or "Authentication failed.")

        auth = auth_result.data
        if auth is None or not auth.authenticated or auth.user_id is None:
            return DbResult.ok(None)

        user_result = self.access.get_user_by_id(auth.user_id)
        if not user_result.success:
            return DbResult.fail(user_result.error or "Could not load authenticated user.")
        if user_result.data is None:
            return DbResult.fail("Authenticated user no longer exists.")

        return self._create_session_for_user(user_result.data)

    def refresh(self, refresh_token: str | None) -> DbResult[AuthenticatedSession]:
        if not refresh_token:
            return DbResult.ok(None)

        old_hash = self.token_service.hash_refresh_token(refresh_token)
        session_result = self.access.get_active_auth_session_by_hash(old_hash)
        if not session_result.success:
            return DbResult.fail(session_result.error or "Could not load refresh session.")
        if session_result.data is None:
            return DbResult.ok(None)

        user_result = self.access.get_user_by_id(session_result.data.user_id)
        if not user_result.success:
            return DbResult.fail(user_result.error or "Could not load refresh-session user.")
        if user_result.data is None:
            return DbResult.ok(None)

        new_refresh_token, new_refresh_hash, new_refresh_expires_at = self.token_service.create_refresh_token()
        rotated = self.access.rotate_auth_session(
            session_id=session_result.data.id,
            old_refresh_token_hash=old_hash,
            new_refresh_token_hash=new_refresh_hash,
            new_expires_at=self._to_database_datetime(new_refresh_expires_at),
        )
        if not rotated.success:
            return DbResult.fail(rotated.error or "Could not rotate refresh session.")
        if not rotated.data:
            # A concurrent refresh may already have rotated or revoked this token.
            return DbResult.ok(None)

        access_token, access_expires_at = self.token_service.create_access_token(user_result.data)
        return DbResult.ok(
            AuthenticatedSession(
                access_token=access_token,
                token_type="bearer",
                expires_at=access_expires_at,
                user=user_result.data,
                refresh_token=new_refresh_token,
                refresh_expires_at=new_refresh_expires_at,
            )
        )

    def logout(self, refresh_token: str | None) -> DbResult[bool]:
        if not refresh_token:
            return DbResult.ok(False)

        token_hash = self.token_service.hash_refresh_token(refresh_token)
        return self.access.revoke_auth_session_by_hash(token_hash)

    def logout_all(self, user: UserRecord) -> DbResult[bool]:
        return self.access.revoke_all_auth_sessions_for_user(user.id)

    def get_current_user(self, token: str) -> DbResult[UserRecord]:
        try:
            payload = self.token_service.verify_access_token(token)
        except AuthError as exc:
            return DbResult.fail(str(exc))

        user_result = self.access.get_user_by_id(payload.user_id)
        if not user_result.success:
            return DbResult.fail(user_result.error or "Could not load current user.")
        if user_result.data is None:
            return DbResult.fail("User no longer exists.")

        # Optional sanity check: a token for an old email should stop working
        # after the user email changes.
        if user_result.data.email != payload.email:
            return DbResult.fail("Token user data is stale.")

        return DbResult.ok(user_result.data)

    def _create_session_for_user(self, user: UserRecord) -> DbResult[AuthenticatedSession]:
        access_token, access_expires_at = self.token_service.create_access_token(user)
        refresh_token, refresh_hash, refresh_expires_at = self.token_service.create_refresh_token()

        session_result = self.access.create_auth_session(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            expires_at=self._to_database_datetime(refresh_expires_at),
        )
        if not session_result.success:
            return DbResult.fail(session_result.error or "Could not create refresh session.")

        return DbResult.ok(
            AuthenticatedSession(
                access_token=access_token,
                token_type="bearer",
                expires_at=access_expires_at,
                user=user,
                refresh_token=refresh_token,
                refresh_expires_at=refresh_expires_at,
            )
        )

    @staticmethod
    def _to_database_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)


__all__ = [
    "AuthError",
    "AuthenticatedSession",
    "AuthService",
    "TokenPayload",
    "TokenService",
]
