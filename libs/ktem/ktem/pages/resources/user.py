import hashlib
import uuid
from typing import Optional

import gradio as gr
import pandas as pd
from ktem.app import BasePage
from ktem.authz import (
    ROLE_ADMIN,
    ROLE_KEY_USER,
    ROLE_USER,
    assert_role_supported,
    can_create_role,
    can_manage_user,
    default_team_choices,
    encode_team_ids,
    ensure_user_access,
    get_access_context,
    list_teams,
    managed_team_ids,
    normalize_default_team_id,
    parse_team_ids,
    team_exists,
    upsert_user_access,
)
from ktem.db.models import Team, User, UserAccess, engine
from sqlalchemy import text
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings

USERNAME_RULE = """**Benutzername-Regeln:**

- Groß-/Kleinschreibung wird nicht unterschieden
- Mindestens 3 Zeichen
- Höchstens 32 Zeichen
- Nur Buchstaben, Zahlen und Unterstriche
"""


PASSWORD_RULE = """**Passwort-Regeln:**

- Mindestens 8 Zeichen
- Mindestens ein Großbuchstabe
- Mindestens ein Kleinbuchstabe
- Mindestens eine Ziffer
- Mindestens ein Sonderzeichen aus dieser Liste:
    ^ $ * . [ ] { } ( ) ? - " ! @ # % & / \\ , > < ' : ; | _ ~  + =
"""


def validate_username(usn):
    errors = []
    if len(usn) < 3:
        errors.append("Der Benutzername muss mindestens 3 Zeichen lang sein")
    if len(usn) > 32:
        errors.append("Der Benutzername darf höchstens 32 Zeichen lang sein")
    if not usn.replace("_", "").isalnum():
        errors.append(
            "Der Benutzername darf nur Buchstaben, Zahlen und Unterstriche enthalten"
        )
    return "; ".join(errors)


def validate_password(pwd, pwd_cnf):
    errors = []
    if pwd != pwd_cnf:
        errors.append("Die Passwörter stimmen nicht überein")
    if len(pwd) < 8:
        errors.append("Das Passwort muss mindestens 8 Zeichen lang sein")
    if not any(c.isupper() for c in pwd):
        errors.append("Das Passwort muss mindestens einen Großbuchstaben enthalten")
    if not any(c.islower() for c in pwd):
        errors.append("Das Passwort muss mindestens einen Kleinbuchstaben enthalten")
    if not any(c.isdigit() for c in pwd):
        errors.append("Das Passwort muss mindestens eine Ziffer enthalten")
    special_chars = "^$*.[]{}()?-\"!@#%&/\\,><':;|_~+="
    if not any(c in special_chars for c in pwd):
        errors.append(
            "Das Passwort muss mindestens ein Sonderzeichen aus dieser "
            f"Liste enthalten: {special_chars}"
        )
    return "; ".join(errors) if errors else ""


def _normalize_role_permissions(role: str, can_read: bool, can_upload: bool) -> tuple[bool, bool]:
    if role in {ROLE_ADMIN, ROLE_KEY_USER}:
        return True, True
    return bool(can_read), bool(can_upload)


def _validate_role_team_constraints(role: str, team_ids: list[str]) -> Optional[str]:
    if role in {ROLE_KEY_USER, ROLE_USER} and not team_ids:
        return "Diese Rolle muss mindestens einem Team zugeordnet sein"
    if role == ROLE_ADMIN and team_ids:
        return "Admin darf keinem Team fest zugeordnet sein"
    return None


def _resolve_actor(session: Session, actor_user_id: Optional[str]):
    actor = get_access_context(session, actor_user_id)
    if not actor:
        gr.Warning("Nicht angemeldet")
        return None
    return actor


def _team_table_has_name_lower(session: Session) -> bool:
    rows = session.exec(text("PRAGMA table_info(team)")).all()
    for row in rows:
        # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
        if len(row) > 1 and str(row[1]) == "name_lower":
            return True
    return False


def create_user(usn, pwd, user_id=None, is_admin=True) -> bool:
    with Session(engine) as session:
        statement = select(User).where(User.username_lower == usn.lower())
        if session.exec(statement).all():
            print(f'User "{usn}" already exists')
            return False

        hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
        user = User(
            id=user_id,
            username=usn,
            username_lower=usn.lower(),
            password=hashed_password,
            admin=is_admin,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        role = ROLE_ADMIN if is_admin else ROLE_USER
        upsert_user_access(
            session=session,
            user_id=user.id,
            role=role,
            team_id=None,
            can_read=True,
            can_upload=is_admin,
        )
        return True


def ensure_admin_user(usn: str, pwd: str) -> bool:
    """Ensure configured bootstrap admin exists and has admin RBAC."""
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username_lower == usn.lower())).first()
        if user is None:
            return create_user(usn=usn, pwd=pwd, is_admin=True)

        changed = False
        if not user.admin:
            user.admin = True
            changed = True
        if changed:
            session.add(user)
            session.commit()

        upsert_user_access(
            session=session,
            user_id=user.id,
            role=ROLE_ADMIN,
            team_id=None,
            can_read=True,
            can_upload=True,
        )
        return changed


class UserManagement(BasePage):
    USER_LIST_COLUMNS = [
        "id",
        "username",
        "role",
        "team",
        "standardteam",
        "can_read",
        "can_upload",
    ]

    def __init__(self, app):
        self._app = app
        self.on_building_ui()
        if hasattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_ADMIN") and hasattr(
            flowsettings, "KH_FEATURE_USER_MANAGEMENT_PASSWORD"
        ):
            usn = flowsettings.KH_FEATURE_USER_MANAGEMENT_ADMIN
            pwd = flowsettings.KH_FEATURE_USER_MANAGEMENT_PASSWORD
            is_created_or_upgraded = ensure_admin_user(usn, pwd)
            if is_created_or_upgraded:
                gr.Info(f'Admin-Benutzer "{usn}" ist aktiv')

    def _team_choices_for_actor(self, actor_user_id: Optional[str]):
        with Session(engine) as session:
            actor = get_access_context(session, actor_user_id)
            if not actor:
                return []
            if actor.is_admin:
                return [(team.name, team.id) for team in list_teams(session)]
            if actor.is_key_user and actor.team_ids:
                manageable_team_ids = managed_team_ids(session, actor)
                result = []
                for team_id in actor.team_ids:
                    if team_id not in manageable_team_ids:
                        continue
                    team = session.exec(select(Team).where(Team.id == team_id)).first()
                    if team:
                        result.append((team.name, team.id))
                return result
            return []

    def _default_team_choices_for_actor(self, actor_user_id: Optional[str]):
        with Session(engine) as session:
            actor = get_access_context(session, actor_user_id)
            choices = [("Kein Standardteam", "")]
            if not actor:
                return choices
            team_map = {team.id: team.name for team in list_teams(session)}
            for team_id in default_team_choices(session, actor):
                if team_id in team_map:
                    choices.append((team_map[team_id], team_id))
            return choices

    def _role_choices_for_actor(self, actor_user_id: Optional[str]):
        with Session(engine) as session:
            actor = get_access_context(session, actor_user_id)
            if not actor:
                return [ROLE_USER]
            if actor.is_admin:
                return [ROLE_USER, ROLE_KEY_USER, ROLE_ADMIN]
            if actor.is_key_user:
                return [ROLE_USER]
            return [ROLE_USER]

    def on_building_ui(self):
        with gr.Tab(label="Benutzerliste"):
            self.state_user_list = gr.State(value=None)
            self.user_sort_column = gr.Dropdown(
                label="Sortieren nach",
                choices=self.USER_LIST_COLUMNS,
                value="username",
            )
            self.user_sort_ascending = gr.Checkbox(label="Aufsteigend", value=True)
            self.user_list = gr.DataFrame(
                headers=self.USER_LIST_COLUMNS,
                interactive=False,
                elem_id="user_list_view",
            )

            with gr.Group(visible=False) as self._selected_panel:
                self.selected_user_id = gr.State(value=-1)
                self.usn_edit = gr.Textbox(label="Benutzername")
                with gr.Row():
                    self.pwd_edit = gr.Textbox(label="Passwort ändern", type="password")
                    self.pwd_cnf_edit = gr.Textbox(
                        label="Passwortänderung bestätigen",
                        type="password",
                    )
                self.role_edit = gr.Dropdown(
                    label="Rolle",
                    choices=[ROLE_ADMIN, ROLE_KEY_USER, ROLE_USER],
                    value=ROLE_USER,
                )
                self.team_edit = gr.Dropdown(
                    label="Teams",
                    choices=[],
                    value=[],
                    multiselect=True,
                )
                self.default_team_edit = gr.Dropdown(
                    label="Standardteam",
                    choices=[("Kein Standardteam", "")],
                    value="",
                    multiselect=False,
                )
                with gr.Row():
                    self.can_read_edit = gr.Checkbox(label="Leserechte", value=True)
                    self.can_upload_edit = gr.Checkbox(label="Upload-Rechte", value=False)

            with gr.Row(visible=False) as self._selected_panel_btn:
                self.btn_edit_save = gr.Button("Speichern")
                self.btn_delete = gr.Button("Löschen")
                self.btn_delete_yes = gr.Button(
                    "Löschen bestätigen", variant="primary", visible=False
                )
                self.btn_delete_no = gr.Button("Abbrechen", visible=False)
                self.btn_close = gr.Button("Schließen")

        with gr.Tab(label="Benutzer anlegen"):
            self.usn_new = gr.Textbox(label="Benutzername", interactive=True)
            self.pwd_new = gr.Textbox(label="Passwort", type="password", interactive=True)
            self.pwd_cnf_new = gr.Textbox(
                label="Passwort bestätigen", type="password", interactive=True
            )
            self.role_new = gr.Dropdown(
                label="Rolle",
                choices=[ROLE_USER],
                value=ROLE_USER,
            )
            self.team_new = gr.Dropdown(
                label="Teams",
                choices=[],
                value=[],
                multiselect=True,
            )
            self.default_team_new = gr.Dropdown(
                label="Standardteam",
                choices=[("Kein Standardteam", "")],
                value="",
                multiselect=False,
            )
            with gr.Row():
                self.can_read_new = gr.Checkbox(label="Leserechte", value=True)
                self.can_upload_new = gr.Checkbox(label="Upload-Rechte", value=False)
            with gr.Row():
                gr.Markdown(USERNAME_RULE)
                gr.Markdown(PASSWORD_RULE)
            self.btn_new = gr.Button("Benutzer anlegen")

        with gr.Tab(label="Teams"):
            self.team_state = gr.State(value=None)
            self.team_list = gr.DataFrame(headers=["id", "name", "global"], interactive=False)
            self.selected_team_id = gr.State(value=None)
            self.team_name_new = gr.Textbox(label="Teamname")
            self.team_global_edit = gr.Checkbox(label="Globales Team", value=False)
            self.btn_team_save = gr.Button("Global-Status speichern")
            with gr.Row():
                self.btn_team_create = gr.Button("Team erstellen")
                self.btn_team_delete = gr.Button("Team löschen")

    def on_register_events(self):
        self._app.user_id.change(
            self.refresh_user_list_view,
            inputs=[self._app.user_id, self.user_sort_column, self.user_sort_ascending],
            outputs=[self.state_user_list, self.user_list],
            show_progress="hidden",
        )
        self._app.user_id.change(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
            show_progress="hidden",
        )
        self._app.user_id.change(
            self.refresh_team_dropdowns,
            inputs=[self._app.user_id],
            outputs=[self.team_new, self.team_edit, self.role_new, self.default_team_new, self.default_team_edit],
            show_progress="hidden",
        )

        self.btn_new.click(
            self.create_user,
            inputs=[
                self._app.user_id,
                self.usn_new,
                self.pwd_new,
                self.pwd_cnf_new,
                self.role_new,
                self.team_new,
                self.default_team_new,
                self.can_read_new,
                self.can_upload_new,
            ],
            outputs=[self.usn_new, self.pwd_new, self.pwd_cnf_new],
        ).then(
            self.refresh_user_list_view,
            inputs=[self._app.user_id, self.user_sort_column, self.user_sort_ascending],
            outputs=[self.state_user_list, self.user_list],
        )

        self.user_sort_column.change(
            self.apply_user_sort,
            inputs=[self.state_user_list, self.user_sort_column, self.user_sort_ascending],
            outputs=[self.user_list],
            show_progress="hidden",
        )
        self.user_sort_ascending.change(
            self.apply_user_sort,
            inputs=[self.state_user_list, self.user_sort_column, self.user_sort_ascending],
            outputs=[self.user_list],
            show_progress="hidden",
        )

        self.user_list.select(
            self.select_user,
            inputs=self.user_list,
            outputs=[self.selected_user_id],
            show_progress="hidden",
        )

        self.selected_user_id.change(
            self.on_selected_user_change,
            inputs=[self._app.user_id, self.selected_user_id],
            outputs=[
                self._selected_panel,
                self._selected_panel_btn,
                self.btn_delete,
                self.btn_delete_yes,
                self.btn_delete_no,
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.role_edit,
                self.team_edit,
                self.default_team_edit,
                self.can_read_edit,
                self.can_upload_edit,
            ],
            show_progress="hidden",
        )

        self.btn_delete.click(
            self.on_btn_delete_click,
            inputs=[self.selected_user_id],
            outputs=[self.btn_delete, self.btn_delete_yes, self.btn_delete_no],
            show_progress="hidden",
        )

        self.btn_delete_yes.click(
            self.delete_user,
            inputs=[self._app.user_id, self.selected_user_id],
            outputs=[self.selected_user_id],
            show_progress="hidden",
        ).then(
            self.refresh_user_list_view,
            inputs=[self._app.user_id, self.user_sort_column, self.user_sort_ascending],
            outputs=[self.state_user_list, self.user_list],
        )

        self.btn_delete_no.click(
            lambda: (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ),
            inputs=[],
            outputs=[self.btn_delete, self.btn_delete_yes, self.btn_delete_no],
            show_progress="hidden",
        )

        self.btn_edit_save.click(
            self.save_user,
            inputs=[
                self._app.user_id,
                self.selected_user_id,
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.role_edit,
                self.team_edit,
                self.default_team_edit,
                self.can_read_edit,
                self.can_upload_edit,
            ],
            outputs=[self.pwd_edit, self.pwd_cnf_edit],
            show_progress="hidden",
        ).then(
            self.refresh_user_list_view,
            inputs=[self._app.user_id, self.user_sort_column, self.user_sort_ascending],
            outputs=[self.state_user_list, self.user_list],
        )

        self.btn_close.click(lambda: -1, outputs=[self.selected_user_id])

        self.btn_team_create.click(
            self.create_team,
            inputs=[self._app.user_id, self.team_name_new],
            outputs=[self.team_name_new],
            show_progress="hidden",
        ).then(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
        ).then(
            self.refresh_team_dropdowns,
            inputs=[self._app.user_id],
            outputs=[self.team_new, self.team_edit, self.role_new, self.default_team_new, self.default_team_edit],
        )

        self.team_list.select(
            self.select_team,
            inputs=[self.team_state],
            outputs=[self.selected_team_id],
            show_progress="hidden",
        )
        self.selected_team_id.change(
            self.on_selected_team_change,
            inputs=[self.team_state, self.selected_team_id],
            outputs=[self.team_global_edit],
            show_progress="hidden",
        )

        self.btn_team_save.click(
            self.save_team_global_status,
            inputs=[self._app.user_id, self.selected_team_id, self.team_global_edit],
            outputs=[self.team_global_edit],
            show_progress="hidden",
        ).then(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
        ).then(
            self.refresh_team_dropdowns,
            inputs=[self._app.user_id],
            outputs=[self.team_new, self.team_edit, self.role_new, self.default_team_new, self.default_team_edit],
        )

        self.btn_team_delete.click(
            self.delete_team,
            inputs=[self._app.user_id, self.selected_team_id],
            outputs=[self.selected_team_id],
            show_progress="hidden",
        ).then(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
        ).then(
            self.refresh_team_dropdowns,
            inputs=[self._app.user_id],
            outputs=[self.team_new, self.team_edit, self.role_new, self.default_team_new, self.default_team_edit],
        )

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.refresh_user_list_view,
                "inputs": [self._app.user_id, self.user_sort_column, self.user_sort_ascending],
                "outputs": [self.state_user_list, self.user_list],
            },
        )
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.list_teams_ui,
                "inputs": [self._app.user_id],
                "outputs": [self.team_state, self.team_list],
            },
        )
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.refresh_team_dropdowns,
                "inputs": [self._app.user_id],
                "outputs": [self.team_new, self.team_edit, self.role_new, self.default_team_new, self.default_team_edit],
            },
        )
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": lambda: (
                    "",
                    "",
                    "",
                    [],
                    self._user_placeholder_frame(),
                    -1,
                    [],
                    pd.DataFrame.from_records([{"id": "-", "name": "-", "global": "-"}]),
                    None,
                    False,
                    gr.update(choices=[("Kein Standardteam", "")], value=""),
                    gr.update(choices=[("Kein Standardteam", "")], value=""),
                ),
                "outputs": [
                    self.usn_new,
                    self.pwd_new,
                    self.pwd_cnf_new,
                    self.state_user_list,
                    self.user_list,
                    self.selected_user_id,
                    self.team_state,
                    self.team_list,
                    self.selected_team_id,
                    self.team_global_edit,
                    self.default_team_new,
                    self.default_team_edit,
                ],
            },
        )

    def refresh_team_dropdowns(self, actor_user_id):
        choices = self._team_choices_for_actor(actor_user_id)
        default_choices = self._default_team_choices_for_actor(actor_user_id)
        role_choices = self._role_choices_for_actor(actor_user_id)
        role_value = ROLE_USER if ROLE_USER in role_choices else role_choices[0]
        return (
            gr.update(choices=choices),
            gr.update(choices=choices),
            gr.update(choices=role_choices, value=role_value),
            gr.update(choices=default_choices, value=""),
            gr.update(choices=default_choices, value=""),
        )

    def _user_placeholder_frame(self):
        return pd.DataFrame.from_records([{column: "-" for column in self.USER_LIST_COLUMNS}])

    def _sort_value(self, value):
        if isinstance(value, str):
            if value == "-":
                return (1, "")
            return (0, value.lower())
        if value is None:
            return (1, "")
        return (0, value)

    def apply_user_sort(self, user_rows, sort_column, ascending):
        rows = list(user_rows or [])
        if not rows:
            return self._user_placeholder_frame()

        if sort_column not in self.USER_LIST_COLUMNS:
            sort_column = "username"

        rows.sort(
            key=lambda row: self._sort_value(row.get(sort_column)),
            reverse=not bool(ascending),
        )
        return pd.DataFrame.from_records(rows, columns=self.USER_LIST_COLUMNS)

    def refresh_user_list_view(self, actor_user_id, sort_column, ascending):
        user_rows = self.list_users(actor_user_id)
        return user_rows, self.apply_user_sort(user_rows, sort_column, ascending)

    def list_teams_ui(self, actor_user_id):
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                return [], pd.DataFrame.from_records([{"id": "-", "name": "-", "global": "-"}])

            teams = list_teams(session)
            rows = [{"id": t.id, "name": t.name, "global": bool(getattr(t, "is_global", False))} for t in teams]
            if not rows:
                rows = [{"id": "-", "name": "-", "global": "-"}]
            return rows, pd.DataFrame.from_records(rows)

    def on_selected_team_change(self, team_rows, selected_team_id):
        if not selected_team_id:
            return gr.update(value=False)
        for row in team_rows or []:
            if row.get("id") == selected_team_id:
                return gr.update(value=bool(row.get("global", False)))
        return gr.update(value=False)

    def select_team(self, team_rows, ev: gr.SelectData):
        if (ev.value == "-" and ev.index[0] == 0) or not ev.selected:
            return None
        return team_rows[ev.index[0]]["id"]

    def create_team(self, actor_user_id, team_name):
        team_name = (team_name or "").strip()
        if not team_name:
            gr.Warning("Teamname darf nicht leer sein")
            return team_name
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                gr.Warning("Nur Admin darf Teams erstellen")
                return team_name

            exists = session.exec(select(Team).where(Team.name == team_name)).first()
            if exists:
                gr.Warning(f'Team "{team_name}" existiert bereits')
                return team_name

            # Backward compatibility for existing databases that still have
            # the legacy `name_lower` column on team table.
            if _team_table_has_name_lower(session):
                session.exec(
                    text(
                        "INSERT INTO team (id, name, name_lower, is_global) VALUES (:id, :name, :name_lower, :is_global)"
                    ).bindparams(
                        id=uuid.uuid4().hex,
                        name=team_name,
                        name_lower=team_name.lower(),
                        is_global=False,
                    )
                )
                session.commit()
            else:
                session.add(Team(name=team_name, is_global=False))
                session.commit()
            gr.Info(f'Team "{team_name}" erstellt')
            return ""

    def save_team_global_status(self, actor_user_id, team_id, is_global):
        if not team_id:
            gr.Warning("Kein Team ausgewählt")
            return gr.update(value=bool(is_global))
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                gr.Warning("Nur Admin darf Team-Status ändern")
                return gr.update(value=bool(is_global))

            team = session.exec(select(Team).where(Team.id == team_id)).first()
            if not team:
                gr.Warning("Team nicht gefunden")
                return gr.update(value=bool(is_global))

            team.is_global = bool(is_global)
            session.add(team)
            session.commit()
            gr.Info(f'Team "{team.name}" aktualisiert')
            return gr.update(value=bool(team.is_global))

    def delete_team(self, actor_user_id, team_id):
        if not team_id:
            gr.Warning("Kein Team ausgewählt")
            return None
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                gr.Warning("Nur Admin darf Teams löschen")
                return team_id

            accesses = session.exec(select(UserAccess)).all()
            in_membership_use = any(team_id in parse_team_ids(access.team_id) for access in accesses)
            in_default_use = any(access.default_team_id == team_id for access in accesses)
            if in_membership_use or in_default_use:
                gr.Warning("Team kann nicht gelöscht werden, solange Benutzer zugeordnet sind oder es als Standardteam verwendet wird")
                return team_id

            team = session.exec(select(Team).where(Team.id == team_id)).first()
            if not team:
                gr.Warning("Team nicht gefunden")
                return None
            session.delete(team)
            session.commit()
            gr.Info(f'Team "{team.name}" gelöscht')
            return None

    def create_user(
        self,
        actor_user_id,
        usn,
        pwd,
        pwd_cnf,
        role,
        team_ids,
        default_team_id,
        can_read,
        can_upload,
    ):
        team_ids = team_ids or []
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf

        errors = validate_password(pwd, pwd_cnf)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf

        role_err = assert_role_supported(role)
        if role_err:
            gr.Warning(role_err)
            return usn, pwd, pwd_cnf

        role_team_err = _validate_role_team_constraints(role, team_ids)
        if role_team_err:
            gr.Warning(role_team_err)
            return usn, pwd, pwd_cnf

        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor:
                return usn, pwd, pwd_cnf

            encoded_team_ids = encode_team_ids(team_ids)
            if not can_create_role(session, actor, role, encoded_team_ids):
                gr.Warning("Du darfst diesen Benutzer/Rolle-Team nicht anlegen")
                return usn, pwd, pwd_cnf

            for team_id in team_ids:
                if not team_exists(session, team_id):
                    gr.Warning("Team existiert nicht")
                    return usn, pwd, pwd_cnf

            existing = session.exec(select(User).where(User.username_lower == usn.lower())).first()
            if existing:
                gr.Warning(f'Benutzername "{usn}" existiert bereits')
                return usn, pwd, pwd_cnf

            normalized_default_team_id = normalize_default_team_id(
                session, actor, role, encoded_team_ids, default_team_id
            )
            if default_team_id and not normalized_default_team_id:
                gr.Warning("Ungültiges Standardteam für diesen Benutzer")
                return usn, pwd, pwd_cnf

            hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
            user = User(
                username=usn,
                username_lower=usn.lower(),
                password=hashed_password,
                admin=(role == ROLE_ADMIN),
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            can_read_norm, can_upload_norm = _normalize_role_permissions(
                role, can_read, can_upload
            )
            upsert_user_access(
                session=session,
                user_id=user.id,
                role=role,
                team_id=encoded_team_ids,
                can_read=can_read_norm,
                can_upload=can_upload_norm,
                default_team_id=normalized_default_team_id,
            )

            gr.Info(f'Benutzer "{usn}" erfolgreich erstellt')
            return "", "", ""

    def list_users(self, actor_user_id):
        if actor_user_id is None:
            return []

        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor:
                return []

            teams = {t.id: t.name for t in list_teams(session)}
            users = session.exec(select(User)).all()
            results = []
            for user in users:
                # Ensure role/team data is available and migrated for each user.
                access = ensure_user_access(session, user)

                if actor.is_admin:
                    allowed = True
                elif actor.is_key_user:
                    actor_team_ids = managed_team_ids(session, actor)
                    target_team_ids = set(parse_team_ids(access.team_id))
                    allowed = (
                        bool(actor_team_ids.intersection(target_team_ids))
                    ) or user.id == actor.user.id
                else:
                    allowed = user.id == actor.user.id

                team_names = [
                    teams.get(team_id, team_id) for team_id in parse_team_ids(access.team_id)
                ]
                team_label = ", ".join(team_names) if team_names else "-"

                if not allowed:
                    continue

                default_team_label = teams.get(access.default_team_id, access.default_team_id) if access.default_team_id else "-"
                results.append(
                    {
                        "id": user.id,
                        "username": user.username,
                        "role": access.role,
                        "team": team_label,
                        "standardteam": default_team_label,
                        "can_read": access.can_read,
                        "can_upload": access.can_upload,
                    }
                )

            if not results:
                return []
            return results

    def select_user(self, user_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Kein Benutzer geladen. Bitte die Benutzerliste aktualisieren")
            return -1
        if not ev.selected:
            return -1
        return user_list["id"][ev.index[0]]

    def on_selected_user_change(self, actor_user_id, selected_user_id):
        if selected_user_id == -1:
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=ROLE_USER),
                gr.update(value=[], choices=[]),
                gr.update(value="", choices=[("Kein Standardteam", "")]),
                gr.update(value=True),
                gr.update(value=False),
            )

        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == selected_user_id)).first()
            access = ensure_user_access(session, user) if user else None
            choices = self._team_choices_for_actor(actor_user_id)
            default_choices = self._default_team_choices_for_actor(actor_user_id)

            if not user or not access:
                return (
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=""),
                    gr.update(value=ROLE_USER),
                    gr.update(value=[], choices=choices),
                    gr.update(value="", choices=default_choices),
                    gr.update(value=True),
                    gr.update(value=False),
                )

            return (
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=user.username),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=access.role),
                gr.update(value=parse_team_ids(access.team_id), choices=choices),
                gr.update(value=access.default_team_id or "", choices=default_choices),
                gr.update(value=access.can_read),
                gr.update(value=access.can_upload),
            )

    def on_btn_delete_click(self, selected_user_id):
        if selected_user_id is None:
            gr.Warning("Kein Benutzer ausgewählt")
            return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
        return gr.update(visible=False), gr.update(visible=True), gr.update(visible=True)

    def save_user(
        self,
        actor_user_id,
        selected_user_id,
        usn,
        pwd,
        pwd_cnf,
        role,
        team_ids,
        default_team_id,
        can_read,
        can_upload,
    ):
        team_ids = team_ids or []
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return pwd, pwd_cnf

        role_err = assert_role_supported(role)
        if role_err:
            gr.Warning(role_err)
            return pwd, pwd_cnf

        role_team_err = _validate_role_team_constraints(role, team_ids)
        if role_team_err:
            gr.Warning(role_team_err)
            return pwd, pwd_cnf

        if pwd:
            errors = validate_password(pwd, pwd_cnf)
            if errors:
                gr.Warning(errors)
                return pwd, pwd_cnf

        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor:
                return pwd, pwd_cnf

            target_user = session.exec(
                select(User).where(User.id == selected_user_id)
            ).first()
            target_access = ensure_user_access(session, target_user) if target_user else None
            if not target_user or not target_access:
                gr.Warning("Benutzer nicht gefunden")
                return pwd, pwd_cnf

            is_self = actor.user.id == selected_user_id
            if not is_self and not can_manage_user(session, actor, target_access):
                gr.Warning("Keine Berechtigung zur Bearbeitung dieses Benutzers")
                return pwd, pwd_cnf

            encoded_team_ids = encode_team_ids(team_ids)
            if is_self and not actor.is_admin:
                if role != target_access.role or encoded_team_ids != target_access.team_id or bool(can_read) != bool(target_access.can_read) or bool(can_upload) != bool(target_access.can_upload):
                    gr.Warning("Du darfst für dich selbst nur das Standardteam ändern")
                    return pwd, pwd_cnf
            elif not can_create_role(session, actor, role, encoded_team_ids):
                gr.Warning("Keine Berechtigung für diese Rolle/Team-Zuordnung")
                return pwd, pwd_cnf

            for team_id in team_ids:
                if not team_exists(session, team_id):
                    gr.Warning("Team existiert nicht")
                    return pwd, pwd_cnf

            existing = session.exec(
                select(User).where(
                    User.username_lower == usn.lower(), User.id != selected_user_id
                )
            ).first()
            if existing:
                gr.Warning(
                    f'Benutzername "{usn}" existiert bereits. Bitte einen eindeutigen Namen verwenden.'
                )
                return pwd, pwd_cnf

            normalized_default_team_id = normalize_default_team_id(
                session, actor, role, encoded_team_ids, default_team_id
            )
            if default_team_id and not normalized_default_team_id:
                gr.Warning("Ungültiges Standardteam für diesen Benutzer")
                return pwd, pwd_cnf

            target_user.username = usn
            target_user.username_lower = usn.lower()
            target_user.admin = role == ROLE_ADMIN
            if pwd:
                target_user.password = hashlib.sha256(pwd.encode()).hexdigest()
            session.add(target_user)
            session.commit()

            can_read_norm, can_upload_norm = _normalize_role_permissions(
                role, can_read, can_upload
            )
            upsert_user_access(
                session=session,
                user_id=target_user.id,
                role=role,
                team_id=encoded_team_ids,
                can_read=can_read_norm,
                can_upload=can_upload_norm,
                default_team_id=normalized_default_team_id,
            )
            gr.Info(f'Benutzer "{usn}" erfolgreich aktualisiert')
            return "", ""

    def delete_user(self, current_user, selected_user_id):
        if current_user == selected_user_id:
            gr.Warning("Du kannst dich nicht selbst löschen")
            return selected_user_id

        with Session(engine) as session:
            actor = _resolve_actor(session, current_user)
            if not actor:
                return selected_user_id

            target_user = session.exec(
                select(User).where(User.id == selected_user_id)
            ).first()
            target_access = ensure_user_access(session, target_user) if target_user else None
            if not target_user or not target_access:
                gr.Warning("Benutzer nicht gefunden")
                return -1

            if not can_manage_user(session, actor, target_access):
                gr.Warning("Keine Berechtigung, diesen Benutzer zu löschen")
                return selected_user_id

            access_row = session.exec(
                select(UserAccess).where(UserAccess.user_id == selected_user_id)
            ).first()
            if access_row:
                session.delete(access_row)
            session.delete(target_user)
            session.commit()
            gr.Info(f'Benutzer "{target_user.username}" erfolgreich gelöscht')
            return -1
