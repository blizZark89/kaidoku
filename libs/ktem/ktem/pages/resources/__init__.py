import gradio as gr
from ktem.authz import get_access_context
from ktem.app import BasePage
from ktem.db.models import engine
from ktem.embeddings.ui import EmbeddingManagement
from ktem.index.ui import IndexManagement
from ktem.llms.ui import LLMManagement
from ktem.mcp.ui import MCPManagement
from ktem.rerankings.ui import RerankingManagement
from sqlmodel import Session

from .user import UserManagement


class ResourcesTab(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Tab("Index-Sammlungen", visible=False) as self.index_management_tab:
            self.index_management = IndexManagement(self._app)

        with gr.Tab("LLMs", visible=False) as self.llm_management_tab:
            self.llm_management = LLMManagement(self._app)

        with gr.Tab("Embeddings", visible=False) as self.emb_management_tab:
            self.emb_management = EmbeddingManagement(self._app)

        with gr.Tab("Rerankings", visible=False) as self.rerank_management_tab:
            self.rerank_management = RerankingManagement(self._app)

        with gr.Tab("MCP-Server", visible=False) as self.mcp_management_tab:
            self.mcp_management = MCPManagement(self._app)

        if self._app.f_user_management:
            with gr.Tab("Benutzer", visible=False) as self.user_management_tab:
                self.user_management = UserManagement(self._app)

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
            # Defensive update path: keep visibility in sync even if a public event
            # chain fails or is skipped.
            self._app.user_id.change(
                self.toggle_management_tabs,
                inputs=[self._app.user_id],
                outputs=self._management_tabs(),
                show_progress="hidden",
            )

    def _management_tabs(self):
        tabs = [
            self.index_management_tab,
            self.llm_management_tab,
            self.emb_management_tab,
            self.rerank_management_tab,
            self.mcp_management_tab,
        ]
        if self._app.f_user_management:
            tabs.append(self.user_management_tab)
        return tabs

    def toggle_management_tabs(self, user_id):
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            is_admin = bool(actor and actor.is_admin)
            can_manage_users = bool(actor and (actor.is_admin or actor.is_key_user))

        return [
            gr.update(visible=is_admin),
            gr.update(visible=is_admin),
            gr.update(visible=is_admin),
            gr.update(visible=is_admin),
            gr.update(visible=is_admin),
            gr.update(visible=can_manage_users),
        ]
