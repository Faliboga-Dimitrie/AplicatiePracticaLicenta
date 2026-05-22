from __future__ import annotations

import base64
import hashlib
import hmac
import json
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


class TokenService:
    """
    Small HS256 bearer-token service.

    This intentionally uses only the Python standard library, so the project does
    not need PyJWT/python-jose yet. The token format is JWT-compatible enough for
    our own backend: header.payload.signature, signed with HMAC-SHA256.

    React does not need to understand the token contents. It only stores the
    string and sends it back as:

        Authorization: Bearer <token>
    """

    def __init__(
        self,
        *,
        secret_key: str,
        issuer: str = "brain-mri-api",
        access_token_minutes: int = 8 * 60,
    ):
        if not secret_key:
            raise ValueError("secret_key must not be empty.")
        if access_token_minutes <= 0:
            raise ValueError("access_token_minutes must be positive.")

        self.secret_key = secret_key.encode("utf-8")
        self.issuer = issuer
        self.access_token_minutes = access_token_minutes

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

    AccessControlService remains responsible for checking email/password.
    AuthService is responsible for web concerns: login response, bearer-token
    creation, bearer-token verification, and loading the current user.
    """

    def __init__(
        self,
        access: AccessControlService,
        token_service: TokenService,
    ):
        self.access = access
        self.token_service = token_service

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

        token, expires_at = self.token_service.create_access_token(user_result.data)
        return DbResult.ok(
            AuthenticatedSession(
                access_token=token,
                token_type="bearer",
                expires_at=expires_at,
                user=user_result.data,
            )
        )

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


__all__ = [
    "AuthError",
    "AuthenticatedSession",
    "AuthService",
    "TokenPayload",
    "TokenService",
]
