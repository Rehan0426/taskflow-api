"""Project endpoints scoped under teams and top-level project IDs."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import (
    get_client_ip,
    get_project_with_access,
    require_project_role,
    require_role,
)
from app.models import Project, TeamMember, TeamRole
from app.schemas import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services import project_service

router = APIRouter(tags=["projects"])


@router.post(
    "/teams/{team_id}/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    team_id: int,
    payload: ProjectCreateRequest,
    membership: TeamMember = Depends(require_role(TeamRole.MEMBER)),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Create a project inside a team (member+ allowed)."""
    project = project_service.create_project(
        db,
        team_id=team_id,
        payload=payload,
        creator_id=membership.user_id,
        ip_address=ip_address,
    )
    return ProjectResponse.model_validate(project)


@router.get("/teams/{team_id}/projects", response_model=list[ProjectResponse])
def list_projects(
    team_id: int,
    membership: TeamMember = Depends(require_role(TeamRole.MEMBER)),
    db: Session = Depends(get_db),
) -> list[ProjectResponse]:
    """List all projects in a team (member+ allowed)."""
    projects = project_service.list_team_projects(db, team_id=team_id)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(
    ctx: tuple[Project, TeamMember] = Depends(get_project_with_access),
) -> ProjectResponse:
    """Get a single project by ID (returns 404 if user is not in the project's team)."""
    project, _ = ctx
    return ProjectResponse.model_validate(project)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    payload: ProjectUpdateRequest,
    ctx: tuple[Project, TeamMember] = Depends(get_project_with_access),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Update a project's name or description (member+ allowed)."""
    project, membership = ctx
    updated = project_service.update_project(
        db,
        project=project,
        payload=payload,
        actor_id=membership.user_id,
        ip_address=ip_address,
    )
    return ProjectResponse.model_validate(updated)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    ctx: tuple[Project, TeamMember] = Depends(require_project_role(TeamRole.ADMIN)),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> None:
    """Delete a project (admin+ required)."""
    project, membership = ctx
    project_service.delete_project(
        db,
        project=project,
        actor_id=membership.user_id,
        ip_address=ip_address,
    )
