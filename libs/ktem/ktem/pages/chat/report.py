from typing import Optional

import gradio as gr
from ktem.app import BasePage
from ktem.db.models import IssueReport, engine
from sqlmodel import Session


class ReportIssue(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Accordion(
            label="Feedback",
            open=False,
            elem_id="report-accordion",
            visible=False,
        ):
            self.correctness = gr.Radio(
                choices=[
                    ("Die Antwort ist korrekt", "correct"),
                    ("Die Antwort ist nicht korrekt", "incorrect"),
                ],
                label="Korrektheit:",
            )
            self.issues = gr.CheckboxGroup(
                choices=[
                    ("Die Antwort ist beleidigend", "offensive"),
                    ("Die Belege sind falsch", "wrong-evidence"),
                ],
                label="Weiteres Problem:",
            )
            self.more_detail = gr.Textbox(
                placeholder=(
                    "Mehr Details (z. B. was falsch ist, was die "
                    "korrekte Antwort wäre usw.)"
                ),
                container=False,
                lines=3,
            )
            gr.Markdown(
                "Dadurch werden der aktuelle Chat und die Benutzereinstellungen "
                "zur Untersuchung übermittelt"
            )
            self.report_btn = gr.Button("Melden")

    def report(
        self,
        correctness: str,
        issues: list[str],
        more_detail: str,
        conv_id: str,
        chat_history: list,
        settings: dict,
        user_id: Optional[int],
        info_panel: str,
        chat_state: dict,
        *selecteds,
    ):
        selecteds_ = {}
        for index in self._app.index_manager.indices:
            if index.selector is not None:
                if isinstance(index.selector, int):
                    selecteds_[str(index.id)] = selecteds[index.selector]
                elif isinstance(index.selector, tuple):
                    selecteds_[str(index.id)] = [selecteds[_] for _ in index.selector]
                else:
                    print(f"Unknown selector type: {index.selector}")

        with Session(engine) as session:
            issue = IssueReport(
                issues={
                    "correctness": correctness,
                    "issues": issues,
                    "more_detail": more_detail,
                },
                chat={
                    "conv_id": conv_id,
                    "chat_history": chat_history,
                    "info_panel": info_panel,
                    "chat_state": chat_state,
                    "selecteds": selecteds_,
                },
                settings=settings,
                user=user_id,
            )
            session.add(issue)
            session.commit()
        gr.Info("Danke für dein Feedback")
