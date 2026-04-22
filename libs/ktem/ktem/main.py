import gradio as gr
from decouple import config
from ktem.app import BaseApp
from ktem.db.models import Settings, engine
from ktem.filesync import FileSyncService
from ktem.pages.chat import ChatPage
from ktem.pages.help import HelpPage
from ktem.pages.resources import ResourcesTab
from ktem.pages.settings import SettingsPage
from ktem.pages.setup import SetupPage
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings

KH_DEMO_MODE = getattr(flowsettings, "KH_DEMO_MODE", False)
KH_SSO_ENABLED = getattr(flowsettings, "KH_SSO_ENABLED", False)
KH_ENABLE_FIRST_SETUP = getattr(flowsettings, "KH_ENABLE_FIRST_SETUP", False)
KH_APP_DATA_EXISTS = getattr(flowsettings, "KH_APP_DATA_EXISTS", True)

# override first setup setting
if config("KH_FIRST_SETUP", default=False, cast=bool):
    KH_APP_DATA_EXISTS = False


def toggle_first_setup_visibility():
    global KH_APP_DATA_EXISTS
    is_first_setup = not KH_DEMO_MODE and not KH_APP_DATA_EXISTS
    KH_APP_DATA_EXISTS = True
    return gr.update(visible=is_first_setup), gr.update(visible=not is_first_setup)


class App(BaseApp):
    """The main app of Kotaemon

    The main application contains app-level information:
        - setting state
        - user id

    App life-cycle:
        - Render
        - Declare public events
        - Subscribe public events
        - Register events
    """

    def ui(self):
        """Render the UI"""
        self._tabs = {}
        self._graph_index_tabs = []
        self.file_sync_service = FileSyncService(self)

        with gr.Tabs() as self.tabs:
            if self.f_user_management:
                from ktem.pages.login import LoginPage

                with gr.Tab(
                    "Willkommen", elem_id="login-tab", id="login-tab"
                ) as self._tabs["login-tab"]:
                    self.login_page = LoginPage(self)

            with gr.Tab(
                "Chat",
                elem_id="chat-tab",
                id="chat-tab",
                visible=not self.f_user_management,
            ) as self._tabs["chat-tab"]:
                self.chat_page = ChatPage(self)

            if len(self.index_manager.indices) == 1:
                for index in self.index_manager.indices:
                    with gr.Tab(
                        f"{index.name}",
                        elem_id="indices-tab",
                        elem_classes=[
                            "fill-main-area-height",
                            "scrollable",
                            "indices-tab",
                        ],
                        id="indices-tab",
                        visible=not self.f_user_management and not KH_DEMO_MODE,
                    ) as self._tabs[f"{index.id}-tab"]:
                        page = index.get_index_page_ui()
                        setattr(self, f"_index_{index.id}", page)
            elif len(self.index_manager.indices) > 1:
                with gr.Tab(
                    "Dateien",
                    elem_id="indices-tab",
                    elem_classes=["fill-main-area-height", "scrollable", "indices-tab"],
                    id="indices-tab",
                    visible=not self.f_user_management and not KH_DEMO_MODE,
                ) as self._tabs["indices-tab"]:
                    for index in self.index_manager.indices:
                        index_name_lower = index.name.lower()
                        graph_setting_key = None
                        if index_name_lower == "graphrag sammlung":
                            graph_setting_key = "application.show_graphrag_collection"
                        elif index_name_lower == "lightrag sammlung":
                            graph_setting_key = "application.show_lightrag_collection"
                        with gr.Tab(
                            index.name,
                            elem_id=f"{index.id}-tab",
                            visible=graph_setting_key is None,
                        ) as self._tabs[f"{index.id}-tab"]:
                            page = index.get_index_page_ui()
                            setattr(self, f"_index_{index.id}", page)
                        if graph_setting_key is not None:
                            self._graph_index_tabs.append(
                                {
                                    "tab_key": f"{index.id}-tab",
                                    "setting_key": graph_setting_key,
                                }
                            )

            if not KH_DEMO_MODE:
                if not KH_SSO_ENABLED:
                    with gr.Tab(
                        "Ressourcen",
                        elem_id="resources-tab",
                        id="resources-tab",
                        visible=not self.f_user_management,
                        elem_classes=["fill-main-area-height", "scrollable"],
                    ) as self._tabs["resources-tab"]:
                        self.resources_page = ResourcesTab(self)

                with gr.Tab(
                    "Einstellungen",
                    elem_id="settings-tab",
                    id="settings-tab",
                    visible=not self.f_user_management,
                    elem_classes=["fill-main-area-height", "scrollable"],
                ) as self._tabs["settings-tab"]:
                    self.settings_page = SettingsPage(self)

            with gr.Tab(
                "Hilfe",
                elem_id="help-tab",
                id="help-tab",
                visible=not self.f_user_management,
            ) as self._tabs["help-tab"]:
                self.help_page = HelpPage(self)

        if KH_ENABLE_FIRST_SETUP:
            with gr.Column(visible=False) as self.setup_page_wrapper:
                self.setup_page = SetupPage(self)

    def graph_index_tabs(self):
        return [self._tabs[item["tab_key"]] for item in self._graph_index_tabs]

    def update_graph_collection_tabs(self, user_id=None, settings_state=None):
        if settings_state is None:
            settings_state = self.default_settings.flatten()
            with Session(engine) as session:
                statement = select(Settings).where(Settings.user == user_id)
                result = session.exec(statement).first()
                if result:
                    settings_state = result.setting

        return [
            gr.update(visible=bool(settings_state.get(item["setting_key"], False)))
            for item in self._graph_index_tabs
        ]

    def on_subscribe_public_events(self):
        if self.f_user_management:
            from ktem.authz import get_access_context
            from ktem.db.engine import engine
            from sqlmodel import Session

            def toggle_login_visibility(user_id):
                if not user_id:
                    return list(
                        (
                            gr.update(visible=True)
                            if k == "login-tab"
                            else gr.update(visible=False)
                        )
                        for k in self._tabs.keys()
                    ) + [gr.update(selected="login-tab")]

                with Session(engine) as session:
                    actor = get_access_context(session, user_id)
                    if actor is None:
                        return list(
                            (
                                gr.update(visible=True)
                                if k == "login-tab"
                                else gr.update(visible=False)
                            )
                            for k in self._tabs.keys()
                        )

                    can_see_resources = actor.is_admin or actor.is_key_user

                tabs_update = []
                for k in self._tabs.keys():
                    if k == "login-tab":
                        tabs_update.append(gr.update(visible=False))
                    elif k == "resources-tab":
                        tabs_update.append(gr.update(visible=can_see_resources))
                    else:
                        tabs_update.append(gr.update(visible=True))

                tabs_update.append(gr.update(selected="chat-tab"))

                return tabs_update

            self.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": toggle_login_visibility,
                    "inputs": [self.user_id],
                    "outputs": list(self._tabs.values()) + [self.tabs],
                    "show_progress": "hidden",
                },
            )

            if self._graph_index_tabs:
                self.subscribe_event(
                    name="onSignIn",
                    definition={
                        "fn": self.update_graph_collection_tabs,
                        "inputs": [self.user_id],
                        "outputs": self.graph_index_tabs(),
                        "show_progress": "hidden",
                    },
                )

            self.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": toggle_login_visibility,
                    "inputs": [self.user_id],
                    "outputs": list(self._tabs.values()) + [self.tabs],
                    "show_progress": "hidden",
                },
            )

        if KH_ENABLE_FIRST_SETUP:
            self.subscribe_event(
                name="onFirstSetupComplete",
                definition={
                    "fn": toggle_first_setup_visibility,
                    "inputs": [],
                    "outputs": [self.setup_page_wrapper, self.tabs],
                    "show_progress": "hidden",
                },
            )

    def _on_app_created(self):
        """Called when the app is created"""
        self.file_sync_service.start()

        if self._graph_index_tabs:
            self.app.load(
                self.update_graph_collection_tabs,
                inputs=[self.user_id],
                outputs=self.graph_index_tabs(),
                show_progress="hidden",
            )

        if KH_ENABLE_FIRST_SETUP:
            self.app.load(
                toggle_first_setup_visibility,
                inputs=[],
                outputs=[self.setup_page_wrapper, self.tabs],
            )
