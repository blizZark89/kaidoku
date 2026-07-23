from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from decouple import config
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings

from ktem.authz import ROLE_ADMIN, ROLE_USER, upsert_user_access
from ktem.db.models import Team, User, engine

AUTH_METHOD_LOCAL = "LOCAL"
AUTH_METHOD_AUTHENTIK = "AUTHENTIK"
AUTH_METHOD_LDAP = "LDAP"
VALID_AUTH_METHODS = {
    AUTH_METHOD_LOCAL,
    AUTH_METHOD_AUTHENTIK,
    AUTH_METHOD_LDAP,
}


class ExternalAuthError(RuntimeError):
    pass


@dataclass
class ExternalIdentity:
    provider: str
    subject: str
    username: str
    email: str
    display_name: str
    groups: list[str]
    raw_claims: dict[str, Any]


@dataclass
class PermissionDecision:
    is_admin: bool
    can_access: bool
    can_upload: bool
    role: str
    reason: str = ""


@dataclass
class UserIdResult:
    user_id: str
    decision: PermissionDecision


def get_authentication_method() -> str:
    value = str(
        getattr(flowsettings, "AUTHENTICATION_METHOD", None)
        or config("AUTHENTICATION_METHOD", default=AUTH_METHOD_LOCAL)
    ).strip().upper()
    if not value:
        return AUTH_METHOD_LOCAL
    if value not in VALID_AUTH_METHODS:
        return AUTH_METHOD_LOCAL
    return value


def is_local_auth() -> bool:
    return get_authentication_method() == AUTH_METHOD_LOCAL


def is_oidc_auth() -> bool:
    return get_authentication_method() == AUTH_METHOD_AUTHENTIK


def is_ldap_auth() -> bool:
    return get_authentication_method() == AUTH_METHOD_LDAP


def uses_external_auth() -> bool:
    return get_authentication_method() in {AUTH_METHOD_AUTHENTIK, AUTH_METHOD_LDAP}


def can_manage_local_users() -> bool:
    return is_local_auth()


def local_user_management_block_reason() -> str:
    method = get_authentication_method()
    return (
        "Lokale Benutzer-, Passwort- und Rechteverwaltung ist deaktiviert, "
        f"weil AUTHENTICATION_METHOD={method} gesetzt ist."
    )


def _parse_csv_env(name: str) -> list[str]:
    raw_value = str(config(name, default="") or "")
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _normalize_group_name(value: str) -> str:
    return str(value or "").strip().casefold()


def normalize_groups(raw_groups: Any) -> list[str]:
    groups: list[str] = []

    def append_group(value: Any):
        normalized = str(value or "").strip()
        if normalized and normalized not in groups:
            groups.append(normalized)

    if raw_groups is None:
        return groups
    if isinstance(raw_groups, str):
        separator = "," if "," in raw_groups else " "
        for item in raw_groups.split(separator):
            append_group(item)
        return groups
    if isinstance(raw_groups, (list, tuple, set)):
        for item in raw_groups:
            append_group(item)
    return groups


def derive_group_permissions(groups: list[str]) -> PermissionDecision:
    normalized_groups = {_normalize_group_name(group) for group in groups}
    admin_groups = {_normalize_group_name(group) for group in _parse_csv_env("ADMIN_GROUPS")}
    user_groups = {_normalize_group_name(group) for group in _parse_csv_env("USER_GROUPS")}
    raw_admin = _parse_csv_env("ADMIN_GROUPS")
    raw_user = _parse_csv_env("USER_GROUPS")
    print("[AUTH DEBUG derive] groups_in=" + str(normalized_groups), flush=True)
    print("[AUTH DEBUG derive] raw_admin=" + str(raw_admin), flush=True)
    print("[AUTH DEBUG derive] raw_user=" + str(raw_user), flush=True)
    upload_groups = {
        _normalize_group_name(group) for group in _parse_csv_env("UPLOAD_ALLOWED_GROUPS")
    }
    denied_groups = {
        _normalize_group_name(group) for group in _parse_csv_env("ACCESS_DENIED_GROUPS")
    }

    if denied_groups and normalized_groups.intersection(denied_groups):
        return PermissionDecision(
            is_admin=False,
            can_access=False,
            can_upload=False,
            role=ROLE_USER,
            reason="Benutzer ist Mitglied in einer gesperrten Gruppe.",
        )

    is_admin = bool(admin_groups and normalized_groups.intersection(admin_groups))
    in_user_group = bool(user_groups and normalized_groups.intersection(user_groups))
    can_access = is_admin or in_user_group
    can_upload = is_admin or bool(
        upload_groups and normalized_groups.intersection(upload_groups)
    )

    if not can_access:
        return PermissionDecision(
            is_admin=is_admin,
            can_access=False,
            can_upload=False,
            role=ROLE_ADMIN if is_admin else ROLE_USER,
            reason=(
                "Keine passende Zugriffsgruppe gefunden. "
                "Prüfe ADMIN_GROUPS/USER_GROUPS."
            ),
        )

    return PermissionDecision(
        is_admin=is_admin,
        can_access=True,
        can_upload=can_upload,
        role=ROLE_ADMIN if is_admin else ROLE_USER,
    )


def get_session_user_id(request) -> Optional[str]:
    if request is None:
        return None
    session = getattr(request, "session", None)
    if not session:
        return None
    user_id = session.get("user_id")
    return str(user_id).strip() if user_id else None


def clear_session_user(request) -> None:
    session = getattr(request, "session", None)
    if session is not None:
        session.pop("user_id", None)
        session.pop("id_token", None)


def _preferred_claim(claims: dict[str, Any], *names: str) -> str:
    for name in names:
        value = claims.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def identity_from_oidc_claims(claims: dict[str, Any]) -> ExternalIdentity:
    groups_claim_name = str(config("OIDC_GROUPS_CLAIM", default="groups") or "groups")
    username_claim_name = str(
        config("OIDC_USERNAME_CLAIM", default="preferred_username") or "preferred_username"
    )
    display_name_claim_name = str(
        config("OIDC_DISPLAY_NAME_CLAIM", default="name") or "name"
    )

    subject = _preferred_claim(claims, "sub")
    email = _preferred_claim(claims, "email")
    username = _preferred_claim(
        claims, username_claim_name, "preferred_username", "email", "sub"
    )
    display_name = _preferred_claim(
        claims,
        display_name_claim_name,
        "name",
        "given_name",
        "preferred_username",
        "email",
    )
    groups = normalize_groups(claims.get(groups_claim_name))

    if not subject:
        raise ExternalAuthError("OIDC-Claims enthalten kein `sub`.")
    if not username:
        username = subject
    if not email:
        email = username
    if not display_name:
        display_name = username

    return ExternalIdentity(
        provider=AUTH_METHOD_AUTHENTIK,
        subject=subject,
        username=username,
        email=email,
        display_name=display_name,
        groups=groups,
        raw_claims=claims,
    )


def _find_user_for_external_identity(
    session: Session, identity: ExternalIdentity
) -> Optional[User]:
    if identity.provider == AUTH_METHOD_AUTHENTIK:
        user = session.exec(select(User).where(User.id == identity.subject)).first()
        if user:
            return user

    return session.exec(
        select(User).where(User.username_lower == identity.username.lower().strip())
    ).first()


def _resolve_team_ids_from_groups(
    session: Session, groups: list[str]
) -> Optional[str]:
    """Map Authentik groups to Kaidoku team IDs via TEAM_GROUP_PREFIX.

    Teams that do not exist yet are auto-created so that adding a group in
    Authentik is sufficient — no manual DB insert required.
    """
    import uuid

    prefix = str(
        getattr(flowsettings, "TEAM_GROUP_PREFIX", None)
        or config("TEAM_GROUP_PREFIX", default="kaidoku_")
        or "kaidoku_"
    )
    team_ids: list[str] = []
    for group_name in groups:
        group_name = str(group_name or "").strip()
        if not group_name.startswith(prefix):
            continue
        team_name = group_name[len(prefix):]
        if not team_name:
            continue
        team = session.exec(select(Team).where(Team.name == team_name)).first()
        if team is None:
            team = Team(
                id=uuid.uuid5(uuid.NAMESPACE_DNS, f"kaidoku.team.{team_name}").hex,
                name=team_name,
                is_global=False,
                owner_user_id=None,
            )
            session.add(team)
            session.commit()
            session.refresh(team)
        team_ids.append(team.id)
    return ",".join(team_ids) if team_ids else None


def sync_external_user(
    identity: ExternalIdentity,
) -> UserIdResult:
    decision = derive_group_permissions(identity.groups)
    password_placeholder = f"external::{identity.provider.lower()}"

    with Session(engine) as session:
        user = _find_user_for_external_identity(session, identity)

        if user is None:
            user_id = (
                identity.subject if identity.provider == AUTH_METHOD_AUTHENTIK else None
            )
            user = User(
                id=user_id,
                username=identity.username,
                username_lower=identity.username.lower().strip(),
                password=password_placeholder,
                admin=decision.is_admin,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        else:
            user.username = identity.username
            user.username_lower = identity.username.lower().strip()
            user.admin = decision.is_admin
            if not user.password:
                user.password = password_placeholder
            session.add(user)
            session.commit()
            session.refresh(user)

        team_id = _resolve_team_ids_from_groups(session, identity.groups)

        upsert_user_access(
            session=session,
            user_id=user.id,
            role=decision.role,
            team_id=team_id,
            can_read=decision.can_access,
            can_upload=decision.can_upload,
            default_team_id=None,
        )
        return UserIdResult(user_id=str(user.id), decision=decision)


def authenticate_ldap_user(username: str, password: str) -> ExternalIdentity:
    from ldap3 import ALL, Connection, Server, Tls

    username = str(username or "").strip()
    password = str(password or "")
    if not username or not password:
        raise ExternalAuthError("Benutzername und Passwort sind erforderlich.")

    server_uri = str(config("LDAP_SERVER_URI", default="") or "").strip()
    if not server_uri:
        raise ExternalAuthError("LDAP_SERVER_URI ist nicht gesetzt.")

    bind_dn_template = str(config("LDAP_BIND_DN_TEMPLATE", default="") or "").strip()
    bind_user_dn = str(config("LDAP_BIND_USER_DN", default="") or "").strip()
    bind_password = str(config("LDAP_BIND_PASSWORD", default="") or "")
    user_base_dn = str(config("LDAP_USER_BASE_DN", default="") or "").strip()
    user_filter = str(
        config("LDAP_USER_FILTER", default="(uid={username})")
        or "(uid={username})"
    )
    username_attribute = str(config("LDAP_USERNAME_ATTRIBUTE", default="uid") or "uid")
    email_attribute = str(config("LDAP_EMAIL_ATTRIBUTE", default="mail") or "mail")
    display_name_attribute = str(
        config("LDAP_DISPLAY_NAME_ATTRIBUTE", default="displayName") or "displayName"
    )
    group_base_dn = str(config("LDAP_GROUP_BASE_DN", default="") or "").strip()
    group_filter = str(
        config(
            "LDAP_GROUP_FILTER",
            default="(&(objectClass=groupOfNames)(member={user_dn}))",
        )
        or "(&(objectClass=groupOfNames)(member={user_dn}))"
    )
    group_name_attribute = str(
        config("LDAP_GROUP_NAME_ATTRIBUTE", default="cn") or "cn"
    )
    ldap_use_ssl = config("LDAP_USE_SSL", default=False, cast=bool)
    ldap_start_tls = config("LDAP_START_TLS", default=False, cast=bool)
    connect_timeout = int(config("LDAP_CONNECT_TIMEOUT", default=10, cast=int))

    tls = Tls(validate=0)
    server = Server(
        server_uri,
        use_ssl=ldap_use_ssl,
        get_info=ALL,
        tls=tls,
        connect_timeout=connect_timeout,
    )

    def bind_connection(user_dn: str, user_password: str) -> Connection:
        connection = Connection(server, user=user_dn, password=user_password, auto_bind=True)
        if ldap_start_tls and not ldap_use_ssl:
            connection.start_tls()
        return connection

    user_dn = bind_dn_template.format(username=username) if bind_dn_template else ""

    service_connection: Optional[Connection] = None
    user_connection: Optional[Connection] = None
    try:
        if bind_user_dn:
            service_connection = bind_connection(bind_user_dn, bind_password)
            if not user_dn:
                if not user_base_dn:
                    raise ExternalAuthError(
                        "LDAP_USER_BASE_DN wird benötigt, wenn LDAP_BIND_DN_TEMPLATE nicht gesetzt ist."
                    )
                search_filter = user_filter.format(username=username)
                service_connection.search(
                    search_base=user_base_dn,
                    search_filter=search_filter,
                    attributes=[
                        username_attribute,
                        email_attribute,
                        display_name_attribute,
                    ],
                    size_limit=1,
                )
                if not service_connection.entries:
                    raise ExternalAuthError("LDAP-Benutzer wurde nicht gefunden.")
                user_entry = service_connection.entries[0]
                user_dn = str(user_entry.entry_dn)
            user_connection = bind_connection(user_dn, password)
        else:
            if not user_dn:
                raise ExternalAuthError(
                    "Setze LDAP_BIND_DN_TEMPLATE oder LDAP_BIND_USER_DN/LDAP_BIND_PASSWORD."
                )
            user_connection = bind_connection(user_dn, password)

        entry_connection = service_connection or user_connection
        username_value = username
        email_value = username
        display_name_value = username

        if user_base_dn:
            search_filter = user_filter.format(username=username)
            entry_connection.search(
                search_base=user_base_dn,
                search_filter=search_filter,
                attributes=[
                    username_attribute,
                    email_attribute,
                    display_name_attribute,
                ],
                size_limit=1,
            )
            if entry_connection.entries:
                user_entry = entry_connection.entries[0]
                username_attr = getattr(user_entry, username_attribute, None)
                email_attr = getattr(user_entry, email_attribute, None)
                display_name_attr = getattr(user_entry, display_name_attribute, None)
                if username_attr and str(username_attr.value).strip():
                    username_value = str(username_attr.value).strip()
                if email_attr and str(email_attr.value).strip():
                    email_value = str(email_attr.value).strip()
                if display_name_attr and str(display_name_attr.value).strip():
                    display_name_value = str(display_name_attr.value).strip()

        groups: list[str] = []
        if group_base_dn:
            search_filter = group_filter.format(user_dn=user_dn, username=username_value)
            entry_connection.search(
                search_base=group_base_dn,
                search_filter=search_filter,
                attributes=[group_name_attribute],
            )
            for entry in entry_connection.entries:
                group_attr = getattr(entry, group_name_attribute, None)
                if group_attr and str(group_attr.value).strip():
                    group_name = str(group_attr.value).strip()
                    if group_name not in groups:
                        groups.append(group_name)

        return ExternalIdentity(
            provider=AUTH_METHOD_LDAP,
            subject=user_dn,
            username=username_value,
            email=email_value,
            display_name=display_name_value,
            groups=groups,
            raw_claims={"dn": user_dn, "groups": groups},
        )
    except ExternalAuthError:
        raise
    except Exception as exc:
        raise ExternalAuthError(f"LDAP-Anmeldung fehlgeschlagen: {exc}") from exc
    finally:
        for connection in (user_connection, service_connection):
            try:
                if connection is not None and connection.bound:
                    connection.unbind()
            except Exception:
                pass
