import gradio as gr
from ktem.app import BasePage
from ktem.embeddings.ui import EmbeddingManagement
from ktem.index.ui import IndexManagement
from ktem.llms.ui import LLMManagement
from ktem.mcp.ui import MCPManagement
from ktem.rerankings.ui import RerankingManagement

from .user import UserManagement


class ResourcesTab(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Tab("Index-Sammlungen") as self.index_management_tab:
            self.index_management = IndexManagement(self._app)

        with gr.Tab("LLMs") as self.llm_management_tab:
            self.llm_management = LLMManagement(self._app)

        with gr.Tab("Embeddings") as self.emb_management_tab:
            self.emb_management = EmbeddingManagement(self._app)

        with gr.Tab("Rerankings") as self.rerank_management_tab:
            self.rerank_management = RerankingManagement(self._app)

        with gr.Tab("MCP-Server") as self.mcp_management_tab:
            self.mcp_management = MCPManagement(self._app)

        if self._app.f_user_management:
            with gr.Tab("Benutzer", visible=True) as self.user_management_tab:
                self.user_management = UserManagement(self._app)
