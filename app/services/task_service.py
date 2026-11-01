"""Task and comment domain service with filtering, sorting, pagination, and team-assignee validation."""

from datetime import datetime
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ForbiddenError
from app.models import Comment, Project, Task, TaskPriority, TaskStatus, TeamMember, TeamRole
from app.schemas import (
    CommentCreateRequest,
    CommentUpdateRequest,
    TaskCreateRequest,
    TaskUpdateRequest,
)
from app.services.audit_service import record_audit_log

ALLOWED_SORT_COLUMNS = {
    "created_at": Task.created_at,
    "due_date": Task.due_date,
    "priority": Task.priority,
    "status": Task.status,
    "title": Task.title,
}


def _validate_assignee_in_team(db: Session, team_id: int, assignee_id: int | None) -> None:
    """Ensure the assigned user is a member of the task's parent team."""
    if assignee_id is None:
        return
    stmt = select(TeamMember).where(
        TeamMember.team_id == team_id,
        TeamMember.user_id == assignee_id,
    )
    if db.scalar(stmt) is None:
        raise BadRequestError("Assignee must be a member of the project's team")


def create_task(
    db: Session,
    *,
    project: Project,
    payload: TaskCreateRequest,
    creator_id: int,
    ip_address: str,
) -> Task:
    """Create a task inside a project after verifying assignee membership."""
    _validate_assignee_in_team(db, team_id=project.team_id, assignee_id=payload.assignee_id)

    task = Task(
        project_id=project.id,
        title=payload.title.strip(),
        description=payload.description,
        status=payload.status.value,
        priority=payload.priority.value,
        due_date=payload.due_date,
        assignee_id=payload.assignee_id,
        created_by=creator_id,
    )
    db.add(task)
    db.flush()

    record_audit_log(
        db,
        action="task.create",
        entity_type="task",
        entity_id=task.id,
        user_id=creator_id,
        team_id=project.team_id,
        metadata={"title": task.title, "project_id": project.id},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(task)
    return task


def list_project_tasks(
    db: Session,
    *,
    project_id: int,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assignee_id: int | None = None,
    due_before: datetime | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Task], int]:
    """Filter, sort, and paginate tasks within a project."""
    base_query = select(Task).where(Task.project_id == project_id)

    if status is not None:
        base_query = base_query.where(Task.status == status.value)
    if priority is not None:
        base_query = base_query.where(Task.priority == priority.value)
    if assignee_id is not None:
        base_query = base_query.where(Task.assignee_id == assignee_id)
    if due_before is not None:
        base_query = base_query.where(Task.due_date <= due_before)

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_stmt) or 0

    sort_col = ALLOWED_SORT_COLUMNS.get(sort_by, Task.created_at)
    order_fn = asc if sort_order.lower() == "asc" else desc

    items_stmt = base_query.order_by(order_fn(sort_col), Task.id.asc()).limit(limit).offset(offset)
    items = list(db.scalars(items_stmt).all())
    return items, total


def update_task(
    db: Session,
    *,
    task: Task,
    project: Project,
    payload: TaskUpdateRequest,
    actor_id: int,
    ip_address: str,
) -> Task:
    """Update a task's fields and record an audit log entry."""
    changes: dict[str, Any] = {}
    fields_set = payload.model_fields_set

    if "assignee_id" in fields_set:
        _validate_assignee_in_team(db, team_id=project.team_id, assignee_id=payload.assignee_id)
        task.assignee_id = payload.assignee_id
        changes["assignee_id"] = payload.assignee_id

    if payload.title is not None:
        task.title = payload.title.strip()
        changes["title"] = task.title
    if "description" in fields_set:
        task.description = payload.description
        changes["description"] = payload.description
    if payload.status is not None:
        task.status = payload.status.value
        changes["status"] = task.status
    if payload.priority is not None:
        task.priority = payload.priority.value
        changes["priority"] = task.priority
    if "due_date" in fields_set:
        task.due_date = payload.due_date
        changes["due_date"] = payload.due_date.isoformat() if payload.due_date else None

    record_audit_log(
        db,
        action="task.update",
        entity_type="task",
        entity_id=task.id,
        user_id=actor_id,
        team_id=project.team_id,
        metadata=changes,
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(task)
    return task


def delete_task(
    db: Session,
    *,
    task: Task,
    project: Project,
    actor_id: int,
    ip_address: str,
) -> None:
    """Delete a task and record an audit log entry."""
    record_audit_log(
        db,
        action="task.delete",
        entity_type="task",
        entity_id=task.id,
        user_id=actor_id,
        team_id=project.team_id,
        metadata={"title": task.title, "project_id": project.id},
        ip_address=ip_address,
    )
    db.delete(task)
    db.commit()


def create_comment(
    db: Session,
    *,
    task: Task,
    payload: CommentCreateRequest,
    author_id: int,
) -> Comment:
    """Create a comment on a task."""
    comment = Comment(
        task_id=task.id,
        user_id=author_id,
        text=payload.text.strip(),
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_task_comments(db: Session, task_id: int) -> list[Comment]:
    """List all comments on a task ordered chronologically."""
    stmt = (
        select(Comment)
        .where(Comment.task_id == task_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    )
    return list(db.scalars(stmt).all())


def update_comment(
    db: Session,
    *,
    comment: Comment,
    payload: CommentUpdateRequest,
    actor_id: int,
) -> Comment:
    """Edit a comment (strictly restricted to the comment's original author)."""
    if comment.user_id != actor_id:
        raise ForbiddenError("Comments can only be edited by their author")

    comment.text = payload.text.strip()
    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(
    db: Session,
    *,
    comment: Comment,
    actor_membership: TeamMember,
) -> None:
    """Delete a comment (allowed for the original author OR a team admin/owner)."""
    is_author = comment.user_id == actor_membership.user_id
    is_admin_plus = actor_membership.role in (TeamRole.ADMIN.value, TeamRole.OWNER.value)
    if not (is_author or is_admin_plus):
        raise ForbiddenError("Comments can only be deleted by their author or a team admin/owner")

    db.delete(comment)
    db.commit()
