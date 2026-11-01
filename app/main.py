"""FastAPI application entrypoint with lifespan events, CORS, routers, and healthcheck."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import logger, setup_logging
from app.db.session import get_db
from app.routers import audit, auth, comments, projects, tasks, teams, users


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize structured logging on startup and log clean shutdown."""
    setup_logging(debug=settings.DEBUG)
    logger.info("Starting %s in %s mode", settings.PROJECT_NAME, settings.ENVIRONMENT)
    yield
    logger.info("Shutting down %s", settings.PROJECT_NAME)


def create_app() -> FastAPI:
    """Application factory creating and configuring the FastAPI instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="1.0.0",
        description="Team Task Management API with RBAC and Refresh Token Rotation",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(teams.router)
    app.include_router(projects.router)
    app.include_router(tasks.router)
    app.include_router(comments.router)
    app.include_router(audit.router)

    @app.get("/health", tags=["health"])
    def healthcheck(db: Session = Depends(get_db)) -> dict[str, Any]:
        """Liveness and database connectivity check."""
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}

    return app


app = create_app()
