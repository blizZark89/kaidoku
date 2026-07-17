import hashlib

import gradio as gr
from ktem.app import BasePage
from ktem.db.models import User, engine
from ktem.external_auth import (
    ExternalAuthError,
    authenticate_ldap_user,
    get_authentication_method,
    get_session_user_id,
    is_ldap_auth,
    is_oidc_auth,
    sync_external_user,
)
from ktem.pages.resources.user import create_user
from sqlmodel import Session, select

fetch_creds = """
function() {
    const username = getStorage('username', '')
    const password = getStorage('password', '')
    return [username, password, null];
}
"""

signin_js = """
function(usn, pwd) {
    setStorage('username', usn);
    setStorage('password', pwd);
    return [usn, pwd];
}
"""

clear_storage_oauth_js = """
function() {
    removeFromStorage('username');
    removeFromStorage('password');
    return [];
}
"""


class LoginPage(BasePage):

    public_events = ["onSignIn"]

    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        gr.Markdown(f"# Willkommen bei {self._app.app_name}!")
        auth_method = get_authentication_method()
        self._is_oidc = is_oidc_auth()
        if self._is_oidc:
            gr.Markdown(
                "Die Anmeldung erfolgt ?ber Authentik. "
                "Verwende den Button unten, um den OIDC-Login zu starten."
            )
        elif is_ldap_auth():
            gr.Markdown("Die Anmeldung erfolgt direkt ?ber LDAP.")

        self.usn = gr.Textbox(label="Benutzername", visible=not self._is_oidc)
        self.pwd = gr.Textbox(
            label="Passwort", type="password", visible=not self._is_oidc
        )
        self.btn_login = gr.Button(
            "Anmelden" if auth_method != "AUTHENTIK" else "Sitzung pr?fen",
            visible=not self._is_oidc,
        )
        self.btn_oidc_login = gr.Button(
            "Mit Authentik anmelden", visible=self._is_oidc
        )
        if self._is_oidc:
            self.btn_oidc_login.click(
                fn=None,
                js="() => { window.location.href = '/login'; }",
            )

    def on_register_events(self):
        onSignIn = gr.on(
            triggers=[self.btn_login.click, self.pwd.submit],
            fn=self.login,
            inputs=[self.usn, self.pwd],
            outputs=[self._app.user_id, self.usn, self.pwd],
            show_progress="hidden",
            js=signin_js,
        ).then(
            self.toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[self.usn, self.pwd, self.btn_login],
        )
        for event in self._app.get_event("onSignIn"):
            onSignIn = onSignIn.success(**event)

    def toggle_login_visibility(self, user_id):
        return (
            gr.update(visible=user_id is None and not self._is_oidc),
            gr.update(visible=user_id is None and not self._is_oidc),
            gr.update(visible=user_id is None and not self._is_oidc),
        )

    def _on_app_created(self):
        load_js = clear_storage_oauth_js if self._is_oidc else fetch_creds
        onSignIn = self._app.app.load(
            self.login,
            inputs=[self.usn, self.pwd],
            outputs=[self._app.user_id, self.usn, self.pwd],
            show_progress="hidden",
            js=load_js,
        ).then(
            self.toggle_login_visibility,
            inputs=[self._app.user_id],
            outputs=[self.usn, self.pwd, self.btn_login],
        )
        for event in self._app.get_event("onSignIn"):
            onSignIn = onSignIn.success(**event)

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": self.toggle_login_visibility,
                "inputs": [self._app.user_id],
                "outputs": [self.usn, self.pwd, self.btn_login],
                "show_progress": "hidden",
            },
        )

    def login(self, usn, pwd, request: gr.Request):
        if is_oidc_auth():
            user_id = get_session_user_id(request)
            if not user_id:
                return None, usn, pwd
            with Session(engine) as session:
                user = session.exec(select(User).where(User.id == user_id)).first()
            if user:
                return user.id, "", ""
            gr.Warning(
                "OIDC-Sitzung gefunden, aber der Benutzer ist lokal nicht synchronisiert."
            )
            return None, usn, pwd

        if is_ldap_auth():
            if not usn or not pwd:
                return None, usn, pwd
            try:
                identity = authenticate_ldap_user(usn, pwd)
                user, decision = sync_external_user(identity)
            except ExternalAuthError as exc:
                gr.Warning(str(exc))
                return None, usn, pwd

            if user is None or not decision.can_access:
                gr.Warning(
                    decision.reason
                    or "LDAP-Anmeldung erfolgreich, aber keine passende Zugriffsgruppe gefunden."
                )
                return None, usn, ""
            return user.id, "", ""

        if not usn or not pwd:
            return None, usn, pwd

        hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
        with Session(engine) as session:
            stmt = select(User).where(
                User.username_lower == usn.lower().strip(),
                User.password == hashed_password,
            )
            result = session.exec(stmt).all()
            if result:
                return result[0].id, "", ""

            gr.Warning("Ung?ltiger Benutzername oder Passwort")
            return None, usn, pwd
