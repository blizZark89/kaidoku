import gradio as gr
from ktem.authz import get_access_context
from ktem.app import BasePage
from ktem.embeddings.ui import EmbeddingManagement
from ktem.index.ui import IndexManagement
from ktem.llms.ui import LLMManagement
from ktem.mcp.ui import MCPManagement
from ktem.rerankings.ui import RerankingManagement
from ktem.speech.ui import SpeechManagement
from ktem.db.models import Settings, engine
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings
from .team import TeamManagement
from .user import UserManagement


class ResourcesTab(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        show_rerank = self._get_setting("show_rerankings_tab", False)
        show_mcp = self._get_setting("show_mcp_tab", False)

        if self._app.f_user_management:
            with gr.Tab("Benutzer", visible=True) as self.user_management_tab:
                self.user_management = UserManagement(self._app)

            with gr.Tab("Teams", visible=True) as self.team_management_tab:
                self.team_management = TeamManagement(self._app)

        with gr.Tab("Index-Sammlungen", visible=True) as self.index_management_tab:
            self.index_management = IndexManagement(self._app)

        with gr.Tab("LLMs", visible=True) as self.llm_management_tab:
            self.llm_management = LLMManagement(self._app)

        with gr.Tab("Embeddings", visible=True) as self.emb_management_tab:
            self.emb_management = EmbeddingManagement(self._app)

        with gr.Tab("Speech", visible=True) as self.speech_management_tab:
            self.speech_management = SpeechManagement(self._app)

        with gr.Tab("Rerankings", visible=show_rerank) as self.rerank_management_tab:
            self.rerank_management = RerankingManagement(self._app)

        with gr.Tab("MCP-Server", visible=show_mcp) as self.mcp_management_tab:
            self.mcp_management = MCPManagement(self._app)

    def on_subscribe_public_events(self):
        if self._app.f_user_management:
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self.toggle_management_tabs,
                    "inputs": [self._app.user_id],
                    "outputs": self._management_tabs(),
                    "show_progress": "hidden",
                },
            )

            self._app.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": self.toggle_management_tabs,
                    "inputs": [self._app.user_id],
                    "outputs": self._management_tabs(),
                    "show_progress": "hidden",
                },
            )

    def on_register_events(self):
        if self._app.f_user_management:
            self._app.user_id.change(
                self.toggle_management_tabs,
                inputs=[self._app.user_id],
                outputs=self._management_tabs(),
                show_progress="hidden",
            )

    def _management_tabs(self):
        tabs = []
        if self._app.f_user_management:
            tabs.append(self.user_management_tab)
            tabs.append(self.team_management_tab)
        tabs.extend([
            self.index_management_tab,
            self.llm_management_tab,
            self.emb_management_tab,
            self.speech_management_tab,
            self.rerank_management_tab,
            self.mcp_management_tab,
        ])
        return tabs

    def _get_setting(self, key, default=False):
        # Prüfe zuerst die im Speicher gehaltenen Default-Settings der App
        try:
            if hasattr(self._app, "default_settings") and self._app.default_settings:
                app_settings = self._app.default_settings.flatten()
                if key in app_settings:
                    return app_settings[key]
        except Exception:
            pass
        # Fallback auf flowsettings
        return getattr(flowsettings, key, default)

    def toggle_management_tabs(self, user_id):
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            is_admin = bool(actor and actor.is_admin)
            can_manage_users = bool(actor and (actor.is_admin or actor.is_key_user))

        show_rerank = self._get_setting("show_rerankings_tab", False)
        show_mcp = self._get_setting("show_mcp_tab", False)

        updates = []
        if self._app.f_user_management:
            updates.append(gr.update(visible=can_manage_users))  # Benutzer
            updates.append(gr.update(visible=is_admin))          # Teams
        updates.extend([
            gr.update(visible=is_admin),                         # Index-Sammlungen
            gr.update(visible=is_admin),                         # LLMs
            gr.update(visible=is_admin),                         # Embeddings
            gr.update(visible=is_admin),                         # Speech
            gr.update(visible=is_admin and show_rerank),         # Rerankings
            gr.update(visible=is_admin and show_mcp),            # MCP-Server
        ])
        return updates

    def _on_app_created(self):
        if self._app.f_user_management:
            self._app.app.load(
                self._sso_initial_visibility,
                inputs=[],
                outputs=self._management_tabs(),
                show_progress="hidden",
            )

    def _sso_initial_visibility(self, request: gr.Request):
        try:
            import gradiologin as grlogin
            user = grlogin.get_user(request)
            if user:
                return self.toggle_management_tabs(user["sub"])
        except Exception:
            pass
        # No active SSO session: do nothing, keep current state (local login
        # flow via onSignIn events will set visibility correctly).
        return [gr.update() for _ in self._management_tabs()]
