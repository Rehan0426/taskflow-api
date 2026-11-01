"""Project domain service for creating, listing, updating, and deleting team projects."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.schemas import ProjectCreateRequest, ProjectUpdateRequest
from app.services.audit_service import record_audit_log


def create_project(
    db: Session,
    *,
    team_id: int,
    payload: ProjectCreateRequest,
    creator_id: int,
    ip_address: str,
) -> Project:
    """Create a new project under a team and write an audit log entry."""
    project = Project(
        team_id=team_id,
        name=payload.name.strip(),
        description=payload.description,
        created_by=creator_id,
    )
    db.add(project)
    db.flush()

    record_audit_log(
        db,
        action="project.create",
        entity_type="project",
        entity_id=project.id,
        user_id=creator_id,
        team_id=team_id,
        metadata={"name": project.name},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(project)
    return project


def list_team_projects(db: Session, team_id: int) -> list[Project]:
    """List all projects belonging to a team."""
    stmt = select(Project).where(Project.team_id == team_id).order_by(Project.id.asc())
    return list(db.scalars(stmt).all())


def update_project(
    db: Session,
    *,
    project: Project,
    payload: ProjectUpdateRequest,
    actor_id: int,
    ip_address: str,
) -> Project:
    """Update mutable fields on a project and record an audit log entry."""
    changes: dict[str, str | None] = {}
    if payload.name is not None:
        project.name = payload.name.strip()
        changes["name"] = project.name
    if "description" in payload.model_fields_set:
        project.description = payload.description
        changes["description"] = project.description

    record_audit_log(
        db,
        action="project.update",
        entity_type="project",
        entity_id=project.id,
        user_id=actor_id,
        team_id=project.team_id,
        metadata=changes,
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(project)
    return project


def delete_project(
    db: Session,
    *,
    project: Project,
    actor_id: int,
    ip_address: str,
) -> None:
    """Delete a project (admin+ required) and record an audit log entry."""
    record_audit_log(
        db,
        action="project.delete",
        entity_type="project",
        entity_id=project.id,
        user_id=actor_id,
        team_id=project.team_id,
        metadata={"name": project.name},
        ip_address=ip_address,
    )
    db.delete(project)
    db.commit()
