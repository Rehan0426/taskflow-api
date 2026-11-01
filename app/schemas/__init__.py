"""Pydantic v2 request and response schemas.

Why this module exists:
Separating Pydantic schemas from SQLAlchemy models guarantees we never accidentally serialize
`hashed_password` or `token_hash` to clients, enforces strict input validation (like email
normalization and password policy), and provides clean OpenAPI documentation.
"""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.password_policy import validate_password_strength
from app.models import TaskPriority, TaskStatus, TeamRole

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response envelope."""

    items: list[T]
    total: int
    limit: int
    offset: int


# --- Auth & User Schemas ---


class UserRegisterRequest(BaseModel):
    """Payload for POST /auth/register."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def check_password_policy(cls, v: str) -> str:
        return validate_password_strength(v)


class UserLoginRequest(BaseModel):
    """Payload for POST /auth/login."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenRefreshRequest(BaseModel):
    """Payload for POST /auth/refresh and POST /auth/logout."""

    refresh_token: str = Field(..., min_length=16)


class TokenPairResponse(BaseModel):
    """JWT access token and opaque refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user profile representation (never includes hashed_password)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


# --- Team & Membership Schemas ---


class TeamCreateRequest(BaseModel):
    """Payload for POST /teams."""

    name: str = Field(..., min_length=1, max_length=120)


class TeamMemberAddRequest(BaseModel):
    """Payload for POST /teams/{id}/members."""

    user_id: int
    role: TeamRole = Field(default=TeamRole.MEMBER)


class TeamMemberRoleUpdateRequest(BaseModel):
    """Payload for PATCH /teams/{id}/members/{user_id}."""

    role: TeamRole


class TeamMemberResponse(BaseModel):
    """Representation of a member inside a team."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    team_id: int
    role: TeamRole
    joined_at: datetime


class TeamResponse(BaseModel):
    """Representation of a team."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    created_at: datetime


# --- Project Schemas ---


class ProjectCreateRequest(BaseModel):
    """Payload for POST /teams/{id}/projects."""

    name: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdateRequest(BaseModel):
    """Payload for PATCH /projects/{id}."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    """Representation of a project."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    team_id: int
    name: str
    description: str | None
    created_by: int | None
    created_at: datetime


# --- Task Schemas ---


class TaskCreateRequest(BaseModel):
    """Payload for POST /projects/{id}/tasks."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    due_date: datetime | None = None
    assignee_id: int | None = None


class TaskUpdateRequest(BaseModel):
    """Payload for PATCH /tasks/{id}."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    assignee_id: int | None = None


class TaskResponse(BaseModel):
    """Representation of a task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: datetime | None
    assignee_id: int | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


# --- Comment Schemas ---


class CommentCreateRequest(BaseModel):
    """Payload for POST /tasks/{id}/comments."""

    text: str = Field(..., min_length=1, max_length=2000)


class CommentUpdateRequest(BaseModel):
    """Payload for PATCH /comments/{id}."""

    text: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    """Representation of a comment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    user_id: int
    text: str
    created_at: datetime
    updated_at: datetime


# --- Audit Log Schemas ---


class AuditLogResponse(BaseModel):
    """Representation of an audit log record."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    user_id: int | None
    team_id: int | None
    action: str
    entity_type: str
    entity_id: int | None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_")
    ip_address: str | None
    created_at: datetime
