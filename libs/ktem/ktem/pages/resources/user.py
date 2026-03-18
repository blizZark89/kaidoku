import hashlib

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
        with gr.Tab(label="Benutzerliste"):
            self.state_user_list = gr.State(value=None)
            self.user_list = gr.DataFrame(
                headers=["id", "username", "admin"],
                column_widths=[0, 50, 50],
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
            with gr.Row():
                gr.Markdown(USERNAME_RULE)
                gr.Markdown(PASSWORD_RULE)
            self.btn_new = gr.Button("Benutzer anlegen")

    def on_register_events(self):
        self.btn_new.click(
            self.create_user,
            inputs=[self.usn_new, self.pwd_new, self.pwd_cnf_new],
            outputs=[self.usn_new, self.pwd_new, self.pwd_cnf_new],
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        )
        self.user_list.select(
            self.select_user,
            inputs=self.user_list,
            outputs=[self.selected_user_id],
            show_progress="hidden",
        )
        self.selected_user_id.change(
            self.on_selected_user_change,
            inputs=[self.selected_user_id],
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
            self.list_users,
            inputs=self._app.user_id,
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
                self.selected_user_id,
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.admin_edit,
            ],
            outputs=[self.pwd_edit, self.pwd_cnf_edit],
            show_progress="hidden",
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        )
        self.btn_close.click(
            lambda: -1,
            outputs=[self.selected_user_id],
        )

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.list_users,
                "inputs": [self._app.user_id],
                "outputs": [self.state_user_list, self.user_list],
            },
        )
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": lambda: ("", "", "", None, None, -1),
                "outputs": [
                    self.usn_new,
                    self.pwd_new,
                    self.pwd_cnf_new,
                    self.state_user_list,
                    self.user_list,
                    self.selected_user_id,
                ],
            },
        )

    def create_user(self, usn, pwd, pwd_cnf):
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf

        errors = validate_password(pwd, pwd_cnf)
        print(errors)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf

        with Session(engine) as session:
            statement = select(User).where(User.username_lower == usn.lower())
            result = session.exec(statement).all()
            if result:
                gr.Warning(f'Benutzername "{usn}" existiert bereits')
                return usn, pwd, pwd_cnf

            try:
                hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
                user = User(
                    username=usn, username_lower=usn.lower(), password=hashed_password
                )
                session.add(user)
                session.commit()
                gr.Info(f'Benutzer "{usn}" erfolgreich erstellt')
            except Exception as e:
                session.rollback()
                gr.Warning(f'Benutzer "{usn}" konnte nicht erstellt werden: {e}')
                return usn, pwd, pwd_cnf

        return "", "", ""

    def list_users(self, user_id):
        if user_id is None:
            return [], pd.DataFrame.from_records(
                [{"id": "-", "username": "-", "admin": "-"}]
            )

        with Session(engine) as session:
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).one()
            if not user.admin:
                return [], pd.DataFrame.from_records(
                    [{"id": "-", "username": "-", "admin": "-"}]
                )

            statement = select(User)
            results = [
                {"id": user.id, "username": user.username, "admin": user.admin}
                for user in session.exec(statement).all()
            ]
            if results:
                user_list = pd.DataFrame.from_records(results)
            else:
                user_list = pd.DataFrame.from_records(
                    [{"id": "-", "username": "-", "admin": "-"}]
                )

        return results, user_list

    def select_user(self, user_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Kein Benutzer geladen. Bitte die Benutzerliste aktualisieren")
            return -1

        if not ev.selected:
            return -1

        return user_list["id"][ev.index[0]]

    def on_selected_user_change(self, selected_user_id):
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

    def save_user(self, selected_user_id, usn, pwd, pwd_cnf, admin):
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return pwd, pwd_cnf

        if pwd:
            errors = validate_password(pwd, pwd_cnf)
            if errors:
                gr.Warning(errors)
                return pwd, pwd_cnf

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
                return pwd, pwd_cnf

            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()
            user.username = usn
            user.username_lower = usn.lower()
            user.admin = admin
            if pwd:
                user.password = hashlib.sha256(pwd.encode()).hexdigest()
            session.commit()
            gr.Info(f'Benutzer "{usn}" erfolgreich aktualisiert')

        return "", ""

    def delete_user(self, current_user, selected_user_id):
        if current_user == selected_user_id:
            gr.Warning("Du kannst dich nicht selbst löschen")
            return selected_user_id

        with Session(engine) as session:
            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()
            session.delete(user)
            session.commit()
            gr.Info(f'Benutzer "{user.username}" erfolgreich gelöscht')
        return -1
