"""Authentication endpoints: register, login, refresh, logout."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_client_ip
from app.schemas import (
    TokenPairResponse,
    TokenRefreshRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegisterRequest,
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Register a new user account with email normalization and password policy enforcement."""
    user = auth_service.register_user(db, payload, ip_address=ip_address)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenPairResponse)
def login(
    payload: UserLoginRequest,
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    """Verify credentials and issue an access + refresh token pair."""
    return auth_service.login_user(db, payload, ip_address=ip_address)


@router.post("/refresh", response_model=TokenPairResponse)
def refresh_tokens(
    payload: TokenRefreshRequest,
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    """Rotate refresh token and issue a fresh token pair (with reuse detection)."""
    return auth_service.rotate_refresh_token(db, payload.refresh_token, ip_address=ip_address)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: TokenRefreshRequest,
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> None:
    """Revoke the supplied refresh token."""
    auth_service.logout_refresh_token(db, payload.refresh_token, ip_address=ip_address)
