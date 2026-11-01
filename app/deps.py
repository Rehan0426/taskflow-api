"""Reusable FastAPI dependencies for authentication and RBAC authorization.

Why this module exists:
Instead of scattering inline `if user.role != "admin"` checks across route handlers, FastAPI's
dependency injection system lets us declare security requirements (`require_team_role(TeamRole.ADMIN)`)
right in the endpoint signature. Crucially, if a user is NOT a member of a team, we raise 404
(`NotFoundError`) instead of 403 so we never leak the existence of private teams, projects, or tasks.
"""

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import Comment, Project, Task, Team, TeamMember, TeamRole, User

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_RANK: dict[str, int] = {
    TeamRole.MEMBER.value: 1,
    TeamRole.ADMIN.value: 2,
    TeamRole.OWNER.value: 3,
}


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request for rate limiting and audit logging."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate Bearer JWT access token and return the active User ORM instance."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Missing Bearer authentication token")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid subject claim in token") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User account not found or inactive")
    return user


def get_team_membership(
    team_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamMember:
    """Return user's TeamMember record or raise 404 to avoid leaking team existence."""
    team = db.get(Team, team_id)
    if team is None:
        raise NotFoundError("Team not found")

    stmt = select(TeamMember).where(
        TeamMember.team_id == team_id,
        TeamMember.user_id == current_user.id,
    )
    membership = db.scalar(stmt)
    if membership is None:
        # Security requirement: resources of a team the user does not belong to return 404
        raise NotFoundError("Team not found")
    return membership


def require_role(minimum_role: TeamRole) -> Callable[[TeamMember], TeamMember]:
    """Dependency factory enforcing `owner > admin > member` hierarchy on a team route."""

    def _dependency(membership: TeamMember = Depends(get_team_membership)) -> TeamMember:
        user_rank = ROLE_RANK.get(membership.role, 0)
        required_rank = ROLE_RANK[minimum_role.value]
        if user_rank < required_rank:
            raise ForbiddenError(f"Requires at least '{minimum_role.value}' role in this team")
        return membership

    return _dependency


def get_project_with_access(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[Project, TeamMember]:
    """Fetch a project and the current user's membership, returning 404 if not a team member."""
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("Project not found")

    stmt = select(TeamMember).where(
        TeamMember.team_id == project.team_id,
        TeamMember.user_id == current_user.id,
    )
    membership = db.scalar(stmt)
    if membership is None:
        raise NotFoundError("Project not found")
    return project, membership


def require_project_role(
    minimum_role: TeamRole,
) -> Callable[[tuple[Project, TeamMember]], tuple[Project, TeamMember]]:
    """Dependency factory enforcing a minimum team role on `/projects/{project_id}` routes."""

    def _dependency(
        ctx: tuple[Project, TeamMember] = Depends(get_project_with_access),
    ) -> tuple[Project, TeamMember]:
        project, membership = ctx
        if ROLE_RANK.get(membership.role, 0) < ROLE_RANK[minimum_role.value]:
            raise ForbiddenError(f"Requires at least '{minimum_role.value}' role in this team")
        return project, membership

    return _dependency


def get_task_with_access(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[Task, Project, TeamMember]:
    """Fetch a task, its project, and user membership, returning 404 if unauthorized."""
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found")

    project = db.get(Project, task.project_id)
    if project is None:
        raise NotFoundError("Task not found")

    stmt = select(TeamMember).where(
        TeamMember.team_id == project.team_id,
        TeamMember.user_id == current_user.id,
    )
    membership = db.scalar(stmt)
    if membership is None:
        raise NotFoundError("Task not found")
    return task, project, membership


def get_comment_with_access(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[Comment, Task, Project, TeamMember]:
    """Fetch a comment and verify the current user belongs to the parent task's team."""
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("Comment not found")

    task = db.get(Task, comment.task_id)
    if task is None:
        raise NotFoundError("Comment not found")

    project = db.get(Project, task.project_id)
    if project is None:
        raise NotFoundError("Comment not found")

    stmt = select(TeamMember).where(
        TeamMember.team_id == project.team_id,
        TeamMember.user_id == current_user.id,
    )
    membership = db.scalar(stmt)
    if membership is None:
        raise NotFoundError("Comment not found")
    return comment, task, project, membership
