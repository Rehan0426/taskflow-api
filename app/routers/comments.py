"""Comment endpoints on tasks."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_comment_with_access, get_task_with_access
from app.models import Comment, Project, Task, TeamMember
from app.schemas import CommentCreateRequest, CommentResponse, CommentUpdateRequest
from app.services import task_service

router = APIRouter(tags=["comments"])


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    payload: CommentCreateRequest,
    ctx: tuple[Task, Project, TeamMember] = Depends(get_task_with_access),
    db: Session = Depends(get_db),
) -> CommentResponse:
    """Add a comment to a task (member+ allowed)."""
    task, _, membership = ctx
    comment = task_service.create_comment(
        db,
        task=task,
        payload=payload,
        author_id=membership.user_id,
    )
    return CommentResponse.model_validate(comment)


@router.get("/tasks/{task_id}/comments", response_model=list[CommentResponse])
def list_comments(
    ctx: tuple[Task, Project, TeamMember] = Depends(get_task_with_access),
    db: Session = Depends(get_db),
) -> list[CommentResponse]:
    """List all comments for a task."""
    task, _, _ = ctx
    comments = task_service.list_task_comments(db, task_id=task.id)
    return [CommentResponse.model_validate(c) for c in comments]


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
def update_comment(
    payload: CommentUpdateRequest,
    ctx: tuple[Comment, Task, Project, TeamMember] = Depends(get_comment_with_access),
    db: Session = Depends(get_db),
) -> CommentResponse:
    """Edit a comment (author only)."""
    comment, _, _, membership = ctx
    updated = task_service.update_comment(
        db,
        comment=comment,
        payload=payload,
        actor_id=membership.user_id,
    )
    return CommentResponse.model_validate(updated)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    ctx: tuple[Comment, Task, Project, TeamMember] = Depends(get_comment_with_access),
    db: Session = Depends(get_db),
) -> None:
    """Delete a comment (author or team admin/owner)."""
    comment, _, _, membership = ctx
    task_service.delete_comment(
        db,
        comment=comment,
        actor_membership=membership,
    )
