"""Authentication service: registration, login with rate-limiting, refresh rotation, and reuse detection.

Why this module exists:
Implements the OAuth2 / OIDC best-practice Refresh Token Rotation with Token Family Reuse Detection:
- Every login creates a new `family_id` (UUID4) and stores only the SHA-256 hash of the refresh token.
- Calling `/auth/refresh` marks the current refresh token as `revoked=True` and issues a fresh pair
  under the same `family_id`.
- If an attacker steals an old refresh token and either the attacker or the legitimate user tries to
  use a token that is ALREADY marked `revoked=True`, the server immediately revokes EVERY token in
  that `family_id`, logs a `auth.token_reuse_detected` security event, and forces re-authentication.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.logging import logger
from app.core.rate_limit import login_rate_limiter
from app.core.security import (
    create_access_token,
    generate_refresh_token_raw,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas import TokenPairResponse, UserLoginRequest, UserRegisterRequest
from app.services.audit_service import record_audit_log

GENERIC_LOGIN_ERROR = "Invalid email or password"


def register_user(db: Session, payload: UserRegisterRequest, ip_address: str) -> User:
    """Register a new user account with a lowercase email and Argon2id password hash."""
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise ConflictError("An account with this email already exists")

    user = User(
        email=payload.email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()

    record_audit_log(
        db,
        action="auth.register",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"email": user.email},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(user)
    return user


def _issue_token_pair(db: Session, user_id: int, family_id: str) -> TokenPairResponse:
    """Create a new access token and persist a hashed refresh token in the given family."""
    access_token = create_access_token(user_id=user_id)
    raw_refresh = generate_refresh_token_raw()
    token_hash = hash_refresh_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    db_token = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id,
        expires_at=expires_at,
        revoked=False,
    )
    db.add(db_token)
    db.flush()
    return TokenPairResponse(access_token=access_token, refresh_token=raw_refresh)


def login_user(db: Session, payload: UserLoginRequest, ip_address: str) -> TokenPairResponse:
    """Authenticate a user with rate limiting and generic failure messages."""
    rate_key = f"{ip_address}:{payload.email}"
    login_rate_limiter.check_or_raise(rate_key)

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        login_rate_limiter.record_failure(rate_key)
        logger.warning("Failed login attempt for email=%s from ip=%s", payload.email, ip_address)
        record_audit_log(
            db,
            action="auth.login_failure",
            entity_type="user",
            entity_id=user.id if user else None,
            user_id=user.id if user else None,
            metadata={"email": payload.email},
            ip_address=ip_address,
        )
        db.commit()
        raise UnauthorizedError(GENERIC_LOGIN_ERROR)

    if not user.is_active:
        raise UnauthorizedError(GENERIC_LOGIN_ERROR)

    login_rate_limiter.reset(rate_key)
    family_id = str(uuid.uuid4())
    tokens = _issue_token_pair(db, user_id=user.id, family_id=family_id)

    record_audit_log(
        db,
        action="auth.login_success",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        metadata={"family_id": family_id},
        ip_address=ip_address,
    )
    db.commit()
    return tokens


def rotate_refresh_token(db: Session, raw_refresh_token: str, ip_address: str) -> TokenPairResponse:
    """Rotate a valid refresh token, or revoke the entire token family if reuse is detected."""
    token_hash = hash_refresh_token(raw_refresh_token)
    stored_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))

    if stored_token is None:
        raise UnauthorizedError("Invalid refresh token")

    # Reuse Detection: if a previously rotated/revoked token is presented again, compromise is assumed
    if stored_token.revoked:
        logger.error(
            "Refresh token reuse detected! user_id=%s family_id=%s ip=%s",
            stored_token.user_id,
            stored_token.family_id,
            ip_address,
        )
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored_token.family_id)
            .values(revoked=True)
        )
        record_audit_log(
            db,
            action="auth.token_reuse_detected",
            entity_type="refresh_token",
            entity_id=stored_token.id,
            user_id=stored_token.user_id,
            metadata={"family_id": stored_token.family_id},
            ip_address=ip_address,
        )
        db.commit()
        raise UnauthorizedError("Refresh token reuse detected; session family revoked")

    now = datetime.now(UTC)
    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= now:
        stored_token.revoked = True
        db.commit()
        raise UnauthorizedError("Refresh token has expired")

    user = db.get(User, stored_token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User account is inactive")

    # Mark current token revoked and mint a new pair in the same family
    stored_token.revoked = True
    new_tokens = _issue_token_pair(db, user_id=user.id, family_id=stored_token.family_id)
    db.commit()
    return new_tokens


def logout_refresh_token(db: Session, raw_refresh_token: str, ip_address: str) -> None:
    """Revoke the provided refresh token on logout."""
    token_hash = hash_refresh_token(raw_refresh_token)
    stored_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    if stored_token is None:
        raise UnauthorizedError("Invalid refresh token")

    stored_token.revoked = True
    record_audit_log(
        db,
        action="auth.logout",
        entity_type="refresh_token",
        entity_id=stored_token.id,
        user_id=stored_token.user_id,
        metadata={"family_id": stored_token.family_id},
        ip_address=ip_address,
    )
    db.commit()
