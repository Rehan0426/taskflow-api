"""Audit logging service for recording security and resource lifecycle events.

Why this module exists:
Centralizing audit log writes ensures every sensitive operation records who did what, on which
entity, from what IP address, and with what metadata—making security reviews and debugging easy.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    user_id: int | None = None,
    team_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """Create and flush an AuditLog entry within the current database transaction."""
    entry = AuditLog(
        user_id=user_id,
        team_id=team_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=metadata,
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()
    return entry


def list_team_audit_logs(
    db: Session,
    *,
    team_id: int,
    action: str | None = None,
    entity_type: str | None = None,
    user_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """Query paginated and filtered audit logs for a specific team."""
    base_query = select(AuditLog).where(AuditLog.team_id == team_id)
    if action:
        base_query = base_query.where(AuditLog.action == action)
    if entity_type:
        base_query = base_query.where(AuditLog.entity_type == entity_type)
    if user_id is not None:
        base_query = base_query.where(AuditLog.user_id == user_id)

    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_stmt) or 0

    items_stmt = (
        base_query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.scalars(items_stmt).all())
    return items, total
