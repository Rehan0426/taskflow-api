"""Team audit log endpoints (admin+ only)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import require_role
from app.models import TeamMember, TeamRole
from app.schemas import AuditLogResponse, PaginatedResponse
from app.services import audit_service

router = APIRouter(tags=["audit"])


@router.get("/teams/{team_id}/audit-logs", response_model=PaginatedResponse[AuditLogResponse])
def get_team_audit_logs(
    team_id: int,
    membership: TeamMember = Depends(require_role(TeamRole.ADMIN)),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuditLogResponse]:
    """List filterable, paginated audit logs for a team (admin+ required)."""
    items, total = audit_service.list_team_audit_logs(
        db,
        team_id=team_id,
        action=action,
        entity_type=entity_type,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse[AuditLogResponse](
        items=[AuditLogResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
