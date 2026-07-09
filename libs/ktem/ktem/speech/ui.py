"""
Speech-to-Text management UI for the Resources tab.

Provides a simple form for managing speech/transcription API configuration:
- API Key
- Provider / Base URL
- Model name
- Optional extra settings (language, etc.)
"""

import gradio as gr
import pandas as pd
import yaml
from ktem.app import BasePage

from .manager import speech_manager


class SpeechManagement(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Tab(label="Ansehen"):
            self.speech_list = gr.DataFrame(
                headers=["name", "provider", "default"],
                interactive=False,
                column_widths=[30, 40, 30],
            )

            with gr.Column(visible=False) as self._selected_panel:
                self.selected_speech_name = gr.Textbox(value="", visible=False)
                with gr.Row():
                    with gr.Column():
                        self.edit_default = gr.Checkbox(
                            label="Als Standard festlegen",
                            info=(
                                "Als Standard-Speech-Konfiguration für die "
                                "Spracheingabe im Chat verwenden."
                            ),
                        )
                        self.edit_name = gr.Textbox(
                            label="Name",
                            info="Zum Umbenennen dieser Konfiguration bearbeiten.",
                        )
                        self.edit_api_key = gr.Textbox(
                            label="API-Key",
                            info="API-Schlüssel für den Speech-to-Text-Anbieter.",
                            type="password",
                        )
                        self.edit_base_url = gr.Textbox(
                            label="Base URL (optional)",
                            info=(
                                "Basis-URL des Speech-to-Text-Endpunkts. "
                                "Leer lassen für Standard-URL des Anbieters."
                            ),
                        )
                        self.edit_model = gr.Textbox(
                            label="Modell",
                            info=(
                                "Modellname für die Transkription, "
                                "z.B. 'whisper-1'."
                            ),
                        )
                        self.edit_language = gr.Textbox(
                            label="Sprache (optional)",
                            info=(
                                "ISO-Sprachcode, z.B. 'de' für Deutsch. "
                                "Leer lassen für automatische Erkennung."
                            ),
                        )

                        with gr.Row(visible=False) as self._selected_panel_btn:
                            with gr.Column():
                                self.btn_edit_save = gr.Button(
                                    "Speichern", min_width=10, variant="primary"
                                )
                            with gr.Column():
                                self.btn_delete = gr.Button(
                                    "Löschen", min_width=10, variant="stop"
                                )
                                with gr.Row():
                                    self.btn_delete_yes = gr.Button(
                                        "Löschen bestätigen",
                                        variant="stop",
                                        visible=False,
                                        min_width=10,
                                    )
                                    self.btn_delete_no = gr.Button(
                                        "Abbrechen", visible=False, min_width=10
                                    )
                            with gr.Column():
                                self.btn_close = gr.Button("Schließen", min_width=10)

        with gr.Tab(label="Hinzufügen"):
            with gr.Row():
                with gr.Column(scale=2):
                    self.name = gr.Textbox(
                        label="Name",
                        info="Eindeutiger Name für diese Speech-Konfiguration.",
                    )
                    self.api_key = gr.Textbox(
                        label="API-Key",
                        info="API-Schlüssel für den Speech-to-Text-Anbieter.",
                        type="password",
                    )
                    self.base_url = gr.Textbox(
                        label="Base URL (optional)",
                        info=(
                            "Basis-URL des Endpunkts. "
                            "Leer lassen für OpenAI-Standard."
                        ),
                        value="",
                    )
                    self.model = gr.Textbox(
                        label="Modell",
                        info="Modellname, z.B. 'whisper-1'.",
                        value="whisper-1",
                    )
                    self.language = gr.Textbox(
                        label="Sprache (optional)",
                        info=(
                            "ISO-Sprachcode, z.B. 'de'. "
                            "Leer lassen für automatische Erkennung."
                        ),
                        value="de",
                    )
                    self.default = gr.Checkbox(
                        label="Als Standard festlegen",
                        info="Als Standard für die Spracheingabe verwenden.",
                    )
                    self.btn_new = gr.Button("Hinzufügen", variant="primary")

    def _on_app_created(self):
        self._app.app.load(
            self.list_speech,
            inputs=[],
            outputs=[self.speech_list],
        )

    def on_register_events(self):
        self.btn_new.click(
            self.create_speech,
            inputs=[
                self.name, self.api_key, self.base_url,
                self.model, self.language, self.default,
            ],
            outputs=None,
        ).success(self.list_speech, inputs=[], outputs=[self.speech_list]).success(
            lambda: ("", "", "", "whisper-1", "de", False),
            outputs=[
                self.name, self.api_key, self.base_url,
                self.model, self.language, self.default,
            ],
        )
        self.speech_list.select(
            self.select_speech,
            inputs=self.speech_list,
            outputs=[self.selected_speech_name],
            show_progress="hidden",
        )
        self.selected_speech_name.change(
            self.on_selected_speech_change,
            inputs=[self.selected_speech_name],
            outputs=[
                self._selected_panel,
                self._selected_panel_btn,
                self.btn_delete,
                self.btn_delete_yes,
                self.btn_delete_no,
                self.edit_name,
                self.edit_api_key,
                self.edit_base_url,
                self.edit_model,
                self.edit_language,
                self.edit_default,
            ],
            show_progress="hidden",
        )
        self.btn_delete.click(
            self.on_btn_delete_click,
            inputs=[],
            outputs=[self.btn_delete, self.btn_delete_yes, self.btn_delete_no],
            show_progress="hidden",
        )
        self.btn_delete_yes.click(
            self.delete_speech,
            inputs=[self.selected_speech_name],
            outputs=[self.selected_speech_name],
            show_progress="hidden",
        ).then(
            self.list_speech,
            inputs=[],
            outputs=[self.speech_list],
        )
        self.btn_delete_no.click(
            lambda: (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ),
            inputs=[],
            outputs=[self.btn_delete, self.btn_delete_yes, self.btn_delete_no],
            show_progress="hidden",
        )
        self.btn_edit_save.click(
            self.save_speech,
            inputs=[
                self.selected_speech_name,
                self.edit_name,
                self.edit_api_key,
                self.edit_base_url,
                self.edit_model,
                self.edit_language,
                self.edit_default,
            ],
            outputs=[self.selected_speech_name],
            show_progress="hidden",
        ).then(
            self.list_speech,
            inputs=[],
            outputs=[self.speech_list],
        )
        self.btn_close.click(
            lambda: "",
            outputs=[self.selected_speech_name],
        )

    def create_speech(
        self, name, api_key, base_url, model, language, default
    ):
        try:
            name = name.strip()
            if not name:
                raise ValueError("Name must not be empty")
            if not api_key:
                raise ValueError("API-Key must not be empty")

            spec = {
                "api_key": api_key,
                "model": model or "whisper-1",
            }
            if base_url:
                spec["base_url"] = base_url
            if language:
                spec["language"] = language

            speech_manager.add(name, spec=spec, default=default)
            gr.Info(f'Speech-Konfiguration "{name}" erstellt.')
        except ValueError as e:
            raise gr.Error(str(e))
        except Exception as e:
            raise gr.Error(
                f"Fehler beim Erstellen der Speech-Konfiguration '{name}': {e}"
            )

    def list_speech(self):
        items = []
        for item in speech_manager.info().values():
            spec = item.get("spec", {})
            provider = "OpenAI"
            if spec.get("base_url"):
                provider = spec["base_url"]
            record = {
                "name": item["name"],
                "provider": provider,
                "default": item["default"],
            }
            items.append(record)

        if items:
            return pd.DataFrame.from_records(items)
        return pd.DataFrame.from_records(
            [{"name": "-", "provider": "-", "default": "-"}]
        )

    def select_speech(self, speech_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Keine Speech-Konfiguration vorhanden.")
            return ""
        if not ev.selected:
            return ""
        return speech_list["name"][ev.index[0]]

    def on_selected_speech_change(self, selected_speech_name):
        if selected_speech_name == "":
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value="whisper-1"),
                gr.update(value="de"),
                gr.update(value=False),
            )

        info = speech_manager.info().get(selected_speech_name)
        if not info:
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value="whisper-1"),
                gr.update(value="de"),
                gr.update(value=False),
            )

        spec = info.get("spec", {})
        return (
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=selected_speech_name),
            gr.update(value=spec.get("api_key", "")),
            gr.update(value=spec.get("base_url", "")),
            gr.update(value=spec.get("model", "whisper-1")),
            gr.update(value=spec.get("language", "de")),
            gr.update(value=info.get("default", False)),
        )

    def on_btn_delete_click(self):
        return (
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=True),
        )

    def delete_speech(self, selected_speech_name):
        try:
            speech_manager.delete(selected_speech_name)
        except Exception as e:
            gr.Error(
                f"Fehler beim Löschen der Speech-Konfiguration "
                f"'{selected_speech_name}': {e}"
            )
            return selected_speech_name
        return ""

    def save_speech(
        self, selected_speech_name, edit_name, api_key, base_url,
        model, language, default,
    ):
        try:
            new_name = edit_name.strip()
            spec = {"api_key": api_key, "model": model or "whisper-1"}
            if base_url:
                spec["base_url"] = base_url
            if language:
                spec["language"] = language

            speech_manager.update(
                selected_speech_name,
                spec=spec,
                default=default,
                new_name=new_name,
            )
            final_name = (
                new_name if new_name != selected_speech_name
                else selected_speech_name
            )
            gr.Info(f'Speech-Konfiguration "{final_name}" gespeichert.')
            return final_name
        except ValueError as e:
            raise gr.Error(str(e))
        except Exception as e:
            raise gr.Error(
                f"Fehler beim Speichern der Speech-Konfiguration "
                f"'{selected_speech_name}': {e}"
            )