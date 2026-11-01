"""Team and membership domain service.

Why this module exists:
Enforces core team invariants in one place:
1. Creating a team automatically adds the creator as `TeamRole.OWNER`.
2. Exactly one owner exists per team.
3. The team owner cannot be removed or demoted.
4. Only owners can promote/demote members; admins can only add/remove regular members.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models import Team, TeamMember, TeamRole, User
from app.schemas import TeamCreateRequest, TeamMemberAddRequest, TeamMemberRoleUpdateRequest
from app.services.audit_service import record_audit_log


def create_team(db: Session, payload: TeamCreateRequest, owner: User, ip_address: str) -> Team:
    """Create a new team and enroll its creator as the single owner."""
    team = Team(name=payload.name.strip(), owner_id=owner.id)
    db.add(team)
    db.flush()

    membership = TeamMember(user_id=owner.id, team_id=team.id, role=TeamRole.OWNER.value)
    db.add(membership)

    record_audit_log(
        db,
        action="team.create",
        entity_type="team",
        entity_id=team.id,
        user_id=owner.id,
        team_id=team.id,
        metadata={"name": team.name},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(team)
    return team


def list_user_teams(db: Session, user_id: int) -> list[Team]:
    """Return all teams that the given user belongs to."""
    stmt = (
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.id.asc())
    )
    return list(db.scalars(stmt).all())


def delete_team(db: Session, team_id: int, actor_id: int, ip_address: str) -> None:
    """Delete a team (owner only) and record an audit log entry."""
    team = db.get(Team, team_id)
    if team is None:
        raise NotFoundError("Team not found")

    team_name = team.name
    record_audit_log(
        db,
        action="team.delete",
        entity_type="team",
        entity_id=team_id,
        user_id=actor_id,
        team_id=None,
        metadata={"name": team_name, "deleted_team_id": team_id},
        ip_address=ip_address,
    )
    db.delete(team)
    db.commit()


def add_team_member(
    db: Session,
    *,
    team_id: int,
    payload: TeamMemberAddRequest,
    actor_membership: TeamMember,
    ip_address: str,
) -> TeamMember:
    """Add a user to a team (admin+ required; only owner can assign admin role; owner role cannot be assigned)."""
    if payload.role == TeamRole.OWNER:
        raise BadRequestError("A team can have only one owner")

    if payload.role == TeamRole.ADMIN and actor_membership.role != TeamRole.OWNER.value:
        raise ForbiddenError("Only the team owner can add a member with the admin role")

    target_user = db.get(User, payload.user_id)
    if target_user is None or not target_user.is_active:
        raise NotFoundError("Target user not found")

    existing = db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == payload.user_id,
        )
    )
    if existing is not None:
        raise ConflictError("User is already a member of this team")

    member = TeamMember(
        user_id=payload.user_id,
        team_id=team_id,
        role=payload.role.value,
    )
    db.add(member)
    db.flush()

    record_audit_log(
        db,
        action="member.add",
        entity_type="team_member",
        entity_id=member.id,
        user_id=actor_membership.user_id,
        team_id=team_id,
        metadata={"target_user_id": payload.user_id, "role": payload.role.value},
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(member)
    return member


def update_member_role(
    db: Session,
    *,
    team_id: int,
    target_user_id: int,
    payload: TeamMemberRoleUpdateRequest,
    actor_id: int,
    ip_address: str,
) -> TeamMember:
    """Update a team member's role (owner only; owner cannot be demoted or replaced)."""
    if payload.role == TeamRole.OWNER:
        raise BadRequestError("Cannot assign a second owner to a team")

    member = db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == target_user_id,
        )
    )
    if member is None:
        raise NotFoundError("Team member not found")

    if member.role == TeamRole.OWNER.value:
        raise BadRequestError("The team owner cannot be demoted")

    old_role = member.role
    member.role = payload.role.value

    record_audit_log(
        db,
        action="member.role_change",
        entity_type="team_member",
        entity_id=member.id,
        user_id=actor_id,
        team_id=team_id,
        metadata={
            "target_user_id": target_user_id,
            "old_role": old_role,
            "new_role": member.role,
        },
        ip_address=ip_address,
    )
    db.commit()
    db.refresh(member)
    return member


def remove_team_member(
    db: Session,
    *,
    team_id: int,
    target_user_id: int,
    actor_membership: TeamMember,
    ip_address: str,
) -> None:
    """Remove a user from a team (admin+; owner can never be removed)."""
    member = db.scalar(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == target_user_id,
        )
    )
    if member is None:
        raise NotFoundError("Team member not found")

    if member.role == TeamRole.OWNER.value:
        raise BadRequestError("The team owner cannot be removed from the team")

    if member.role == TeamRole.ADMIN.value and actor_membership.role != TeamRole.OWNER.value:
        raise ForbiddenError("Only the team owner can remove an admin")

    record_audit_log(
        db,
        action="member.remove",
        entity_type="team_member",
        entity_id=member.id,
        user_id=actor_membership.user_id,
        team_id=team_id,
        metadata={"target_user_id": target_user_id, "role": member.role},
        ip_address=ip_address,
    )
    db.delete(member)
    db.commit()
