import hashlib

import gradio as gr
from ktem.app import BasePage
from ktem.components import reasonings
from ktem.authz import get_access_context
from ktem.db.models import Settings, Team, User, engine
from ktem.external_auth import (
    can_manage_local_users,
    is_oidc_auth,
    local_user_management_block_reason,
)
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings

KH_SSO_ENABLED = getattr(flowsettings, "KH_SSO_ENABLED", False)


signout_js = """
function(u, c, pw, pwc) {
    removeFromStorage('username');
    removeFromStorage('password');
    return [u, c, pw, pwc];
}
"""

oidc_signout_js = """
function() {
    removeFromStorage('username');
    removeFromStorage('password');
    window.location.href = "/logout";
}
"""


gr_cls_single_value = {
    "text": gr.Textbox,
    "number": gr.Number,
    "checkbox": gr.Checkbox,
}


gr_cls_choices = {
    "dropdown": gr.Dropdown,
    "radio": gr.Radio,
    "checkboxgroup": gr.CheckboxGroup,
}


def render_setting_item(setting_item, value):
    """Render the setting component into corresponding Gradio UI component"""
    kwargs = {
        "label": setting_item.name,
        "value": value,
        "interactive": True,
    }

    if setting_item.component in gr_cls_single_value:
        return gr_cls_single_value[setting_item.component](**kwargs)

    kwargs["choices"] = setting_item.choices

    if setting_item.component in gr_cls_choices:
        return gr_cls_choices[setting_item.component](**kwargs)

    raise ValueError(
        f"Unknown component {setting_item.component}, allowed are: "
        f"{list(gr_cls_single_value.keys()) + list(gr_cls_choices.keys())}.\n"
        f"Setting item: {setting_item}"
    )


class SettingsPage(BasePage):
    """Responsible for allowing the users to customize the application

    **IMPORTANT**: the name and id of the UI setting components should match the
    name of the setting in the `app.default_settings`
    """

    public_events = ["onSignOut"]

    def __init__(self, app):
        """Initiate the page and render the UI"""
        self._app = app
        self._filesync_service = getattr(app, "file_sync_service", None)

        self._settings_state = app.settings_state
        self._user_id = app.user_id
        self._default_settings = app.default_settings
        self._settings_dict = self._default_settings.flatten()
        self._settings_keys = list(self._settings_dict.keys())

        self._components = {}
        self._reasoning_mode = {}

        # store llms and embeddings components
        self._llms = []
        self._embeddings = []

        # render application page if there are application settings
        self._render_app_tab = False

        if self._default_settings.application.settings:
            self._render_app_tab = True

        # render index page if there are index settings (general and/or specific)
        self._render_index_tab = False

        if self._default_settings.index.settings:
            self._render_index_tab = True
        else:
            for sig in self._default_settings.index.options.values():
                if sig.settings:
                    self._render_index_tab = True
                    break

        # render reasoning page if there are reasoning settings
        self._render_reasoning_tab = False

        if len(self._default_settings.reasoning.settings) > 1:
            self._render_reasoning_tab = True
        else:
            for sig in self._default_settings.reasoning.options.values():
                if sig.settings:
                    self._render_reasoning_tab = True
                    break

        self.on_building_ui()

    def on_building_ui(self):
        if True:
            self.setting_save_btn = gr.Button(
                "Speichern und schließen",
                variant="primary",
                elem_classes=["right-button"],
                elem_id="save-setting-btn",
            )
        if self._app.f_user_management:
            with gr.Tab("Benutzereinstellungen"):
                self.user_tab()

        self.app_tab()
        self.index_tab()
        self.reasoning_tab()
        self.filesync_tab()

    def _user_can_manage_advanced_settings(self, user_id) -> bool:
        if not self._app.f_user_management:
            return True
        if not user_id:
            return False

        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            return bool(actor and actor.is_admin)

    def _advanced_settings_tab_updates(self, user_id):
        can_manage_advanced_settings = self._user_can_manage_advanced_settings(user_id)
        return [
            gr.update(visible=self._render_app_tab and can_manage_advanced_settings),
            gr.update(visible=self._render_index_tab and can_manage_advanced_settings),
            gr.update(
                visible=self._render_reasoning_tab and can_manage_advanced_settings
            ),
            gr.update(visible=can_manage_advanced_settings),
        ]

    def on_subscribe_public_events(self):
        """
        Subscribes to public events related to user management.

        This function is responsible for subscribing to the "onSignIn" event, which is
        triggered when a user signs in. It registers two event handlers for this event.

        The first event handler, "load_setting", is responsible for loading the user's
        settings when they sign in. It takes the user ID as input and returns the
        settings state and a list of component outputs. The progress indicator for this
        event is set to "hidden".

        The second event handler, "get_name", is responsible for retrieving the
        username of the current user. It takes the user ID as input and returns the
        username if it exists, otherwise it returns "___". The progress indicator for
        this event is also set to "hidden".

        Parameters:
            self (object): The instance of the class.

        Returns:
            None
        """
        if self._app.f_user_management:
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self.load_setting,
                    "inputs": self._user_id,
                    "outputs": [self._settings_state] + self.components(),
                    "show_progress": "hidden",
                },
            )

            def get_name(user_id):
                name = "Aktueller Benutzer: "
                if user_id:
                    with Session(engine) as session:
                        statement = select(User).where(User.id == user_id)
                        result = session.exec(statement).all()
                        if result:
                            return name + result[0].username
                return name + "___"

            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": get_name,
                    "inputs": self._user_id,
                    "outputs": [self.current_name],
                    "show_progress": "hidden",
                },
            )

            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self._get_current_team_label,
                    "inputs": self._user_id,
                    "outputs": [self.current_team],
                    "show_progress": "hidden",
                },
            )

            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self._advanced_settings_tab_updates,
                    "inputs": self._user_id,
                    "outputs": [
                        self.general_settings_tab,
                        self.retrieval_settings_tab,
                        self.reasoning_settings_tab,
                        self.filesync_settings_tab,
                    ],
                    "show_progress": "hidden",
                },
            )
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self._populate_chat_default_choices,
                    "inputs": self._user_id,
                    "outputs": [self._components["chat_default_team"], self._components["chat_default_groups"]],
                    "show_progress": "hidden",
                },
            )

            self._app.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": self._advanced_settings_tab_updates,
                    "inputs": self._user_id,
                    "outputs": [
                        self.general_settings_tab,
                        self.retrieval_settings_tab,
                        self.reasoning_settings_tab,
                        self.filesync_settings_tab,
                    ],
                    "show_progress": "hidden",
                },
            )
            if self._filesync_service:
                self._app.subscribe_event(
                    name="onSignIn",
                    definition={
                        "fn": self._filesync_service.load_ui_state,
                        "inputs": [self._user_id],
                        "outputs": self.filesync_outputs(),
                        "show_progress": "hidden",
                    },
                )
                self._app.subscribe_event(
                    name="onSignOut",
                    definition={
                        "fn": self._filesync_service.load_ui_state,
                        "inputs": [self._user_id],
                        "outputs": self.filesync_outputs(),
                        "show_progress": "hidden",
                    },
                )

    def _get_current_username_label(self, user_id):
        name = "Aktueller Benutzer: "
        if user_id:
            with Session(engine) as session:
                statement = select(User).where(User.id == user_id)
                result = session.exec(statement).all()
                if result:
                    return name + result[0].username
        return name + "___"

    def _get_current_team_label(self, user_id):
        name = "Aktuelles Team: "
        if not user_id:
            return name + "___"

        with Session(engine) as session:
            access = get_access_context(session, user_id)
            if not access:
                return name + "___"

            assigned_team_ids = access.team_ids
            if not assigned_team_ids:
                return name + "-"

            teams = session.exec(select(Team).where(Team.id.in_(assigned_team_ids))).all()
            team_name_map = {team.id: team.name for team in teams}
            team_names = [team_name_map.get(team_id, team_id) for team_id in assigned_team_ids]
            return name + ", ".join(team_names)

    def on_register_events(self):
        if self._app.f_user_management:
            self._app.user_id.change(
                self._get_current_username_label,
                inputs=[self._user_id],
                outputs=[self.current_name],
                show_progress="hidden",
            )
            self._app.user_id.change(
                self._get_current_team_label,
                inputs=[self._user_id],
                outputs=[self.current_team],
                show_progress="hidden",
            )
            self._app.user_id.change(
                self._advanced_settings_tab_updates,
                inputs=[self._user_id],
                outputs=[
                    self.general_settings_tab,
                    self.retrieval_settings_tab,
                    self.reasoning_settings_tab,
                    self.filesync_settings_tab,
                ],
                show_progress="hidden",
            )
            self._app.user_id.change(
                self._populate_chat_default_choices,
                inputs=[self._user_id],
                outputs=[self._components["chat_default_team"], self._components["chat_default_groups"]],
                show_progress="hidden",
            )

        if True:
            save_chain = self.setting_save_btn.click(
                self.save_setting,
                inputs=[self._user_id] + self.components(),
                outputs=self._settings_state,
            )
            if hasattr(self._app, "update_graph_collection_tabs") and hasattr(
                self._app, "graph_index_tabs"
            ):
                save_chain = save_chain.then(
                    self._app.update_graph_collection_tabs,
                    inputs=[self._user_id, self._settings_state],
                    outputs=self._app.graph_index_tabs(),
                )
            save_chain = save_chain.then(
                lambda: gr.Tabs(selected="chat-tab"),
                outputs=self._app.tabs,
            )
            if hasattr(self._app, "resources_page"):
                save_chain = save_chain.then(
                    self._app.resources_page.toggle_management_tabs,
                    inputs=[self._user_id],
                    outputs=self._app.resources_page._management_tabs(),
                )
        self._components["reasoning.use"].change(
            self.change_reasoning_mode,
            inputs=[self._components["reasoning.use"]],
            outputs=list(self._reasoning_mode.values()),
            show_progress="hidden",
            )
        if self._app.f_user_management and can_manage_local_users():
            self.password_change_btn.click(
                self.change_password,
                inputs=[
                    self._user_id,
                    self.password_change,
                    self.password_change_confirm,
                ],
                outputs=[self.password_change, self.password_change_confirm],
                show_progress="hidden",
            )
            onSignOutClick = self.signout.click(
                lambda: (None, "Aktueller Benutzer: ___", "Aktuelles Team: ___", "", ""),
                inputs=[],
                outputs=[
                    self._user_id,
                    self.current_name,
                    self.current_team,
                    self.password_change,
                    self.password_change_confirm,
                ],
                show_progress="hidden",
                js=signout_js,
            ).then(
                self.load_setting,
                inputs=self._user_id,
                outputs=[self._settings_state] + self.components(),
                show_progress="hidden",
            )
            for event in self._app.get_event("onSignOut"):
                onSignOutClick = onSignOutClick.then(**event)
        elif self._app.f_user_management and is_oidc_auth():
            self.signout.click(
                fn=None,
                js=oidc_signout_js,
            )
        elif self._app.f_user_management:
            onSignOutClick = self.signout.click(
                lambda: (None, "Aktueller Benutzer: ___", "Aktuelles Team: ___", "", ""),
                inputs=[],
                outputs=[
                    self._user_id,
                    self.current_name,
                    self.current_team,
                    self.password_change,
                    self.password_change_confirm,
                ],
                show_progress="hidden",
                js=signout_js,
            ).then(
                self.load_setting,
                inputs=self._user_id,
                outputs=[self._settings_state] + self.components(),
                show_progress="hidden",
            )
            for event in self._app.get_event("onSignOut"):
                onSignOutClick = onSignOutClick.then(**event)

        if self._filesync_service:
            self.filesync_folder_selector.change(
                self._filesync_service.load_folder_team_selection,
                inputs=[
                    self.filesync_folder_selector,
                    self.filesync_folder_mapping_state,
                    self._user_id,
                ],
                outputs=[self.filesync_folder_team_ids],
                show_progress="hidden",
            )
            self.filesync_folder_team_ids.change(
                self._filesync_service.update_folder_team_mapping,
                inputs=[
                    self.filesync_folder_selector,
                    self.filesync_folder_team_ids,
                    self.filesync_folder_mapping_state,
                    self.filesync_detected_folders,
                    self._user_id,
                ],
                outputs=[
                    self.filesync_folder_mapping_state,
                    self.filesync_mapping_preview,
                ],
                show_progress="hidden",
            )
            self.filesync_test_path_btn.click(
                self._filesync_service.test_path_ui,
                inputs=[
                    self._user_id,
                    self.filesync_local_folder_path,
                    self.filesync_folder_mapping_state,
                ],
                outputs=[
                    self.filesync_detected_folders,
                    self.filesync_folder_mapping_state,
                    self.filesync_folder_selector,
                    self.filesync_folder_team_ids,
                    self.filesync_mapping_preview,
                    self.filesync_path_accessible,
                    self.filesync_last_status,
                ],
                show_progress="hidden",
            )
            self.filesync_save_btn.click(
                self._filesync_service.save_config_ui,
                inputs=[
                    self._user_id,
                    self.filesync_local_folder_path,
                    self.filesync_scan_interval,
                    self.filesync_file_type_filter,
                    self.filesync_folder_mapping_state,
                ],
                outputs=self.filesync_outputs(),
                show_progress="hidden",
            )
            self.filesync_run_now_btn.click(
                self._filesync_service.run_sync_now_ui,
                inputs=[self._user_id],
                outputs=self.filesync_outputs(),
                show_progress="hidden",
            )

    def user_tab(self):
        # user management
        self.current_name = gr.Markdown("Aktueller Benutzer: ___")
        self.current_team = gr.Markdown("Aktuelles Team: ___")
        self.signout = gr.Button("Abmelden")

        # Chat-Voreinstellungen
        gr.Markdown("### Chat-Voreinstellungen")
        self._components["chat_default_mode"] = gr.Radio(
            label="Standard-Suchmodus",
            choices=[
                ("Alle durchsuchen", "all"),
                ("Dateien durchsuchen", "select"),
                ("Dateigruppen durchsuchen", "group_select"),
            ],
            value="all",
            interactive=True,
        )
        self._components["chat_default_team"] = gr.Dropdown(
            label="Standard-Team",
            choices=[("Alle Teams", "")],
            value="",
            interactive=True,
            allow_custom_value=False,
        )
        self._components["chat_default_groups"] = gr.Dropdown(
            label="Standard-Dateigruppen",
            choices=[],
            value=[],
            multiselect=True,
            interactive=True,
        )
        for key in ["chat_default_mode", "chat_default_team", "chat_default_groups"]:
            if key not in self._settings_keys:
                self._settings_keys.append(key)

        if can_manage_local_users():
            self.password_change = gr.Textbox(
                label="Neues Passwort", interactive=True, type="password"
            )
            self.password_change_confirm = gr.Textbox(
                label="Passwort best?tigen", interactive=True, type="password"
            )
            self.password_change_btn = gr.Button("Passwort ?ndern", interactive=True)
        else:
            self.password_change = gr.Textbox(
                label="Neues Passwort", interactive=False, type="password", visible=False
            )
            self.password_change_confirm = gr.Textbox(
                label="Passwort bestätigen", interactive=False, type="password", visible=False
            )
            self.password_change_btn = gr.Button(
                "Passwort ändern", interactive=False, visible=False
            )

    def filesync_tab(self):
        with gr.Tab("FileSync", visible=False) as self.filesync_settings_tab:
            self.filesync_detected_folders = gr.State(value=[])
            self.filesync_folder_mapping_state = gr.State(value={})
            self.filesync_local_folder_path = gr.Textbox(
                label="Lokaler Ordnerpfad",
                placeholder="Absoluter Ordnerpfad auf dem Server",
            )
            self.filesync_scan_interval = gr.Number(
                label="Scan-Intervall in Minuten",
                value=5,
                precision=0,
            )
            supported_types = (
                self._filesync_service.supported_file_types()
                if self._filesync_service
                else []
            )
            self.filesync_file_type_filter = gr.Dropdown(
                label="Dateityp-Filter",
                choices=supported_types,
                value=supported_types,
                multiselect=True,
            )
            with gr.Row():
                self.filesync_save_btn = gr.Button("Konfiguration speichern")
                self.filesync_test_path_btn = gr.Button("Pfad testen")
                self.filesync_run_now_btn = gr.Button("Jetzt synchronisieren")
            with gr.Row():
                self.filesync_path_accessible = gr.Checkbox(
                    label="Pfad erreichbar",
                    value=False,
                    interactive=False,
                )
                self.filesync_processed_count = gr.Number(
                    label="Verarbeitete Dateien",
                    value=0,
                    precision=0,
                    interactive=False,
                )
            with gr.Row():
                self.filesync_last_scan = gr.Textbox(
                    label="Letzter Scan",
                    interactive=False,
                )
                self.filesync_last_success = gr.Textbox(
                    label="Letzte erfolgreiche Synchronisierung",
                    interactive=False,
                )
            self.filesync_last_status = gr.Textbox(label="Status", interactive=False)
            gr.Markdown("### Ordner zu Teams")
            self.filesync_folder_selector = gr.Dropdown(
                label="Erkannter Ordner",
                choices=[],
                value=None,
            )
            self.filesync_folder_team_ids = gr.Dropdown(
                label="Erlaubte Teams",
                choices=[],
                value=[],
                multiselect=True,
            )
            self.filesync_mapping_preview = gr.DataFrame(
                headers=["Ordner", "Teams"],
                interactive=False,
            )

    def filesync_outputs(self):
        return [
            self.filesync_local_folder_path,
            self.filesync_scan_interval,
            self.filesync_file_type_filter,
            self.filesync_folder_mapping_state,
            self.filesync_detected_folders,
            self.filesync_folder_selector,
            self.filesync_folder_team_ids,
            self.filesync_mapping_preview,
            self.filesync_path_accessible,
            self.filesync_last_scan,
            self.filesync_last_success,
            self.filesync_processed_count,
            self.filesync_last_status,
        ]

    def change_password(self, user_id, password, password_confirm):
        if not can_manage_local_users():
            gr.Warning(local_user_management_block_reason())
            return password, password_confirm
        from ktem.pages.resources.user import validate_password

        errors = validate_password(password, password_confirm)
        if errors:
            print(errors)
            gr.Warning(errors)
            return password, password_confirm

        with Session(engine) as session:
            statement = select(User).where(User.id == user_id)
            result = session.exec(statement).all()
            if result:
                user = result[0]
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                user.password = hashed_password
                session.add(user)
                session.commit()
                gr.Info("Passwort geändert")
            else:
                gr.Warning("Benutzer nicht gefunden")

        return "", ""

    def app_tab(self):
        with gr.Tab("Allgemein", visible=self._render_app_tab) as self.general_settings_tab:
            for n, si in self._default_settings.application.settings.items():
                obj = render_setting_item(si, si.value)
                self._components[f"application.{n}"] = obj
                if si.special_type == "llm":
                    self._llms.append(obj)
                if si.special_type == "embedding":
                    self._embeddings.append(obj)

    def index_tab(self):
        # TODO: double check if we need general
        # with gr.Tab("General"):
        #     for n, si in self._default_settings.index.settings.items():
        #         obj = render_setting_item(si, si.value)
        #         self._components[f"index.{n}"] = obj

        id2name = {k: v.name for k, v in self._app.index_manager.info().items()}
        with gr.Tab("Abruf-Einstellungen", visible=self._render_index_tab) as self.retrieval_settings_tab:
            for pn, sig in self._default_settings.index.options.items():
                name = id2name.get(pn, f"<id {pn}>")
                with gr.Tab(name):
                    for n, si in sig.settings.items():
                        obj = render_setting_item(si, si.value)
                        self._components[f"index.options.{pn}.{n}"] = obj
                        if si.special_type == "llm":
                            self._llms.append(obj)
                        if si.special_type == "embedding":
                            self._embeddings.append(obj)

    def reasoning_tab(self):
        with gr.Tab("Reasoning-Einstellungen", visible=self._render_reasoning_tab) as self.reasoning_settings_tab:
            with gr.Group():
                for n, si in self._default_settings.reasoning.settings.items():
                    if n == "use":
                        continue
                    obj = render_setting_item(si, si.value)
                    self._components[f"reasoning.{n}"] = obj
                    if si.special_type == "llm":
                        self._llms.append(obj)
                    if si.special_type == "embedding":
                        self._embeddings.append(obj)

            gr.Markdown("### Reasoning-spezifische Einstellungen")
            self._components["reasoning.use"] = render_setting_item(
                self._default_settings.reasoning.settings["use"],
                self._default_settings.reasoning.settings["use"].value,
            )

            for idx, (pn, sig) in enumerate(
                self._default_settings.reasoning.options.items()
            ):
                with gr.Group(
                    visible=idx == 0,
                    elem_id=pn,
                ) as self._reasoning_mode[pn]:
                    reasoning = reasonings.get(pn, None)
                    if reasoning is None:
                        gr.Markdown("**Name**: Beschreibung")
                    else:
                        info = reasoning.get_info()
                        gr.Markdown(f"**{info['name']}**: {info['description']}")
                    for n, si in sig.settings.items():
                        obj = render_setting_item(si, si.value)
                        self._components[f"reasoning.options.{pn}.{n}"] = obj
                        if si.special_type == "llm":
                            self._llms.append(obj)
                        if si.special_type == "embedding":
                            self._embeddings.append(obj)

    def change_reasoning_mode(self, value):
        output = []
        for each in self._reasoning_mode.values():
            if value == each.elem_id:
                output.append(gr.update(visible=True))
            else:
                output.append(gr.update(visible=False))
        return output

    def load_setting(self, user_id=None):
        settings = self._settings_dict
        with Session(engine) as session:
            statement = select(Settings).where(Settings.user == user_id)
            result = session.exec(statement).all()
            if result:
                settings = result[0].setting

        # Ensure chat default keys exist
        for key in ("chat_default_mode", "chat_default_team", "chat_default_groups"):
            if key not in settings:
                settings[key] = "all" if key == "chat_default_mode" else ("" if key == "chat_default_team" else [])

        output = [settings]
        output += tuple(settings.get(name, self._settings_dict.get(name)) for name in self.component_names())
        return output

    def _populate_chat_default_choices(self, user_id):
        team_choices = [("Alle Teams", "")]
        group_choices = []
        from ktem.authz import globally_visible_team_ids
        if user_id and self._app.f_user_management:
            try:
                with Session(engine) as s:
                    actor = get_access_context(s, user_id)
                    if actor:
                        teams = s.exec(select(Team)).all()
                        team_map = {t.id: t.name for t in teams}
                        if actor.is_admin:
                            for t in teams:
                                team_choices.append((t.name, t.id))
                        else:
                            gids = globally_visible_team_ids(s)
                            for tid in list(actor.team_ids) + list(gids):
                                if tid in team_map:
                                    team_choices.append((team_map[tid], tid))
                        # Fetch file groups visible to the user
                        try:
                            from ktem.index.file.ui import (
                                _display_group_name, _encode_group_selector_value,
                                _group_visible_to_actor, _team_ref_map,
                            )
                            visible_global = globally_visible_team_ids(s)
                            team_ref = _team_ref_map(s)
                            for idx in self._app.index_manager.indices:
                                FileGroup = idx._resources["FileGroup"]
                                groups = s.exec(select(FileGroup)).all()
                                for item in groups:
                                    grp = item[0]
                                    if not _group_visible_to_actor(grp, actor, visible_global, None, team_ref):
                                        continue
                                    group_files = grp.data.get("files", [])
                                    group_value = _encode_group_selector_value(grp.id, group_files)
                                    group_choices.append((_display_group_name(grp.name), group_value))
                                group_choices.sort(key=lambda x: (x[0] or "").casefold())
                                break  # only first index
                        except Exception:
                            pass
            except Exception:
                pass
        return gr.update(choices=team_choices), gr.update(choices=group_choices)

    def save_setting(self, user_id: int, *args):
        """Save the setting to disk and persist the setting to session state

        Args:
            user_id: the user id
            args: all the values from the settings
        """
        setting = {key: value for key, value in zip(self.component_names(), args)}
        if user_id is None:
            gr.Warning("Zum Speichern der Einstellungen musst du angemeldet sein")
            return setting

        with Session(engine) as session:
            statement = select(Settings).where(Settings.user == user_id)
            try:
                user_setting = session.exec(statement).one()
            except Exception:
                user_setting = Settings()
                user_setting.user = user_id
            user_setting.setting = setting
            session.add(user_setting)
            session.commit()

        gr.Info("Einstellungen gespeichert")
        return setting

    def components(self) -> list:
        """Get the setting components"""
        output = []
        for name in self._settings_keys:
            output.append(self._components[name])
        return output

    def component_names(self):
        """Get the setting components"""
        return self._settings_keys

    def _on_app_created(self):
        if self._app.f_user_management:
            self._app.app.load(
                self._get_current_username_label,
                inputs=[self._user_id],
                outputs=[self.current_name],
                show_progress="hidden",
            )
            self._app.app.load(
                self._advanced_settings_tab_updates,
                inputs=[self._user_id],
                outputs=[
                    self.general_settings_tab,
                    self.retrieval_settings_tab,
                    self.reasoning_settings_tab,
                    self.filesync_settings_tab,
                ],
                show_progress="hidden",
            )
            self._app.app.load(
                self._populate_chat_default_choices,
                inputs=[self._user_id],
                outputs=[self._components["chat_default_team"], self._components["chat_default_groups"]],
                show_progress="hidden",
            )
            if self._filesync_service:
                self._app.app.load(
                    self._filesync_service.load_ui_state,
                    inputs=[self._user_id],
                    outputs=self.filesync_outputs(),
                    show_progress="hidden",
                )
        else:
            self._app.app.load(
                self.load_setting,
                inputs=self._user_id,
                outputs=[self._settings_state] + self.components(),
                show_progress="hidden",
            )
            if self._filesync_service:
                self._app.app.load(
                    self._filesync_service.load_ui_state,
                    inputs=[self._user_id],
                    outputs=self.filesync_outputs(),
                    show_progress="hidden",
                )

        def update_llms():
            from ktem.llms.manager import llms

            if llms._default:
                llm_choices = [(f"{llms._default} (default)", "")]
            else:
                llm_choices = [("(random)", "")]
            llm_choices += [(_, _) for _ in llms.options().keys()]
            return gr.update(choices=llm_choices)

        def update_embeddings():
            from ktem.embeddings.manager import embedding_models_manager

            if embedding_models_manager._default:
                emb_choices = [(f"{embedding_models_manager._default} (default)", "")]
            else:
                emb_choices = [("(random)", "")]
            emb_choices += [(_, _) for _ in embedding_models_manager.options().keys()]
            return gr.update(choices=emb_choices)

        for llm in self._llms:
            self._app.app.load(
                update_llms,
                inputs=[],
                outputs=[llm],
                show_progress="hidden",
            )
        for emb in self._embeddings:
            self._app.app.load(
                update_embeddings,
                inputs=[],
                outputs=[emb],
                show_progress="hidden",
            )
