import gradio as gr
from decouple import config
from ktem.app import BaseApp
from ktem.authz import get_access_context
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

if config("KH_FIRST_SETUP", default=False, cast=bool):
    KH_APP_DATA_EXISTS = False


def toggle_first_setup_visibility():
    global KH_APP_DATA_EXISTS
    is_first_setup = not KH_DEMO_MODE and not KH_APP_DATA_EXISTS
    KH_APP_DATA_EXISTS = True
    return gr.update(visible=is_first_setup), gr.update(visible=not is_first_setup)


# Initial div only (no script). The script lives in _TAB_VIS_SCRIPT injected via <head>.
_TAB_VIS_DIV = '<div id="kaidoku-tab-vis" data-state="logged-out"></div>'

# Tab visibility JS for <head> injection. gr.HTML does NOT execute <script> tags,
# so the logic must live in the document <head> via gr.Blocks(head=...).
# Uses setInterval polling (300ms) instead of MutationObserver because Gradio
# replaces the entire gr.HTML content on update, detaching observed nodes.
_TAB_VIS_SCRIPT = """<script>
(function() {
    var KNOWN = ['Willkommen', 'Chat', 'Dateien', 'Ressourcen', 'Einstellungen', 'Hilfe'];
    var _lastState = null;
    function getBtns() { return document.querySelectorAll('.tabs > .tab-nav button[role="tab"]'); }
    function setTab(name, display) {
        getBtns().forEach(function(b) { if (b.textContent.trim() === name) b.style.display = display; });
    }
    function apply(state) {
        if (!state || state === _lastState) return;
        _lastState = state;
        if (state === 'logged-out') {
            setTab('Willkommen', '');
            KNOWN.forEach(function(t) { if (t !== 'Willkommen') setTab(t, 'none'); });
        } else {
            setTab('Willkommen', 'none');
            KNOWN.forEach(function(t) { if (t !== 'Willkommen' && t !== 'Ressourcen') setTab(t, ''); });
            var showResources = (state === 'logged-in-admin' || state === 'logged-in-keyuser');
            setTab('Ressourcen', showResources ? '' : 'none');
        }
        getBtns().forEach(function(b) {
            var t = b.textContent.trim();
            if (KNOWN.indexOf(t) === -1) b.style.display = (state === 'logged-out') ? 'none' : '';
        });
    }
    function poll() {
        var target = document.getElementById('kaidoku-tab-vis');
        if (target) apply(target.getAttribute('data-state'));
    }
    // First poll after DOM ready, then every 300ms
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { poll(); setInterval(poll, 300); });
    } else {
        poll();
        setInterval(poll, 300);
    }
})();
</script>"""

_LOGGED_OUT_HTML = '<div id="kaidoku-tab-vis" data-state="logged-out"></div>'
_LOGGED_IN_ADMIN_HTML = '<div id="kaidoku-tab-vis" data-state="logged-in-admin"></div>'
_LOGGED_IN_KEYUSER_HTML = '<div id="kaidoku-tab-vis" data-state="logged-in-keyuser"></div>'
_LOGGED_IN_USER_HTML = '<div id="kaidoku-tab-vis" data-state="logged-in-user"></div>'


class App(BaseApp):
    """The main app of Kotaemon"""

    def __init__(self):
        super().__init__()
        # Script injected into <head> so it executes reliably (gr.HTML strips <script>)
        self._extra_head_html = _TAB_VIS_SCRIPT

    def ui(self):
        """Render the UI"""
        self._tabs = {}
        self._graph_index_tabs = []
        self.file_sync_service = FileSyncService(self)

        # HTML component: initial div with data-state. Script runs from <head>.
        self._tab_visibility_js = gr.HTML(value=_TAB_VIS_DIV, visible=True)

        with gr.Tabs() as self.tabs:
            if self.f_user_management:
                from ktem.pages.login import LoginPage

                with gr.Tab("Willkommen", elem_id="login-tab", id="login-tab") as self._tabs["login-tab"]:
                    self.login_page = LoginPage(self)

            with gr.Tab("Chat", elem_id="chat-tab", id="chat-tab") as self._tabs["chat-tab"]:
                self.chat_page = ChatPage(self)

            if len(self.index_manager.indices) == 1:
                for index in self.index_manager.indices:
                    with gr.Tab(
                        f"{index.name}", elem_id="indices-tab",
                        elem_classes=["fill-main-area-height", "scrollable", "indices-tab"],
                        id="indices-tab",
                    ) as self._tabs[f"{index.id}-tab"]:
                        page = index.get_index_page_ui()
                        setattr(self, f"_index_{index.id}", page)
            elif len(self.index_manager.indices) > 1:
                with gr.Tab(
                    "Dateien", elem_id="indices-tab",
                    elem_classes=["fill-main-area-height", "scrollable", "indices-tab"],
                    id="indices-tab",
                ) as self._tabs["indices-tab"]:
                    for index in self.index_manager.indices:
                        index_name_lower = index.name.lower()
                        graph_setting_key = None
                        graph_roles_setting_key = None
                        if index_name_lower == "graphrag sammlung":
                            graph_setting_key = "application.show_graphrag_collection"
                            graph_roles_setting_key = "application.show_graphrag_collection_roles"
                        elif index_name_lower == "lightrag sammlung":
                            graph_setting_key = "application.show_lightrag_collection"
                            graph_roles_setting_key = "application.show_lightrag_collection_roles"
                        with gr.Tab(index.name, elem_id=f"{index.id}-tab", visible=graph_setting_key is None) as self._tabs[f"{index.id}-tab"]:
                            page = index.get_index_page_ui()
                            setattr(self, f"_index_{index.id}", page)
                        if graph_setting_key is not None:
                            self._graph_index_tabs.append({
                                "tab_key": f"{index.id}-tab",
                                "setting_key": graph_setting_key,
                                "roles_setting_key": graph_roles_setting_key,
                            })

            if not KH_DEMO_MODE:
                with gr.Tab("Ressourcen", elem_id="resources-tab", id="resources-tab",
                            elem_classes=["fill-main-area-height", "scrollable"]) as self._tabs["resources-tab"]:
                    self.resources_page = ResourcesTab(self)

                with gr.Tab("Einstellungen", elem_id="settings-tab", id="settings-tab",
                            elem_classes=["fill-main-area-height", "scrollable"]) as self._tabs["settings-tab"]:
                    self.settings_page = SettingsPage(self)

            with gr.Tab("Hilfe", elem_id="help-tab", id="help-tab") as self._tabs["help-tab"]:
                self.help_page = HelpPage(self)

        if KH_ENABLE_FIRST_SETUP:
            with gr.Column(visible=False) as self.setup_page_wrapper:
                self.setup_page = SetupPage(self)

    def graph_index_tabs(self):
        return []

    def update_graph_collection_tabs(self, *args, **kwargs):
        return []

    def _is_graph_tab_visible(self, *args, **kwargs):
        return False

    def _build_tab_visibility_html(self, user_id):
        """Return HTML div with data-state for the setInterval poller."""
        if not user_id:
            return _LOGGED_OUT_HTML
        if self.f_user_management:
            with Session(engine) as session:
                actor = get_access_context(session, user_id)
                if actor:
                    if actor.is_admin:
                        return _LOGGED_IN_ADMIN_HTML
                    if actor.is_key_user:
                        return _LOGGED_IN_KEYUSER_HTML
        return _LOGGED_IN_USER_HTML

    def on_subscribe_public_events(self):
        if self.f_user_management:

            self.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": lambda user_id: gr.Tabs(selected="chat-tab") if user_id else gr.update(),
                    "inputs": [self.user_id], "outputs": [self.tabs], "show_progress": "hidden",
                },
            )

            self.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": lambda: gr.Tabs(selected="login-tab"),
                    "inputs": [], "outputs": [self.tabs], "show_progress": "hidden",
                },
            )

            self.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self._build_tab_visibility_html,
                    "inputs": [self.user_id], "outputs": [self._tab_visibility_js], "show_progress": "hidden",
                },
            )

            self.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": lambda: _LOGGED_OUT_HTML,
                    "inputs": [], "outputs": [self._tab_visibility_js], "show_progress": "hidden",
                },
            )

        if KH_ENABLE_FIRST_SETUP:
            self.subscribe_event(
                name="onFirstSetupComplete",
                definition={
                    "fn": toggle_first_setup_visibility,
                    "inputs": [], "outputs": [self.setup_page_wrapper, self.tabs], "show_progress": "hidden",
                },
            )

    def _on_app_created(self):
        self.file_sync_service.start()
        if KH_ENABLE_FIRST_SETUP:
            self.app.load(toggle_first_setup_visibility, inputs=[], outputs=[self.setup_page_wrapper, self.tabs])
