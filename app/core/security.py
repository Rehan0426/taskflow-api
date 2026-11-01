"""Cryptographic primitives: Argon2 password hashing, JWT creation/verification, and token hashing.

Why this module exists:
1. Argon2id (via `argon2-cffi`) is the winner of the Password Hashing Competition and resists both
   GPU cracking (via memory hardness) and side-channel attacks.
2. Access tokens are short-lived stateless JWTs (`type="access"`), while refresh tokens are random
   high-entropy strings stored as SHA-256 hashes in PostgreSQL so a database leak cannot be used to
   mint new sessions.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

_ph = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Argon2id with random salt."""
    return _ph.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2 hash in constant time."""
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token with `sub`, `iat`, `exp`, and `type` claims."""
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access JWT, strictly enforcing `type == 'access'`."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type: expected access token")
    return payload


def generate_refresh_token_raw() -> str:
    """Generate a cryptographically secure 48-byte URL-safe refresh token string."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """Compute a deterministic SHA-256 hex digest of a refresh token for safe DB storage."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
