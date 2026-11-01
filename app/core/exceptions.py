"""Custom application exceptions and global FastAPI exception handlers.

Why this module exists:
Default framework errors often expose internal validation shapes or vary across endpoints.
Using a single `AppError` hierarchy and registering global handlers guarantees every client
receives a predictable `{"code": "...", "message": "...", "details": ...}` JSON envelope
and prevents raw stack traces from leaking to clients on 500 errors.
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import logger


class AppError(Exception):
    """Base exception for domain and HTTP errors."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


class NotFoundError(AppError):
    """404 Not Found — also used when hiding existence of unauthorized team resources."""

    def __init__(self, message: str = "Resource not found", details: Any = None) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, "NOT_FOUND", message, details)


class ForbiddenError(AppError):
    """403 Forbidden — user belongs to the team but lacks the required role/permission."""

    def __init__(self, message: str = "Insufficient permissions", details: Any = None) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, "FORBIDDEN", message, details)


class UnauthorizedError(AppError):
    """401 Unauthorized — missing, invalid, expired, or revoked credentials."""

    def __init__(
        self, message: str = "Invalid or expired credentials", details: Any = None
    ) -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            "UNAUTHORIZED",
            message,
            details,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ConflictError(AppError):
    """409 Conflict — duplicate email or existing team membership."""

    def __init__(self, message: str = "Resource conflict", details: Any = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, "CONFLICT", message, details)


class BadRequestError(AppError):
    """400 Bad Request — domain rule violation (e.g., demoting team owner)."""

    def __init__(self, message: str = "Invalid request", details: Any = None) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, "BAD_REQUEST", message, details)


class RateLimitError(AppError):
    """429 Too Many Requests — login rate limit exceeded."""

    def __init__(self, retry_after: int, message: str = "Too many failed login attempts") -> None:
        super().__init__(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            message,
            details={"retry_after_seconds": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach consistent JSON error handlers to the FastAPI application."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized_errors = [
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": sanitized_errors,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal error occurred",
                "details": None,
            },
        )
