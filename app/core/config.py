"""Application configuration loaded from environment variables via pydantic-settings.

Why this module exists:
Hardcoding secrets or database URLs in source code is a critical security risk and makes switching
between development, testing, and production painful. `pydantic-settings` validates environment
variables at startup so the app fails fast if a required setting is missing or malformed.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings validated at startup."""

    PROJECT_NAME: str = "TaskFlow API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+psycopg://taskflow:taskflow_secret@localhost:5432/taskflow_db"

    JWT_SECRET_KEY: str = "change-this-in-production-to-a-64-char-random-hex-secret-key-0123456789"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900

    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Ensure JWT secret is at least 32 characters to resist brute-force attacks."""
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long.")
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a clean list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()
