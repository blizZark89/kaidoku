import gradio as gr
from ktem.app import BasePage
from theflow.settings import settings as flowsettings

KH_DEMO_MODE = getattr(flowsettings, "KH_DEMO_MODE", False)

if not KH_DEMO_MODE:
    PLACEHOLDER_TEXT = (
        "Dies ist der Beginn einer neuen Unterhaltung.\n"
        "Starte mit dem Hochladen einer Datei oder einer Web-URL. "
        "Im Tab Dateien findest du weitere Optionen (z. B. GraphRAG)."
    )
else:
    PLACEHOLDER_TEXT = (
        "Willkommen zur kaidoku-Demo. "
        "Starte mit den vorgeladenen Unterhaltungen, um dich einzuarbeiten.\n"
        "Im Hinweis-Bereich findest du weitere Tipps."
    )


class ChatPanel(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        self.chatbot = gr.Chatbot(
            label=self._app.app_name,
            placeholder=PLACEHOLDER_TEXT,
            show_label=False,
            elem_id="main-chat-bot",
            show_copy_button=True,
            likeable=True,
            bubble_full_width=False,
        )
        with gr.Row():
            self.text_input = gr.MultimodalTextbox(
                interactive=True,
                scale=20,
                file_count="multiple",
                placeholder=(
                    "Nachricht eingeben, mit @web suchen oder eine Datei mit @dateiname markieren"
                ),
                container=False,
                show_label=False,
                elem_id="chat-input",
            )

    def submit_msg(self, chat_input, chat_history):
        """Submit a message to the chatbot"""
        return "", chat_history + [(chat_input, None)]
