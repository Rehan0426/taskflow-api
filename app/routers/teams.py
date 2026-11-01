"""Team and team membership management endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_client_ip, get_current_user, require_role
from app.models import Team, TeamMember, TeamRole, User
from app.schemas import (
    TeamCreateRequest,
    TeamMemberAddRequest,
    TeamMemberResponse,
    TeamMemberRoleUpdateRequest,
    TeamResponse,
)
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamCreateRequest,
    current_user: User = Depends(get_current_user),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TeamResponse:
    """Create a new team with the current user as owner."""
    team = team_service.create_team(db, payload, owner=current_user, ip_address=ip_address)
    return TeamResponse.model_validate(team)


@router.get("", response_model=list[TeamResponse])
def list_my_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamResponse]:
    """List all teams the authenticated user belongs to."""
    teams = team_service.list_user_teams(db, user_id=current_user.id)
    return [TeamResponse.model_validate(t) for t in teams]


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(
    team_id: int,
    membership: TeamMember = Depends(require_role(TeamRole.MEMBER)),
    db: Session = Depends(get_db),
) -> TeamResponse:
    """Retrieve a specific team (returns 404 if user is not a member)."""
    team = db.get(Team, team_id)
    return TeamResponse.model_validate(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: int,
    membership: TeamMember = Depends(require_role(TeamRole.OWNER)),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> None:
    """Delete a team (owner only)."""
    team_service.delete_team(
        db, team_id=team_id, actor_id=membership.user_id, ip_address=ip_address
    )


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    team_id: int,
    payload: TeamMemberAddRequest,
    membership: TeamMember = Depends(require_role(TeamRole.ADMIN)),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TeamMemberResponse:
    """Add a user to a team (admin+ required)."""
    member = team_service.add_team_member(
        db,
        team_id=team_id,
        payload=payload,
        actor_membership=membership,
        ip_address=ip_address,
    )
    return TeamMemberResponse.model_validate(member)


@router.patch("/{team_id}/members/{user_id}", response_model=TeamMemberResponse)
def change_member_role(
    team_id: int,
    user_id: int,
    payload: TeamMemberRoleUpdateRequest,
    membership: TeamMember = Depends(require_role(TeamRole.OWNER)),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> TeamMemberResponse:
    """Change a member's role (owner only; owner cannot be demoted)."""
    member = team_service.update_member_role(
        db,
        team_id=team_id,
        target_user_id=user_id,
        payload=payload,
        actor_id=membership.user_id,
        ip_address=ip_address,
    )
    return TeamMemberResponse.model_validate(member)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    team_id: int,
    user_id: int,
    membership: TeamMember = Depends(require_role(TeamRole.ADMIN)),
    ip_address: str = Depends(get_client_ip),
    db: Session = Depends(get_db),
) -> None:
    """Remove a member from a team (admin+ required; owner cannot be removed)."""
    team_service.remove_team_member(
        db,
        team_id=team_id,
        target_user_id=user_id,
        actor_membership=membership,
        ip_address=ip_address,
    )
