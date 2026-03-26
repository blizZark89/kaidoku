from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from sqlalchemy import text
from sqlmodel import Session, select

from ktem.db.models import Team, User, UserAccess

ROLE_ADMIN = "admin"
ROLE_KEY_USER = "key_user"
ROLE_USER = "user"
VALID_ROLES = {ROLE_ADMIN, ROLE_KEY_USER, ROLE_USER}


def _unwrap_row_value(value):
    # SQLAlchemy Row -> first selected entity/scalar
    if hasattr(value, "_mapping"):
        try:
            mapping_values = list(value._mapping.values())
            if mapping_values:
                return mapping_values[0]
        except Exception:
            pass
        try:
            return value[0]
        except Exception:
            return value
    if isinstance(value, (tuple, list)):
        return value[0] if value else value
    return value


def _first(session, statement):
    if hasattr(session, "exec"):
        return session.exec(statement).first()
    row = session.execute(statement).first()
    if row is None:
        return None
    return _unwrap_row_value(row)


def _all(session, statement):
    if hasattr(session, "exec"):
        return session.exec(statement).all()
    rows = session.execute(statement).all()
    return [_unwrap_row_value(row) for row in rows]


def parse_team_ids(team_value: Optional[str]) -> list[str]:
    if not team_value:
        return []
    return [t.strip() for t in str(team_value).split(",") if t.strip()]


def encode_team_ids(team_ids: Optional[list[str]]) -> Optional[str]:
    if not team_ids:
        return None
    unique_ids = []
    for team_id in team_ids:
        t = str(team_id).strip()
        if t and t not in unique_ids:
            unique_ids.append(t)
    return ",".join(unique_ids) if unique_ids else None


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

    @property
    def team_ids(self) -> list[str]:
        return parse_team_ids(self.access.team_id)


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


def _legacy_team_id_for_user(session: Session, user_id: str) -> Optional[str]:
    # Migration helper for installs that still have the previous membership table.
    for table in ("userteammembership", "baseuserteammembership"):
        try:
            stmt = text(
                f"SELECT team_id FROM {table} WHERE user_id = :uid LIMIT 1"
            ).bindparams(uid=user_id)
            row = _first(session, stmt)
            if row:
                if isinstance(row, tuple):
                    return str(row[0]) if row[0] else None
                return str(row) if row else None
        except Exception:
            continue
    return None


def ensure_user_access(session: Session, user: User) -> UserAccess:
    access = _first(session, select(UserAccess).where(UserAccess.user_id == user.id))
    if access:
        # Keep legacy admin flag and RBAC role in sync to avoid UI lockout.
        if user.admin and access.role != ROLE_ADMIN:
            access.role = ROLE_ADMIN
            access.team_id = None
            access.can_read = True
            access.can_upload = True
        # Keep legacy team memberships available after RBAC table migration.
        if not user.admin and not access.team_id:
            legacy_team_id = _legacy_team_id_for_user(session, user.id)
            if legacy_team_id:
                access.team_id = legacy_team_id
        session.add(access)
        session.commit()
        session.refresh(access)
        return access

    access = _default_access_for_user(user)
    if not user.admin:
        legacy_team_id = _legacy_team_id_for_user(session, user.id)
        if legacy_team_id:
            access.team_id = legacy_team_id
    session.add(access)
    session.commit()
    session.refresh(access)
    return access


def get_access_context(session: Session, user_id: Optional[str]) -> Optional[AccessContext]:
    if not user_id:
        return None
    user = _first(session, select(User).where(User.id == user_id))
    if not user:
        return None
    access = ensure_user_access(session, user)
    return AccessContext(user=user, access=access)


def team_exists(session: Session, team_id: Optional[str]) -> bool:
    if team_id is None:
        return False
    return _first(session, select(Team).where(Team.id == team_id)) is not None


def list_teams(session: Session) -> Sequence[Team]:
    return _all(session, select(Team).order_by(Team.name))


def assert_role_supported(role: str) -> Optional[str]:
    if role not in VALID_ROLES:
        return f"Unbekannte Rolle: {role}"
    return None


def can_manage_user(actor: AccessContext, target: UserAccess) -> bool:
    if actor.is_admin:
        return True
    if actor.is_key_user:
        actor_team_ids = set(actor.team_ids)
        target_team_ids = set(parse_team_ids(target.team_id))
        return (
            target.role == ROLE_USER
            and bool(actor_team_ids)
            and bool(actor_team_ids.intersection(target_team_ids))
        )
    return False


def can_create_role(actor: AccessContext, role: str, team_id: Optional[str]) -> bool:
    if actor.is_admin:
        return True
    if actor.is_key_user:
        actor_team_ids = set(actor.team_ids)
        target_team_ids = set(parse_team_ids(team_id))
        return (
            role == ROLE_USER
            and bool(actor_team_ids)
            and bool(target_team_ids)
            and target_team_ids.issubset(actor_team_ids)
        )
    return False


def allowed_user_ids_for_scope(session: Session, actor: AccessContext) -> list[str]:
    if actor.is_admin:
        return [u.id for u in _all(session, select(User))]

    actor_team_ids = set(actor.team_ids)
    if not actor_team_ids:
        return []

    team_user_ids = []
    for access in _all(session, select(UserAccess)):
        target_team_ids = set(parse_team_ids(access.team_id))
        if actor_team_ids.intersection(target_team_ids):
            team_user_ids.append(access.user_id)
    if actor.user.id not in team_user_ids:
        team_user_ids.append(actor.user.id)
    return list(dict.fromkeys(team_user_ids))


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
    access = _first(session, select(UserAccess).where(UserAccess.user_id == user_id))
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
