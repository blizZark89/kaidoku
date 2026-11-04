import gradio as gr
from ktem.app import BasePage
from ktem.embeddings.ui import EmbeddingManagement
from ktem.index.ui import IndexManagement
from ktem.llms.ui import LLMManagement
from ktem.mcp.ui import MCPManagement
from ktem.rerankings.ui import RerankingManagement
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
            with gr.Tab("Benutzer") as self.user_management_tab:
                self.user_management = UserManagement(self._app)

            with gr.Tab("Teams") as self.team_management_tab:
                self.team_management = TeamManagement(self._app)

        with gr.Tab("Index-Sammlungen") as self.index_management_tab:
            self.index_management = IndexManagement(self._app)

        with gr.Tab("LLMs") as self.llm_management_tab:
            self.llm_management = LLMManagement(self._app)

        with gr.Tab("Embeddings") as self.emb_management_tab:
            self.emb_management = EmbeddingManagement(self._app)

        with gr.Tab("Rerankings", visible=show_rerank) as self.rerank_management_tab:
            self.rerank_management = RerankingManagement(self._app)

        with gr.Tab("MCP-Server", visible=show_mcp) as self.mcp_management_tab:
            self.mcp_management = MCPManagement(self._app)

    def _get_setting(self, key, default=False):
        try:
            if hasattr(self._app, "default_settings") and self._app.default_settings:
                app_settings = self._app.default_settings.flatten()
                if key in app_settings:
                    return app_settings[key]
        except Exception:
            pass
        return getattr(flowsettings, key, default)