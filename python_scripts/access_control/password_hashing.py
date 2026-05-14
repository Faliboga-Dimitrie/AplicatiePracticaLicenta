from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


class PasswordHasher:
    """
    Standard-library password hasher based on PBKDF2-HMAC-SHA256.

    Stored format:
        pbkdf2_sha256$iterations$salt_base64$hash_base64

    Argon2id would be preferable if you add an external dependency such as
    argon2-cffi. PBKDF2 is used here to keep the module self-contained.
    """

    algorithm = "pbkdf2_sha256"

    def __init__(
        self,
        *,
        iterations: int = 600_000,
        salt_bytes: int = 16,
        dklen: int = 32,
    ):
        if iterations < 100_000:
            raise ValueError("PasswordHasher iterations should not be below 100_000.")
        self.iterations = iterations
        self.salt_bytes = salt_bytes
        self.dklen = dklen

    def hash_password(self, password: str) -> str:
        self._validate_password(password)
        salt = secrets.token_bytes(self.salt_bytes)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.iterations,
            dklen=self.dklen,
        )
        salt_b64 = base64.b64encode(salt).decode("ascii")
        digest_b64 = base64.b64encode(digest).decode("ascii")
        return f"{self.algorithm}${self.iterations}${salt_b64}${digest_b64}"

    def verify_password(self, password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations_raw, salt_b64, digest_b64 = stored_hash.split("$", 3)
            iterations = int(iterations_raw)
            salt = base64.b64decode(salt_b64.encode("ascii"), validate=True)
            expected_digest = base64.b64decode(digest_b64.encode("ascii"), validate=True)
        except Exception:
            return False

        if algorithm != self.algorithm:
            return False

        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_digest),
        )
        return hmac.compare_digest(actual_digest, expected_digest)

    def needs_rehash(self, stored_hash: str) -> bool:
        try:
            algorithm, iterations_raw, _salt_b64, _digest_b64 = stored_hash.split("$", 3)
            iterations = int(iterations_raw)
        except Exception:
            return True
        return algorithm != self.algorithm or iterations < self.iterations

    def _validate_password(self, password: str) -> None:
        if not isinstance(password, str) or not password:
            raise ValueError("Password must be a non-empty string.")


__all__ = ["PasswordHasher"]
