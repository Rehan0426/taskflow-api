"""Task endpoints with filtering, sorting, and pagination."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_client_ip, get_project_with_access, get_task_with_access
from app.models import Project, Task, TaskPriority, TaskStatus, TeamMember
from app.schemas import PaginatedResponse, TaskCreateRequest, TaskResponse, TaskUpdateRequest
from app.services import task_service

router = APIRouter(tags=["tasks"])


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    payload: TaskCreateRequest,
    ctx: tuple[Project, TeamMember] = Depends(get_project_with_access),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Create a task in a project (validates that assignee belongs to the team)."""
    project, membership = ctx
    task = task_service.create_task(
        db,
        project=project,
        payload=payload,
        creator_id=membership.user_id,
        ip_address=ip_address,
    )
    return TaskResponse.model_validate(task)


@router.get("/projects/{project_id}/tasks", response_model=PaginatedResponse[TaskResponse])
def list_tasks(
    ctx: tuple[Project, TeamMember] = Depends(get_project_with_access),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = Query(default=None),
    assignee: int | None = Query(default=None),
    due_before: datetime | None = Query(default=None),
    sort_by: Literal["created_at", "due_date", "priority", "status", "title"] = Query(
        default="created_at"
    ),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedResponse[TaskResponse]:
    """List tasks in a project with filters, sorting, and pagination envelope."""
    project, _ = ctx
    items, total = task_service.list_project_tasks(
        db,
        project_id=project.id,
        status=status_filter,
        priority=priority,
        assignee_id=assignee,
        due_before=due_before,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[TaskResponse](
        items=[TaskResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    ctx: tuple[Task, Project, TeamMember] = Depends(get_task_with_access),
) -> TaskResponse:
    """Get a single task by ID."""
    task, _, _ = ctx
    return TaskResponse.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    payload: TaskUpdateRequest,
    ctx: tuple[Task, Project, TeamMember] = Depends(get_task_with_access),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Update a task (member+ allowed; assignee must belong to the team)."""
    task, project, membership = ctx
    updated = task_service.update_task(
        db,
        task=task,
        project=project,
        payload=payload,
        actor_id=membership.user_id,
        ip_address=ip_address,
    )
    return TaskResponse.model_validate(updated)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    ctx: tuple[Task, Project, TeamMember] = Depends(get_task_with_access),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> None:
    """Delete a task (member+ allowed)."""
    task, project, membership = ctx
    task_service.delete_task(
        db,
        task=task,
        project=project,
        actor_id=membership.user_id,
        ip_address=ip_address,
    )
