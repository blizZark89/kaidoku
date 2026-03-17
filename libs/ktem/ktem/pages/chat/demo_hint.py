from textwrap import dedent

import gradio as gr
from ktem.app import BasePage


class HintPage(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Accordion(label="Hinweis", open=False):
            gr.Markdown(
                dedent(
                    """
                - Du kannst jeden Text aus der Chat-Antwort auswählen, um **passende Quellenstellen** im rechten Bereich hervorzuheben.
                - **Zitate/Belege** können sowohl im PDF-Viewer als auch im Rohtext angesehen werden.
                - Im Menü **Chat-Einstellungen** kannst du das Zitatformat anpassen und erweitertes (CoT-)Reasoning nutzen.
                - Du willst **mehr erkunden**? Im Bereich **Hilfe** erfährst du, wie du deinen eigenen privaten Space erstellst.
            """  # noqa
                )
            )
