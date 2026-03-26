from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from sqlmodel import Session, select

from ktem.db.models import Team, User, UserAccess

ROLE_ADMIN = "admin"
ROLE_KEY_USER = "key_user"
ROLE_USER = "user"
VALID_ROLES = {ROLE_ADMIN, ROLE_KEY_USER, ROLE_USER}


@dataclass
class AccessContext:
    user: User
    access: UserAccess

    @property
    def is_admin(self) -> bool:
        # Backward compatibility: existing installs may still have admin flag set
        # while UserAccess.role is stale.
        return self.access.role == ROLE_ADMIN or bool(self.user.admin)

    @property
    def is_key_user(self) -> bool:
        return self.access.role == ROLE_KEY_USER

    @property
    def is_user(self) -> bool:
        return self.access.role == ROLE_USER


def _default_access_for_user(user: User) -> UserAccess:
    if user.admin:
        return UserAccess(
            user_id=user.id,
            role=ROLE_ADMIN,
            team_id=None,
            can_read=True,
            can_upload=True,
        )
    return UserAccess(
        user_id=user.id,
        role=ROLE_USER,
        team_id=None,
        can_read=True,
        can_upload=False,
    )


def ensure_user_access(session: Session, user: User) -> UserAccess:
    access = session.exec(
        select(UserAccess).where(UserAccess.user_id == user.id)
    ).first()
    if access:
        # Keep legacy admin flag and RBAC role in sync to avoid UI lockout.
        if user.admin and access.role != ROLE_ADMIN:
            access.role = ROLE_ADMIN
            access.team_id = None
            access.can_read = True
            access.can_upload = True
            session.add(access)
            session.commit()
            session.refresh(access)
        return access

    access = _default_access_for_user(user)
    session.add(access)
    session.commit()
    session.refresh(access)
    return access


def get_access_context(session: Session, user_id: Optional[str]) -> Optional[AccessContext]:
    if not user_id:
        return None
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        return None
    access = ensure_user_access(session, user)
    return AccessContext(user=user, access=access)


def team_exists(session: Session, team_id: Optional[str]) -> bool:
    if team_id is None:
        return False
    return session.exec(select(Team).where(Team.id == team_id)).first() is not None


def list_teams(session: Session) -> Sequence[Team]:
    return session.exec(select(Team).order_by(Team.name)).all()


def assert_role_supported(role: str) -> Optional[str]:
    if role not in VALID_ROLES:
        return f"Unbekannte Rolle: {role}"
    return None


def can_manage_user(actor: AccessContext, target: UserAccess) -> bool:
    if actor.is_admin:
        return True
    if actor.is_key_user:
        return (
            target.role == ROLE_USER
            and actor.access.team_id is not None
            and target.team_id == actor.access.team_id
        )
    return False


def can_create_role(actor: AccessContext, role: str, team_id: Optional[str]) -> bool:
    if actor.is_admin:
        return True
    if actor.is_key_user:
        return (
            role == ROLE_USER
            and actor.access.team_id is not None
            and team_id == actor.access.team_id
        )
    return False


def allowed_user_ids_for_scope(session: Session, actor: AccessContext) -> list[str]:
    if actor.is_admin:
        return [u.id for u in session.exec(select(User)).all()]

    team_id = actor.access.team_id
    if not team_id:
        return []

    team_user_ids = [
        row.user_id
        for row in session.exec(
            select(UserAccess.user_id).where(UserAccess.team_id == team_id)
        ).all()
    ]
    if actor.user.id not in team_user_ids:
        team_user_ids.append(actor.user.id)
    return team_user_ids


def has_read_access(actor: AccessContext) -> bool:
    return bool(actor.access.can_read or actor.is_admin)


def has_upload_access(actor: AccessContext) -> bool:
    if actor.is_admin:
        return True
    if actor.is_key_user:
        return True
    return bool(actor.access.can_upload)


def upsert_user_access(
    session: Session,
    user_id: str,
    role: str,
    team_id: Optional[str],
    can_read: bool,
    can_upload: bool,
) -> UserAccess:
    access = session.exec(
        select(UserAccess).where(UserAccess.user_id == user_id)
    ).first()
    if not access:
        access = UserAccess(user_id=user_id)
    access.role = role
    access.team_id = team_id
    access.can_read = can_read
    access.can_upload = can_upload
    session.add(access)
    session.commit()
    session.refresh(access)
    return access
