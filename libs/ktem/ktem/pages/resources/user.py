import hashlib
import json
import uuid

import gradio as gr
import pandas as pd
from ktem.app import BasePage
from ktem.db.models import User, engine
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


fetch_team_state_js = """
function(userId, currentValue) {
    const key = `kaidoku_team_state_${userId || 'anonymous'}`;
    return [userId, getStorage(key, currentValue || '')];
}
"""


save_team_state_js = """
function(userId, teamState) {
    const key = `kaidoku_team_state_${userId || 'anonymous'}`;
    const serialized = JSON.stringify(teamState || {teams: [], user_teams: {}});
    setStorage(key, serialized);
    return serialized;
}
"""


def default_team_state():
    return {"teams": [], "user_teams": {}}


def normalize_team_state(team_state):
    state = default_team_state()
    if not isinstance(team_state, dict):
        return state

    teams = []
    for team in team_state.get("teams", []):
        if not isinstance(team, dict):
            continue
        team_id = str(team.get("id", "")).strip()
        team_name = str(team.get("name", "")).strip()
        if team_id and team_name:
            teams.append({"id": team_id, "name": team_name})

    valid_team_ids = {team["id"] for team in teams}
    user_teams = {}
    for username, team_ids in team_state.get("user_teams", {}).items():
        if not isinstance(team_ids, list):
            continue
        filtered_ids = [team_id for team_id in team_ids if team_id in valid_team_ids]
        user_teams[str(username).lower()] = filtered_ids

    state["teams"] = teams
    state["user_teams"] = user_teams
    return state


def get_team_choices(team_state):
    state = normalize_team_state(team_state)
    return [(team["name"], team["id"]) for team in state["teams"]]


def get_team_names_for_user(username_lower, team_state):
    state = normalize_team_state(team_state)
    team_lookup = {team["id"]: team["name"] for team in state["teams"]}
    team_ids = state["user_teams"].get(username_lower.lower(), [])
    return [team_lookup[team_id] for team_id in team_ids if team_id in team_lookup]


def format_team_names(team_names):
    return ", ".join(team_names) if team_names else "-"


def render_team_badges(team_names):
    if not team_names:
        return "<div>Keine Teams zugeordnet</div>"

    badges = "".join(
        (
            "<span style='display:inline-block;padding:4px 10px;margin:0 6px 6px 0;"
            "border-radius:999px;background:var(--background-fill-secondary);"
            "border:1px solid var(--border-color-primary);font-size:12px;'>"
            f"{team_name}</span>"
        )
        for team_name in team_names
    )
    return f"<div>{badges}</div>"


def validate_username(usn):
    """Validate that whether username is valid

    Args:
        usn (str): Username
    """
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
    """Validate that whether password is valid

    - Password must be at least 8 characters long
    - Password must contain at least one uppercase letter
    - Password must contain at least one lowercase letter
    - Password must contain at least one digit
    - Password must contain at least one special character from the following:
        ^ $ * . [ ] { } ( ) ? - " ! @ # % & / \\ , > < ' : ; | _ ~  + =

    Args:
        pwd (str): Password
        pwd_cnf (str): Confirm password

    Returns:
        str: Error message if password is not valid
    """
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

    if errors:
        return "; ".join(errors)

    return ""


def create_user(usn, pwd, user_id=None, is_admin=True) -> bool:
    with Session(engine) as session:
        statement = select(User).where(User.username_lower == usn.lower())
        result = session.exec(statement).all()
        if result:
            print(f'User "{usn}" already exists')
            return False

        else:
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

            return True


class UserManagement(BasePage):
    def __init__(self, app):
        self._app = app

        self.on_building_ui()
        if hasattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_ADMIN") and hasattr(
            flowsettings, "KH_FEATURE_USER_MANAGEMENT_PASSWORD"
        ):
            usn = flowsettings.KH_FEATURE_USER_MANAGEMENT_ADMIN
            pwd = flowsettings.KH_FEATURE_USER_MANAGEMENT_PASSWORD

            is_created = create_user(usn, pwd)
            if is_created:
                gr.Info(f'Benutzer "{usn}" erfolgreich erstellt')

    def on_building_ui(self):
        self.team_state = gr.State(value=default_team_state())
        self.team_state_storage = gr.Textbox(visible=False, value="")

        with gr.Tab(label="Benutzerliste"):
            self.state_user_list = gr.State(value=None)
            self.user_list = gr.DataFrame(
                headers=["id", "username", "admin", "teams"],
                column_widths=[0, 35, 15, 50],
                interactive=False,
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
                self.admin_edit = gr.Checkbox(label="Administrator")
                self.user_teams_edit = gr.Dropdown(
                    label="Teams",
                    choices=[],
                    value=[],
                    multiselect=True,
                    allow_custom_value=False,
                )
                self.user_teams_badges = gr.HTML("Keine Teams zugeordnet")

            with gr.Row(visible=False) as self._selected_panel_btn:
                with gr.Column():
                    self.btn_edit_save = gr.Button("Speichern")
                with gr.Column():
                    self.btn_delete = gr.Button("Löschen")
                    with gr.Row():
                        self.btn_delete_yes = gr.Button(
                            "Löschen bestätigen", variant="primary", visible=False
                        )
                        self.btn_delete_no = gr.Button("Abbrechen", visible=False)
                with gr.Column():
                    self.btn_close = gr.Button("Schließen")

        with gr.Tab(label="Benutzer anlegen"):
            self.usn_new = gr.Textbox(label="Benutzername", interactive=True)
            self.pwd_new = gr.Textbox(
                label="Passwort", type="password", interactive=True
            )
            self.pwd_cnf_new = gr.Textbox(
                label="Passwort bestätigen", type="password", interactive=True
            )
            self.user_teams_new = gr.Dropdown(
                label="Teams",
                choices=[],
                value=[],
                multiselect=True,
                allow_custom_value=False,
            )
            with gr.Row():
                gr.Markdown(USERNAME_RULE)
                gr.Markdown(PASSWORD_RULE)
            self.btn_new = gr.Button("Benutzer anlegen")

        with gr.Tab(label="Teams verwalten"):
            self.state_team_list = gr.State(value=None)
            self.team_list = gr.DataFrame(
                headers=["id", "team", "mitglieder"],
                column_widths=[0, 35, 65],
                interactive=False,
            )

            with gr.Group(visible=False) as self._selected_team_panel:
                self.selected_team_id = gr.State(value="")
                self.team_name_edit = gr.Textbox(label="Teamname")

            with gr.Row(visible=False) as self._selected_team_panel_btn:
                self.btn_team_save = gr.Button("Umbenennen")
                self.btn_team_delete = gr.Button("Löschen")
                self.btn_team_close = gr.Button("Schließen")

            self.team_name_new = gr.Textbox(label="Neues Team", interactive=True)
            self.btn_team_new = gr.Button("Team erstellen")

    def on_register_events(self):
        self.btn_new.click(
            self.create_user,
            inputs=[
                self.usn_new,
                self.pwd_new,
                self.pwd_cnf_new,
                self.user_teams_new,
                self.team_state,
            ],
            outputs=[
                self.usn_new,
                self.pwd_new,
                self.pwd_cnf_new,
                self.user_teams_new,
                self.team_state,
            ],
        ).then(
            self.refresh_management_views,
            inputs=[self._app.user_id, self.team_state],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
        ).then(
            fn=None,
            inputs=[self._app.user_id, self.team_state],
            outputs=[self.team_state_storage],
            js=save_team_state_js,
        )
        self.user_list.select(
            self.select_user,
            inputs=self.user_list,
            outputs=[self.selected_user_id],
            show_progress="hidden",
        )
        self.selected_user_id.change(
            self.on_selected_user_change,
            inputs=[self.selected_user_id, self.team_state],
            outputs=[
                self._selected_panel,
                self._selected_panel_btn,
                # delete section
                self.btn_delete,
                self.btn_delete_yes,
                self.btn_delete_no,
                # edit section
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.admin_edit,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
            show_progress="hidden",
        )
        self.user_teams_edit.change(
            lambda team_ids, team_state: render_team_badges(
                [
                    name
                    for name, team_id in get_team_choices(team_state)
                    if team_id in (team_ids or [])
                ]
            ),
            inputs=[self.user_teams_edit, self.team_state],
            outputs=[self.user_teams_badges],
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
            inputs=[self._app.user_id, self.selected_user_id, self.team_state],
            outputs=[self.selected_user_id, self.team_state],
            show_progress="hidden",
        ).then(
            self.refresh_management_views,
            inputs=[self._app.user_id, self.team_state],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
        ).then(
            fn=None,
            inputs=[self._app.user_id, self.team_state],
            outputs=[self.team_state_storage],
            js=save_team_state_js,
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
                self.selected_user_id,
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.admin_edit,
                self.user_teams_edit,
                self.team_state,
            ],
            outputs=[self.pwd_edit, self.pwd_cnf_edit, self.team_state],
            show_progress="hidden",
        ).then(
            self.refresh_management_views,
            inputs=[self._app.user_id, self.team_state],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
        ).then(
            fn=None,
            inputs=[self._app.user_id, self.team_state],
            outputs=[self.team_state_storage],
            js=save_team_state_js,
        )
        self.btn_close.click(
            lambda: -1,
            outputs=[self.selected_user_id],
        )
        self.team_list.select(
            self.select_team,
            inputs=self.team_list,
            outputs=[self.selected_team_id],
            show_progress="hidden",
        )
        self.selected_team_id.change(
            self.on_selected_team_change,
            inputs=[self.selected_team_id, self.team_state],
            outputs=[
                self._selected_team_panel,
                self._selected_team_panel_btn,
                self.team_name_edit,
            ],
            show_progress="hidden",
        )
        self.btn_team_new.click(
            self.create_team,
            inputs=[self.team_name_new, self.team_state],
            outputs=[self.team_name_new, self.team_state],
            show_progress="hidden",
        ).then(
            self.refresh_management_views,
            inputs=[self._app.user_id, self.team_state],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
        ).then(
            fn=None,
            inputs=[self._app.user_id, self.team_state],
            outputs=[self.team_state_storage],
            js=save_team_state_js,
        )
        self.btn_team_save.click(
            self.rename_team,
            inputs=[self.selected_team_id, self.team_name_edit, self.team_state],
            outputs=[self.team_name_edit, self.team_state],
            show_progress="hidden",
        ).then(
            self.refresh_management_views,
            inputs=[self._app.user_id, self.team_state],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
        ).then(
            fn=None,
            inputs=[self._app.user_id, self.team_state],
            outputs=[self.team_state_storage],
            js=save_team_state_js,
        )
        self.btn_team_delete.click(
            self.delete_team,
            inputs=[self.selected_team_id, self.team_state],
            outputs=[self.selected_team_id, self.team_state],
            show_progress="hidden",
        ).then(
            self.refresh_management_views,
            inputs=[self._app.user_id, self.team_state],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
        ).then(
            fn=None,
            inputs=[self._app.user_id, self.team_state],
            outputs=[self.team_state_storage],
            js=save_team_state_js,
        )
        self.btn_team_close.click(lambda: "", outputs=[self.selected_team_id])

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.load_team_state_and_refresh,
                "inputs": [self._app.user_id, self.team_state_storage],
                "outputs": [
                    self.team_state,
                    self.state_user_list,
                    self.user_list,
                    self.state_team_list,
                    self.team_list,
                    self.user_teams_new,
                    self.user_teams_edit,
                    self.user_teams_badges,
                ],
                "js": fetch_team_state_js,
            },
        )
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": lambda team_state: (
                    "",
                    "",
                    "",
                    gr.update(choices=get_team_choices(team_state), value=[]),
                    None,
                    None,
                    -1,
                    "",
                    "",
                    gr.update(choices=get_team_choices(team_state), value=[]),
                    render_team_badges([]),
                ),
                "inputs": [self.team_state],
                "outputs": [
                    self.usn_new,
                    self.pwd_new,
                    self.pwd_cnf_new,
                    self.user_teams_new,
                    self.state_user_list,
                    self.user_list,
                    self.selected_user_id,
                    self.team_name_new,
                    self.selected_team_id,
                    self.user_teams_edit,
                    self.user_teams_badges,
                ],
            },
        )

    def create_user(self, usn, pwd, pwd_cnf, team_ids, team_state):
        team_state = normalize_team_state(team_state)
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf, team_ids, team_state

        errors = validate_password(pwd, pwd_cnf)
        print(errors)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf, team_ids, team_state

        with Session(engine) as session:
            statement = select(User).where(User.username_lower == usn.lower())
            result = session.exec(statement).all()
            if result:
                gr.Warning(f'Benutzername "{usn}" existiert bereits')
                return usn, pwd, pwd_cnf, team_ids, team_state

            try:
                hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
                user = User(
                    username=usn, username_lower=usn.lower(), password=hashed_password
                )
                session.add(user)
                session.commit()
                team_state["user_teams"][usn.lower()] = list(team_ids or [])
                gr.Info(f'Benutzer "{usn}" erfolgreich erstellt')
            except Exception as e:
                session.rollback()
                gr.Warning(f'Benutzer "{usn}" konnte nicht erstellt werden: {e}')
                return usn, pwd, pwd_cnf, team_ids, team_state

        return "", "", "", [], team_state

    def list_users(self, user_id, team_state):
        team_state = normalize_team_state(team_state)
        if user_id is None:
            return [], pd.DataFrame.from_records(
                [{"id": "-", "username": "-", "admin": "-", "teams": "-"}]
            )

        with Session(engine) as session:
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).one()
            if not user.admin:
                return [], pd.DataFrame.from_records(
                    [{"id": "-", "username": "-", "admin": "-", "teams": "-"}]
                )

            statement = select(User)
            results = [
                {
                    "id": user.id,
                    "username": user.username,
                    "admin": user.admin,
                    "teams": format_team_names(
                        get_team_names_for_user(user.username_lower, team_state)
                    ),
                }
                for user in session.exec(statement).all()
            ]
            if results:
                user_list = pd.DataFrame.from_records(results)
            else:
                user_list = pd.DataFrame.from_records(
                    [{"id": "-", "username": "-", "admin": "-", "teams": "-"}]
                )

        return results, user_list

    def list_teams(self, team_state):
        team_state = normalize_team_state(team_state)
        with Session(engine) as session:
            users = session.exec(select(User)).all()

        rows = []
        for team in team_state["teams"]:
            members = [
                user.username
                for user in users
                if team["id"] in team_state["user_teams"].get(user.username_lower, [])
            ]
            rows.append(
                {
                    "id": team["id"],
                    "team": team["name"],
                    "mitglieder": ", ".join(members) if members else "-",
                }
            )

        if not rows:
            return [], pd.DataFrame.from_records(
                [{"id": "-", "team": "-", "mitglieder": "-"}]
            )

        return rows, pd.DataFrame.from_records(rows)

    def refresh_management_views(self, user_id, team_state):
        team_state = normalize_team_state(team_state)
        user_rows, user_df = self.list_users(user_id, team_state)
        team_rows, team_df = self.list_teams(team_state)
        empty_choices = gr.update(choices=get_team_choices(team_state), value=[])

        return (
            team_state,
            user_rows,
            user_df,
            team_rows,
            team_df,
            empty_choices,
            empty_choices,
            render_team_badges([]),
        )

    def load_team_state_and_refresh(self, user_id, team_state_storage):
        team_state = default_team_state()
        if team_state_storage:
            try:
                team_state = normalize_team_state(json.loads(team_state_storage))
            except Exception:
                team_state = default_team_state()
        return self.refresh_management_views(user_id, team_state)

    def select_user(self, user_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Kein Benutzer geladen. Bitte die Benutzerliste aktualisieren")
            return -1

        if not ev.selected:
            return -1

        return user_list["id"][ev.index[0]]

    def on_selected_user_change(self, selected_user_id, team_state):
        team_state = normalize_team_state(team_state)
        if selected_user_id == -1:
            _selected_panel = gr.update(visible=False)
            _selected_panel_btn = gr.update(visible=False)
            btn_delete = gr.update(visible=True)
            btn_delete_yes = gr.update(visible=False)
            btn_delete_no = gr.update(visible=False)
            usn_edit = gr.update(value="")
            pwd_edit = gr.update(value="")
            pwd_cnf_edit = gr.update(value="")
            admin_edit = gr.update(value=False)
            user_teams_edit = gr.update(choices=get_team_choices(team_state), value=[])
            user_teams_badges = render_team_badges([])
        else:
            _selected_panel = gr.update(visible=True)
            _selected_panel_btn = gr.update(visible=True)
            btn_delete = gr.update(visible=True)
            btn_delete_yes = gr.update(visible=False)
            btn_delete_no = gr.update(visible=False)

            with Session(engine) as session:
                statement = select(User).where(User.id == selected_user_id)
                user = session.exec(statement).one()

            usn_edit = gr.update(value=user.username)
            pwd_edit = gr.update(value="")
            pwd_cnf_edit = gr.update(value="")
            admin_edit = gr.update(value=user.admin)
            selected_team_ids = team_state["user_teams"].get(user.username_lower, [])
            selected_team_names = get_team_names_for_user(user.username_lower, team_state)
            user_teams_edit = gr.update(
                choices=get_team_choices(team_state),
                value=selected_team_ids,
            )
            user_teams_badges = render_team_badges(selected_team_names)

        return (
            _selected_panel,
            _selected_panel_btn,
            btn_delete,
            btn_delete_yes,
            btn_delete_no,
            usn_edit,
            pwd_edit,
            pwd_cnf_edit,
            admin_edit,
            user_teams_edit,
            user_teams_badges,
        )

    def on_btn_delete_click(self, selected_user_id):
        if selected_user_id is None:
            gr.Warning("Kein Benutzer ausgewählt")
            btn_delete = gr.update(visible=True)
            btn_delete_yes = gr.update(visible=False)
            btn_delete_no = gr.update(visible=False)
            return

        btn_delete = gr.update(visible=False)
        btn_delete_yes = gr.update(visible=True)
        btn_delete_no = gr.update(visible=True)

        return btn_delete, btn_delete_yes, btn_delete_no

    def save_user(self, selected_user_id, usn, pwd, pwd_cnf, admin, team_ids, team_state):
        team_state = normalize_team_state(team_state)
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return pwd, pwd_cnf, team_state

        if pwd:
            errors = validate_password(pwd, pwd_cnf)
            if errors:
                gr.Warning(errors)
                return pwd, pwd_cnf, team_state

        with Session(engine) as session:
            # Check username uniqueness (excluding current user)
            statement = select(User).where(
                User.username_lower == usn.lower(),
                User.id != selected_user_id,
            )
            existing = session.exec(statement).first()
            if existing:
                gr.Warning(
                    f'Benutzername "{usn}" existiert bereits. Bitte einen eindeutigen Namen verwenden.'
                )
                return pwd, pwd_cnf, team_state

            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()
            old_username_lower = user.username_lower
            user.username = usn
            user.username_lower = usn.lower()
            user.admin = admin
            if pwd:
                user.password = hashlib.sha256(pwd.encode()).hexdigest()
            session.commit()
            if old_username_lower != user.username_lower:
                team_state["user_teams"][user.username_lower] = team_state["user_teams"].pop(
                    old_username_lower, []
                )
            team_state["user_teams"][user.username_lower] = list(team_ids or [])
            gr.Info(f'Benutzer "{usn}" erfolgreich aktualisiert')

        return "", "", team_state

    def delete_user(self, current_user, selected_user_id, team_state):
        team_state = normalize_team_state(team_state)
        if current_user == selected_user_id:
            gr.Warning("Du kannst dich nicht selbst löschen")
            return selected_user_id, team_state

        with Session(engine) as session:
            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()
            team_state["user_teams"].pop(user.username_lower, None)
            session.delete(user)
            session.commit()
            gr.Info(f'Benutzer "{user.username}" erfolgreich gelöscht')
        return -1, team_state

    def select_team(self, team_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Kein Team geladen")
            return ""

        if not ev.selected:
            return ""

        return team_list["id"][ev.index[0]]

    def on_selected_team_change(self, selected_team_id, team_state):
        team_state = normalize_team_state(team_state)
        if not selected_team_id:
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
            )

        team = next(
            (team for team in team_state["teams"] if team["id"] == selected_team_id),
            None,
        )
        if team is None:
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
            )

        return (
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(value=team["name"]),
        )

    def create_team(self, team_name, team_state):
        team_state = normalize_team_state(team_state)
        team_name = team_name.strip()
        if not team_name:
            gr.Warning("Der Teamname darf nicht leer sein")
            return team_name, team_state

        if any(team["name"].lower() == team_name.lower() for team in team_state["teams"]):
            gr.Warning(f'Team "{team_name}" existiert bereits')
            return team_name, team_state

        team_state["teams"].append({"id": uuid.uuid4().hex, "name": team_name})
        gr.Info(f'Team "{team_name}" erfolgreich erstellt')
        return "", team_state

    def rename_team(self, selected_team_id, team_name, team_state):
        team_state = normalize_team_state(team_state)
        team_name = team_name.strip()
        if not selected_team_id:
            gr.Warning("Kein Team ausgewählt")
            return team_name, team_state
        if not team_name:
            gr.Warning("Der Teamname darf nicht leer sein")
            return team_name, team_state

        for team in team_state["teams"]:
            if team["id"] != selected_team_id and team["name"].lower() == team_name.lower():
                gr.Warning(f'Team "{team_name}" existiert bereits')
                return team_name, team_state

        for team in team_state["teams"]:
            if team["id"] == selected_team_id:
                team["name"] = team_name
                gr.Info(f'Team "{team_name}" erfolgreich umbenannt')
                return team_name, team_state

        gr.Warning("Team nicht gefunden")
        return team_name, team_state

    def delete_team(self, selected_team_id, team_state):
        team_state = normalize_team_state(team_state)
        if not selected_team_id:
            gr.Warning("Kein Team ausgewählt")
            return selected_team_id, team_state

        team = next(
            (team for team in team_state["teams"] if team["id"] == selected_team_id),
            None,
        )
        if team is None:
            gr.Warning("Team nicht gefunden")
            return "", team_state

        team_state["teams"] = [
            team for team in team_state["teams"] if team["id"] != selected_team_id
        ]
        for username, team_ids in team_state["user_teams"].items():
            team_state["user_teams"][username] = [
                team_id for team_id in team_ids if team_id != selected_team_id
            ]

        gr.Info(f'Team "{team["name"]}" erfolgreich gelöscht')
        return "", team_state

    def _on_app_created(self):
        self._app.app.load(
            self.load_team_state_and_refresh,
            inputs=[self._app.user_id, self.team_state_storage],
            outputs=[
                self.team_state,
                self.state_user_list,
                self.user_list,
                self.state_team_list,
                self.team_list,
                self.user_teams_new,
                self.user_teams_edit,
                self.user_teams_badges,
            ],
            show_progress="hidden",
            js=fetch_team_state_js,
        )
