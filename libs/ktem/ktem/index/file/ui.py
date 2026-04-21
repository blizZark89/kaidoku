import html
import json
import os
import shutil
import tempfile
import traceback
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Generator

import gradio as gr
import pandas as pd
from gradio.data_classes import FileData
from gradio.utils import NamedString
from ktem.authz import (
    allowed_user_ids_for_scope,
    get_access_context,
    globally_visible_team_ids,
    has_read_access,
    has_upload_access,
    list_teams,
    parse_team_ids,
)
from ktem.app import BasePage
from ktem.db.engine import engine
from ktem.utils.render import Render
from sqlalchemy import select
from sqlalchemy.orm import Session
from theflow.settings import settings as flowsettings

from ...utils.commands import WEB_SEARCH_COMMAND
from ...utils.rate_limit import check_rate_limit
from .utils import download_arxiv_pdf, is_arxiv_url

KH_DEMO_MODE = getattr(flowsettings, "KH_DEMO_MODE", False)
KH_SSO_ENABLED = getattr(flowsettings, "KH_SSO_ENABLED", False)
DOWNLOAD_MESSAGE = "Download starten"
MAX_FILENAME_LENGTH = 20
MAX_FILE_COUNT = 200

chat_input_focus_js = """
function() {
    let chatInput = document.querySelector("#chat-input textarea");
    chatInput.focus();
}
"""

chat_input_focus_js_with_submit = """
function() {
    let chatInput = document.querySelector("#chat-input textarea");
    let chatInputSubmit = document.querySelector("#chat-input button.submit-button");
    chatInputSubmit.click();
    chatInput.focus();
}
"""

update_file_list_js = """
function(file_list) {
    var values = [];
    for (var i = 0; i < file_list.length; i++) {
        values.push({
            key: file_list[i][0],
            value: '"' + file_list[i][0] + '"',
        });
    }

    // manually push web search tag
    values.push({
        key: "web_search",
        value: '"web_search"',
    });

    var tribute = new Tribute({
        values: values,
        noMatchTemplate: "",
        allowSpaces: true,
    })
    input_box = document.querySelector('#chat-input textarea');
    tribute.detach(input_box);
    tribute.attach(input_box);
}
""".replace(
    "web_search", WEB_SEARCH_COMMAND
)


def _normalize_source_team_ids(raw_value) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return parse_team_ids(raw_value)
    if isinstance(raw_value, (list, tuple, set)):
        team_ids: list[str] = []
        for team_id in raw_value:
            value = str(team_id).strip()
            if value and value not in team_ids:
                team_ids.append(value)
        return team_ids
    return []


def _source_team_ids(source) -> list[str]:
    note = getattr(source, "note", None) or {}
    return _normalize_source_team_ids(note.get("team_ids"))


def _group_team_ids(group) -> list[str]:
    data = getattr(group, "data", None) or {}
    return _normalize_source_team_ids(data.get("team_ids"))


def _source_visible_to_actor(source, actor, global_team_ids=None, scope_user_ids=None) -> bool:
    if actor is None:
        return True
    if actor.is_admin:
        return True
    source_team_ids = set(_source_team_ids(source))
    global_team_ids = set(global_team_ids or [])
    if source_team_ids and source_team_ids.intersection(global_team_ids):
        return True
    if not source_team_ids:
        # Legacy behavior (without document team mapping):
        # only visible within uploader scope.
        if scope_user_ids is None:
            return False
        return getattr(source, "user", None) in set(scope_user_ids)
    actor_team_ids = set(actor.team_ids)
    return bool(actor_team_ids.intersection(source_team_ids))


def _group_visible_to_actor(group, actor, global_team_ids=None, scope_user_ids=None) -> bool:
    if actor is None:
        return True
    if actor.is_admin:
        return True
    group_team_ids = set(_group_team_ids(group))
    global_team_ids = set(global_team_ids or [])
    if group_team_ids and group_team_ids.intersection(global_team_ids):
        return True
    if not group_team_ids:
        if scope_user_ids is None:
            return False
        return getattr(group, "user", None) in set(scope_user_ids)
    actor_team_ids = set(actor.team_ids)
    return bool(actor_team_ids.intersection(group_team_ids))


class File(gr.File):
    """Subclass from gr.File to maintain the original filename

    The issue happens when user uploads file with name like: !@#$%%^&*().pdf
    """

    def _process_single_file(self, f: FileData) -> NamedString | bytes:
        file_name = f.path
        if self.type == "filepath":
            if f.orig_name and Path(file_name).name != f.orig_name:
                file_name = str(Path(file_name).parent / f.orig_name)
                os.rename(f.path, file_name)
            file = tempfile.NamedTemporaryFile(delete=False, dir=self.GRADIO_CACHE)
            file.name = file_name
            return NamedString(file_name)
        elif self.type == "binary":
            with open(file_name, "rb") as file_data:
                return file_data.read()
        else:
            raise ValueError(
                "Unknown type: "
                + str(type)
                + ". Please choose from: 'filepath', 'binary'."
            )


class DirectoryUpload(BasePage):
    def __init__(self, app, index):
        super().__init__(app)
        self._index = index
        self._supported_file_types_str = self._index.config.get(
            "supported_file_types", ""
        )
        self._supported_file_types = [
            each.strip() for each in self._supported_file_types_str.split(",")
        ]
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Accordion(label="Ordner-Upload", open=False):
            gr.Markdown(f"Unterstützte Dateitypen: {self._supported_file_types_str}")
            self.path = gr.Textbox(
                placeholder="Ordnerpfad...", lines=1, max_lines=1, container=False
            )
            with gr.Accordion("Erweiterte Indexierungsoptionen", open=False):
                with gr.Row():
                    self.reindex = gr.Checkbox(
                        value=False, label="Datei neu indexieren erzwingen", container=False
                    )

            self.upload_button = gr.Button("Hochladen und indexieren")


class FileIndexPage(BasePage):
    def __init__(self, app, index):
        super().__init__(app)
        self._index = index
        self._supported_file_types_str = self._index.config.get(
            "supported_file_types", ""
        )
        self._supported_file_types = [
            each.strip() for each in self._supported_file_types_str.split(",")
        ]
        self.selected_panel_false = "Ausgewählte Datei: (bitte oben auswählen)"
        self.selected_panel_true = "Ausgewählte Datei: {name}"
        # TODO: on_building_ui is not correctly named if it's always called in
        # the constructor
        self.public_events = [f"onFileIndex{index.id}Changed"]

        if not KH_DEMO_MODE:
            self.on_building_ui()

    def upload_instruction(self) -> str:
        msgs = []
        if self._supported_file_types:
            msgs.append(f"- Supported file types: {self._supported_file_types_str}")

        if max_file_size := self._index.config.get("max_file_size", 0):
            msgs.append(f"- Maximum file size: {max_file_size} MB")

        if max_number_of_files := self._index.config.get("max_number_of_files", 0):
            msgs.append(f"- The index can have maximum {max_number_of_files} files")

        if msgs:
            return "\n".join(msgs)

        return ""

    def _scope_user_ids(self, session: Session, user_id):
        if not self._app.f_user_management:
            return None
        actor = get_access_context(session, user_id)
        if not actor or not has_read_access(actor):
            return []
        return allowed_user_ids_for_scope(session, actor)

    def _check_upload_permission(self, user_id) -> bool:
        if not self._app.f_user_management:
            return True
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor:
                gr.Warning("Nicht angemeldet")
                return False
            if not has_upload_access(actor):
                gr.Warning("Keine Upload-Berechtigung")
                return False
            return True

    def _resolve_document_team_assignment(
        self,
        session: Session,
        user_id,
        selected_team_ids,
        apply_default_if_empty: bool = True,
    ):
        if not self._app.f_user_management:
            return [], None

        actor = get_access_context(session, user_id)
        if not actor:
            return [], "Nicht angemeldet"
        if not has_upload_access(actor):
            return [], "Keine Upload-Berechtigung"

        selected_team_ids = selected_team_ids or []
        selected_team_ids = [str(team_id).strip() for team_id in selected_team_ids if str(team_id).strip()]
        selected_team_ids = list(dict.fromkeys(selected_team_ids))

        all_teams = list_teams(session)
        existing_team_ids = {team.id for team in all_teams}

        if actor.is_admin:
            allowed_team_ids = existing_team_ids
            default_team_ids = selected_team_ids
        else:
            allowed_team_ids = set(actor.team_ids)
            # During upload we default to the actor's teams, but when editing an
            # existing document an empty selection must remain empty so teams can
            # actually be removed.
            default_team_ids = (
                selected_team_ids or list(actor.team_ids)
                if apply_default_if_empty
                else selected_team_ids
            )

        invalid_team_ids = [team_id for team_id in default_team_ids if team_id not in allowed_team_ids]
        if invalid_team_ids:
            return [], "Keine Berechtigung für ausgewählte Teams"
        if any(team_id not in existing_team_ids for team_id in default_team_ids):
            return [], "Mindestens ein ausgewähltes Team existiert nicht"

        return default_team_ids, None

    def _apply_document_teams(self, file_ids, user_id, selected_team_ids):
        if not self._app.f_user_management:
            return
        file_ids = [file_id for file_id in (file_ids or []) if file_id]
        if not file_ids:
            return

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            resolved_team_ids, error = self._resolve_document_team_assignment(
                session, user_id, selected_team_ids, apply_default_if_empty=False
            )
            if error:
                gr.Warning(error)
                return

            for file_id in file_ids:
                source = session.query(Source).filter_by(id=file_id).first()
                if not source:
                    continue
                source_note = dict(source.note or {})
                source_note["team_ids"] = resolved_team_ids
                source.note = source_note
                session.add(source)
            session.commit()

    def list_document_team_choices(self, user_id):
        if not self._app.f_user_management or user_id is None:
            return gr.update(choices=[], value=[], visible=False)

        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor or not has_upload_access(actor):
                return gr.update(choices=[], value=[], visible=False)

            teams = list_teams(session)
            team_map = {team.id: team.name for team in teams}
            if actor.is_admin:
                choices = [(team.name, team.id) for team in teams]
                values = []
            else:
                choices = [
                    (team_map.get(team_id, team_id), team_id)
                    for team_id in actor.team_ids
                    if team_id in team_map
                ]
                values = []

        return gr.update(choices=choices, value=values, visible=True)

    def selected_file_team_choices(self, file_id, user_id):
        if not self._app.f_user_management or user_id is None or not file_id:
            return (
                gr.update(choices=[], value=[], visible=False),
                gr.update(visible=False),
            )

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor or not has_upload_access(actor):
                return (
                    gr.update(choices=[], value=[], visible=False),
                    gr.update(visible=False),
                )

            source = session.query(Source).filter_by(id=file_id).first()
            if not source:
                return (
                    gr.update(choices=[], value=[], visible=False),
                    gr.update(visible=False),
                )

            scope_ids = self._scope_user_ids(session, user_id)
            if not _source_visible_to_actor(source, actor, globally_visible_team_ids(session), scope_ids):
                return (
                    gr.update(choices=[], value=[], visible=False),
                    gr.update(visible=False),
                )

            teams = list_teams(session)
            team_map = {team.id: team.name for team in teams}
            if actor.is_admin:
                choices = [(team.name, team.id) for team in teams]
            else:
                choices = [
                    (team_map.get(team_id, team_id), team_id)
                    for team_id in actor.team_ids
                    if team_id in team_map
                ]
            selected = [
                team_id for team_id in _source_team_ids(source) if any(team_id == tid for _, tid in choices)
            ]
            return (
                gr.update(choices=choices, value=selected, visible=True),
                gr.update(visible=True),
            )

    def save_selected_file_teams(self, file_id, user_id, selected_team_ids):
        if not file_id:
            gr.Warning("Keine Datei ausgewählt")
            return gr.update()

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor or not has_upload_access(actor):
                gr.Warning("Keine Upload-Berechtigung")
                return gr.update()
            source = session.query(Source).filter_by(id=file_id).first()
            if not source:
                gr.Warning("Datei nicht gefunden")
                return gr.update()

            scope_ids = self._scope_user_ids(session, user_id)
            if not _source_visible_to_actor(source, actor, globally_visible_team_ids(session), scope_ids):
                gr.Warning("Keine Berechtigung für diese Datei")
                return gr.update()

            resolved_team_ids, error = self._resolve_document_team_assignment(
                session, user_id, selected_team_ids, apply_default_if_empty=False
            )
            if error:
                gr.Warning(error)
                return gr.update()

            source_note = dict(source.note or {})
            source_note["team_ids"] = resolved_team_ids
            source.note = source_note
            session.add(source)
            session.commit()

        gr.Info("Dokument-Teams gespeichert")
        return gr.update(value=resolved_team_ids)

    def _resolve_group_team_assignment(self, session: Session, user_id, selected_team_ids):
        if not self._app.f_user_management:
            return [], None

        actor = get_access_context(session, user_id)
        if not actor:
            return [], "Nicht angemeldet"
        if not has_read_access(actor):
            return [], "Keine Leseberechtigung"

        selected_team_ids = [
            str(team_id).strip()
            for team_id in (selected_team_ids or [])
            if str(team_id).strip()
        ]
        selected_team_ids = list(dict.fromkeys(selected_team_ids))

        teams = list_teams(session)
        team_map = {team.id: team for team in teams}
        existing_team_ids = set(team_map)

        if actor.is_admin:
            allowed_team_ids = existing_team_ids
            default_team_ids = selected_team_ids
        else:
            allowed_team_ids = set(actor.team_ids)
            default_team_ids = selected_team_ids or list(actor.team_ids)

        if any(team_id not in existing_team_ids for team_id in default_team_ids):
            return [], "Mindestens ein ausgewähltes Team existiert nicht"
        if any(team_id not in allowed_team_ids for team_id in default_team_ids):
            return [], "Keine Berechtigung für ausgewählte Teams"

        return default_team_ids, None

    def _visible_source_ids_for_actor(self, session: Session, user_id):
        Source = self._index._resources["Source"]
        scope_ids = self._scope_user_ids(session, user_id)
        actor = None
        visible_source_ids = set()

        if self._app.f_user_management:
            actor = get_access_context(session, user_id)
            if not actor or not has_read_access(actor):
                return visible_source_ids, actor, scope_ids

        statement = select(Source)
        if self._index.config.get("private", False) and scope_ids is None:
            statement = statement.where(Source.user == user_id)

        global_team_ids = globally_visible_team_ids(session) if actor else set()
        for row in session.execute(statement).all():
            source = row[0]
            if actor and not _source_visible_to_actor(
                source, actor, global_team_ids, scope_ids
            ):
                continue
            visible_source_ids.add(source.id)

        return visible_source_ids, actor, scope_ids

    def list_group_team_choices(self, user_id, selected_team_ids=None):
        if not self._app.f_user_management or user_id is None:
            return gr.update(choices=[], value=[], visible=False)

        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor or not has_read_access(actor):
                return gr.update(choices=[], value=[], visible=False)

            teams = list_teams(session)
            team_map = {team.id: team.name for team in teams}
            if actor.is_admin:
                choices = [(team.name, team.id) for team in teams]
                selected = [
                    team_id for team_id in (selected_team_ids or []) if team_id in team_map
                ]
            else:
                choices = [
                    (team_map.get(team_id, team_id), team_id)
                    for team_id in actor.team_ids
                    if team_id in team_map
                ]
                allowed_ids = {team_id for _, team_id in choices}
                selected = [
                    team_id
                    for team_id in (selected_team_ids or list(actor.team_ids))
                    if team_id in allowed_ids
                ]

        return gr.update(choices=choices, value=selected, visible=True)

    def prepare_new_group(self, user_id):
        return [
            gr.update(visible=False),
            gr.update(value="### Add new group"),
            gr.update(visible=True),
            gr.update(value=""),
            gr.update(value=[]),
            self.list_group_team_choices(user_id),
            None,
        ]

    def render_file_list(self):
        self.filter = gr.Textbox(
            value="",
            label="Nach Namen filtern:",
            info=(
                "(1) Groß-/Kleinschreibung wird ignoriert. "
                "(2) Mit leerer Suche werden alle Dateien angezeigt."
            ),
        )
        self.file_list_state = gr.State(value=None)
        self.file_list = gr.DataFrame(
            headers=[
                "id",
                "name",
                "group",
                "size",
                "tokens",
                "loader",
                "date_created",
            ],
            column_widths=[0, 34, 16, 8, 7, 15, 20],
            interactive=False,
            wrap=False,
            elem_id="file_list_view",
        )

        with gr.Row():

            self.chat_button = gr.Button(
                "Zum Chat",
                visible=False,
            )
            self.is_zipped_state = gr.State(value=False)
            self.download_single_button = gr.DownloadButton(
                "Herunterladen",
                visible=False,
            )
            self.delete_button = gr.Button(
                "Löschen",
                variant="stop",
                visible=False,
            )
            self.deselect_button = gr.Button(
                "Schließen",
                visible=False,
            )

        with gr.Row() as self.selection_info:
            self.selected_file_id = gr.State(value=None)
            with gr.Column(scale=2):
                self.selected_panel = gr.Markdown(self.selected_panel_false)
                if self._app.f_user_management:
                    self.file_team_ids = gr.Dropdown(
                        label="Dokument-Teams",
                        choices=[],
                        value=[],
                        multiselect=True,
                        container=False,
                        interactive=True,
                        visible=False,
                    )
                    self.file_team_save_button = gr.Button(
                        "Teams speichern",
                        variant="primary",
                        visible=False,
                    )
                else:
                    self.file_team_ids = gr.State(value=[])
                    self.file_team_save_button = gr.State(value=None)

        self.chunks = gr.HTML(visible=False)

        with gr.Accordion("Erweiterte Optionen", open=False):
            with gr.Row():
                if not KH_SSO_ENABLED:
                    self.download_all_button = gr.DownloadButton(
                        "Alle Dateien herunterladen",
                    )
                self.delete_all_button = gr.Button(
                    "Alle Dateien löschen",
                    variant="stop",
                    visible=True,
                )
                self.delete_all_button_confirm = gr.Button(
                    "Löschen bestätigen", variant="stop", visible=False
                )
                self.delete_all_button_cancel = gr.Button("Abbrechen", visible=False)

    def render_group_list(self):
        self.group_list_state = gr.State(value=None)
        self.group_list = gr.DataFrame(
            headers=[
                "id",
                "name",
                "teams",
                "files",
                "date_created",
            ],
            column_widths=[0, 22, 18, 40, 20],
            interactive=False,
            wrap=False,
        )

        with gr.Row():
            self.group_add_button = gr.Button(
                "Hinzufügen",
                variant="primary",
            )
            self.group_chat_button = gr.Button(
                "Zum Chat",
                visible=False,
            )
            self.group_delete_button = gr.Button(
                "Löschen",
                variant="stop",
                visible=False,
            )
            self.group_close_button = gr.Button(
                "Schließen",
                visible=False,
            )

        with gr.Column(visible=False) as self._group_info_panel:
            self.selected_group_id = gr.State(value=None)
            self.group_label = gr.Markdown()
            self.group_name = gr.Textbox(
                label="Gruppenname",
                placeholder="Gruppenname",
                lines=1,
                max_lines=1,
            )
            self.group_files = gr.Dropdown(
                label="Zugeordnete Dateien",
                multiselect=True,
            )
            if self._app.f_user_management:
                self.group_team_ids = gr.Dropdown(
                    label="Gruppen-Teams",
                    choices=[],
                    value=[],
                    multiselect=True,
                    container=False,
                    interactive=True,
                    visible=False,
                )
            else:
                self.group_team_ids = gr.State(value=[])
            self.group_save_button = gr.Button(
                "Speichern",
                variant="primary",
            )

    def on_building_ui(self):
        """Build the UI of the app"""
        with gr.Row():
            with gr.Column(scale=1):
                with gr.Column() as self.upload:
                    with gr.Tab("Dateien hochladen"):
                        self.files = File(
                            file_types=self._supported_file_types,
                            file_count="multiple",
                            container=True,
                            show_label=False,
                        )

                        msg = self.upload_instruction()
                        if msg:
                            gr.Markdown(msg)

                    with gr.Tab("Web-Links verwenden"):
                        self.urls = gr.Textbox(
                            label="Web-URLs eingeben",
                            lines=8,
                        )
                        gr.Markdown("(durch Zeilenumbruch getrennt)")

                    with gr.Accordion("Erweiterte Indexierungsoptionen", open=False):
                        with gr.Row():
                            self.reindex = gr.Checkbox(
                                value=False, label="Datei neu indexieren erzwingen", container=False
                            )
                        if self._app.f_user_management:
                            self.document_team_ids = gr.Dropdown(
                                label="Dokument-Teams",
                                choices=[],
                                value=[],
                                multiselect=True,
                                container=False,
                                interactive=True,
                                info="Nur ausgewählte Teams sehen diese Dokumente.",
                            )
                        else:
                            self.document_team_ids = gr.State(value=[])

                    self.upload_button = gr.Button(
                        "Hochladen und indexieren", variant="primary"
                    )

            with gr.Column(scale=4):
                with gr.Column(visible=False) as self.upload_progress_panel:
                    gr.Markdown("## Upload-Fortschritt")
                    with gr.Row():
                        self.upload_result = gr.Textbox(
                            lines=1, max_lines=20, label="Upload-Ergebnis"
                        )
                        self.upload_info = gr.Textbox(
                            lines=1, max_lines=20, label="Upload-Info"
                        )
                    self.btn_close_upload_progress_panel = gr.Button(
                        "Upload-Info leeren und schließen",
                        variant="secondary",
                        elem_classes=["right-button"],
                    )

                with gr.Tab("Dateien"):
                    self.render_file_list()

                with gr.Tab("Gruppen"):
                    self.render_group_list()

    def on_subscribe_public_events(self):
        """Subscribe to the declared public event of the app"""
        if KH_DEMO_MODE:
            return

        self._app.subscribe_event(
            name=f"onFileIndex{self._index.id}Changed",
            definition={
                "fn": self.list_file_names,
                "inputs": [self.file_list_state],
                "outputs": [self.group_files],
                "show_progress": "hidden",
            },
        )

        if self._app.f_user_management:
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self.list_file,
                    "inputs": [self._app.user_id],
                    "outputs": [self.file_list_state, self.file_list],
                    "show_progress": "hidden",
                },
            )
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self.list_group,
                    "inputs": [self._app.user_id, self.file_list_state],
                    "outputs": [self.group_list_state, self.group_list],
                    "show_progress": "hidden",
                },
            )
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self.list_file_names,
                    "inputs": [self.file_list_state],
                    "outputs": [self.group_files],
                    "show_progress": "hidden",
                },
            )
            self._app.subscribe_event(
                name="onSignIn",
                definition={
                    "fn": self.list_document_team_choices,
                    "inputs": [self._app.user_id],
                    "outputs": [self.document_team_ids],
                    "show_progress": "hidden",
                },
            )
            self._app.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": self.list_file,
                    "inputs": [self._app.user_id],
                    "outputs": [self.file_list_state, self.file_list],
                    "show_progress": "hidden",
                },
            )
            self._app.subscribe_event(
                name="onSignOut",
                definition={
                    "fn": self.list_document_team_choices,
                    "inputs": [self._app.user_id],
                    "outputs": [self.document_team_ids],
                    "show_progress": "hidden",
                },
            )

    def file_selected(self, file_id):
        chunks = []
        if file_id is not None:
            # get the chunks

            Index = self._index._resources["Index"]
            with Session(engine) as session:
                matches = session.execute(
                    select(Index).where(
                        Index.source_id == file_id,
                        Index.relation_type == "document",
                    )
                )
                doc_ids = [doc.target_id for (doc,) in matches]
                docs = self._index._docstore.get(doc_ids)
                docs = sorted(
                    docs, key=lambda x: x.metadata.get("page_label", float("inf"))
                )

                for idx, doc in enumerate(docs):
                    title = html.escape(
                        f"{doc.text[:50]}..." if len(doc.text) > 50 else doc.text
                    )
                    doc_type = doc.metadata.get("type", "text")
                    content = ""
                    if doc_type == "text":
                        content = html.escape(doc.text)
                    elif doc_type == "table":
                        content = Render.table(doc.text)
                    elif doc_type == "image":
                        content = Render.image(
                            url=doc.metadata.get("image_origin", ""), text=doc.text
                        )

                    header_prefix = f"[{idx+1}/{len(docs)}]"
                    if doc.metadata.get("page_label"):
                        header_prefix += f" [Page {doc.metadata['page_label']}]"

                    chunks.append(
                        Render.collapsible(
                            header=f"{header_prefix} {title}",
                            content=content,
                        )
                    )
        return (
            gr.update(value="".join(chunks), visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
        )

    def delete_event(self, file_id, user_id):
        file_name = ""
        with Session(engine) as session:
            actor = get_access_context(session, user_id) if self._app.f_user_management else None
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
            if source:
                scope_ids = self._scope_user_ids(session, user_id)
                if scope_ids is not None and source[0].user not in scope_ids:
                    gr.Warning("Keine Berechtigung für diese Datei")
                    return None, self.selected_panel_false
                if self._app.f_user_management and not _source_visible_to_actor(source[0], actor, globally_visible_team_ids(session), scope_ids):
                    gr.Warning("Keine Berechtigung fÃ¼r diese Datei")
                    return None, self.selected_panel_false
                file_name = source[0].name
                session.delete(source[0])

            vs_ids, ds_ids = [], []
            index = session.execute(
                select(self._index._resources["Index"]).where(
                    self._index._resources["Index"].source_id == file_id
                )
            ).all()
            for each in index:
                if each[0].relation_type == "vector":
                    vs_ids.append(each[0].target_id)
                elif each[0].relation_type == "document":
                    ds_ids.append(each[0].target_id)
                session.delete(each[0])
            session.commit()

        if vs_ids:
            self._index._vs.delete(vs_ids)
        self._index._docstore.delete(ds_ids)

        gr.Info(f"File {file_name} has been deleted")

        return None, self.selected_panel_false

    def delete_no_event(self):
        return (
            gr.update(visible=True),
            gr.update(visible=False),
        )

    def download_single_file(self, is_zipped_state, file_id, user_id):
        with Session(engine) as session:
            actor = get_access_context(session, user_id) if self._app.f_user_management else None
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
            if source:
                scope_ids = self._scope_user_ids(session, user_id)
                if scope_ids is not None and source[0].user not in scope_ids:
                    gr.Warning("Keine Berechtigung fÃ¼r diese Datei")
                    return is_zipped_state, gr.DownloadButton(
                        label="Download", value=None
                    )
                if self._app.f_user_management and not _source_visible_to_actor(source[0], actor, globally_visible_team_ids(session), scope_ids):
                    gr.Warning("Keine Berechtigung fÃ¼r diese Datei")
                    return is_zipped_state, gr.DownloadButton(
                        label="Download", value=None
                    )
        if source:
            target_file_name = Path(source[0].name)
        zip_files = []
        for file_name in os.listdir(flowsettings.KH_CHUNKS_OUTPUT_DIR):
            if target_file_name.stem in file_name:
                zip_files.append(
                    os.path.join(flowsettings.KH_CHUNKS_OUTPUT_DIR, file_name)
                )
        for file_name in os.listdir(flowsettings.KH_MARKDOWN_OUTPUT_DIR):
            if target_file_name.stem in file_name:
                zip_files.append(
                    os.path.join(flowsettings.KH_MARKDOWN_OUTPUT_DIR, file_name)
                )
        zip_file_path = os.path.join(
            flowsettings.KH_ZIP_OUTPUT_DIR, target_file_name.stem
        )
        with zipfile.ZipFile(f"{zip_file_path}.zip", "w") as zipMe:
            for file in zip_files:
                zipMe.write(file, arcname=os.path.basename(file))

        if is_zipped_state:
            new_button = gr.DownloadButton(label="Download", value=None)
        else:
            new_button = gr.DownloadButton(
                label=DOWNLOAD_MESSAGE, value=f"{zip_file_path}.zip"
            )

        return not is_zipped_state, new_button

    def download_single_file_simple(self, is_zipped_state, file_html, file_id, user_id):
        with Session(engine) as session:
            actor = get_access_context(session, user_id) if self._app.f_user_management else None
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
            if source:
                scope_ids = self._scope_user_ids(session, user_id)
                if scope_ids is not None and source[0].user not in scope_ids:
                    gr.Warning("Keine Berechtigung fÃ¼r diese Datei")
                    return is_zipped_state, gr.DownloadButton(
                        label="Download", value=None
                    )
                if self._app.f_user_management and not _source_visible_to_actor(source[0], actor, globally_visible_team_ids(session), scope_ids):
                    gr.Warning("Keine Berechtigung fÃ¼r diese Datei")
                    return is_zipped_state, gr.DownloadButton(
                        label="Download", value=None
                    )
        if source:
            target_file_name = Path(source[0].name)

        # create a temporary file with a path to export
        output_file_path = os.path.join(
            flowsettings.KH_ZIP_OUTPUT_DIR, target_file_name.stem + ".html"
        )
        with open(output_file_path, "w") as f:
            f.write(file_html)

        if is_zipped_state:
            new_button = gr.DownloadButton(label="Download", value=None)
        else:
            # export the file path
            new_button = gr.DownloadButton(
                label=DOWNLOAD_MESSAGE,
                value=output_file_path,
            )

        return not is_zipped_state, new_button

    def download_all_files(self):
        if self._index.config.get("private", False):
            raise gr.Error("This feature is not available for private collection.")

        zip_files = []
        for file_name in os.listdir(flowsettings.KH_CHUNKS_OUTPUT_DIR):
            zip_files.append(os.path.join(flowsettings.KH_CHUNKS_OUTPUT_DIR, file_name))
        for file_name in os.listdir(flowsettings.KH_MARKDOWN_OUTPUT_DIR):
            zip_files.append(
                os.path.join(flowsettings.KH_MARKDOWN_OUTPUT_DIR, file_name)
            )
        zip_file_path = os.path.join(flowsettings.KH_ZIP_OUTPUT_DIR, "all")
        with zipfile.ZipFile(f"{zip_file_path}.zip", "w") as zipMe:
            for file in zip_files:
                arcname = Path(file)
                zipMe.write(file, arcname=arcname.name)
        return gr.DownloadButton(label=DOWNLOAD_MESSAGE, value=f"{zip_file_path}.zip")

    def delete_all_files(self, file_list, user_id):
        for file_id in file_list.id.values:
            self.delete_event(file_id, user_id)

    def set_file_id_selector(self, selected_file_id):
        return [selected_file_id, "select", gr.Tabs(selected="chat-tab")]

    def show_delete_all_confirm(self, file_list):
        # when the list of files is empty it shows a single line with id equal to -
        if len(file_list) == 0 or (
            len(file_list) == 1 and file_list.id.values[0] == "-"
        ):
            gr.Info("No file to delete")
            return [
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ]
        else:
            return [
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=True),
            ]

    def on_register_quick_uploads(self):
        try:
            # quick file upload event registration of first Index only
            if self._index.id == 1:
                self.quick_upload_state = gr.State(value=[])
                print("Setting up quick upload event")

                # override indexing function from chat page
                self._app.chat_page.first_indexing_url_fn = (
                    self.index_fn_url_with_default_loaders
                )

                if not KH_DEMO_MODE:
                    quickUploadedEvent = (
                        self._app.chat_page.quick_file_upload.upload(
                            fn=lambda: gr.update(
                                value="Please wait for the indexing process "
                                "to complete before adding your question."
                            ),
                            outputs=self._app.chat_page.quick_file_upload_status,
                        )
                        .then(
                            fn=self.index_fn_file_with_default_loaders,
                            inputs=[
                                self._app.chat_page.quick_file_upload,
                                gr.State(value=False),
                                self._app.settings_state,
                                self._app.user_id,
                            ],
                            outputs=self.quick_upload_state,
                            concurrency_limit=10,
                        )
                        .success(
                            fn=lambda: [
                                gr.update(value=None),
                                gr.update(value="select"),
                            ],
                            outputs=[
                                self._app.chat_page.quick_file_upload,
                                self._app.chat_page._indices_input[0],
                            ],
                        )
                    )
                    for event in self._app.get_event(
                        f"onFileIndex{self._index.id}Changed"
                    ):
                        quickUploadedEvent = quickUploadedEvent.then(**event)

                    quickUploadedEvent = (
                        quickUploadedEvent.success(
                            fn=lambda x: x,
                            inputs=self.quick_upload_state,
                            outputs=self._app.chat_page._indices_input[1],
                        )
                        .then(
                            fn=lambda: gr.update(value="Indexing completed."),
                            outputs=self._app.chat_page.quick_file_upload_status,
                        )
                        .then(
                            fn=self.list_file,
                            inputs=[self._app.user_id, self.filter],
                            outputs=[self.file_list_state, self.file_list],
                            concurrency_limit=20,
                        )
                        .then(
                            fn=lambda: True,
                            inputs=None,
                            outputs=None,
                            js=chat_input_focus_js_with_submit,
                        )
                    )

                quickURLUploadedEvent = (
                    self._app.chat_page.quick_urls.submit(
                        fn=lambda: gr.update(
                            value="Please wait for the indexing process "
                            "to complete before adding your question."
                        ),
                        outputs=self._app.chat_page.quick_file_upload_status,
                    )
                    .then(
                        fn=self.index_fn_url_with_default_loaders,
                        inputs=[
                            self._app.chat_page.quick_urls,
                            gr.State(value=False),
                            self._app.settings_state,
                            self._app.user_id,
                        ],
                        outputs=self.quick_upload_state,
                        concurrency_limit=10,
                    )
                    .success(
                        fn=lambda: [
                            gr.update(value=None),
                            gr.update(value="select"),
                        ],
                        outputs=[
                            self._app.chat_page.quick_urls,
                            self._app.chat_page._indices_input[0],
                        ],
                    )
                )
                for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
                    quickURLUploadedEvent = quickURLUploadedEvent.then(**event)

                quickURLUploadedEvent = quickURLUploadedEvent.success(
                    fn=lambda x: x,
                    inputs=self.quick_upload_state,
                    outputs=self._app.chat_page._indices_input[1],
                ).then(
                    fn=lambda: gr.update(value="Indexing completed."),
                    outputs=self._app.chat_page.quick_file_upload_status,
                )

                if not KH_DEMO_MODE:
                    quickURLUploadedEvent = quickURLUploadedEvent.then(
                        fn=self.list_file,
                        inputs=[self._app.user_id, self.filter],
                        outputs=[self.file_list_state, self.file_list],
                        concurrency_limit=20,
                    )

                quickURLUploadedEvent = quickURLUploadedEvent.then(
                    fn=lambda: True,
                    inputs=None,
                    outputs=None,
                    js=chat_input_focus_js_with_submit,
                )

        except Exception as e:
            print(e)

    def on_register_events(self):
        """Register all events to the app"""
        self.on_register_quick_uploads()

        if KH_DEMO_MODE:
            return

        onDeleted = (
            self.delete_button.click(
                fn=self.delete_event,
                inputs=[self.selected_file_id, self._app.user_id],
                outputs=None,
            )
            .then(
                fn=lambda: (None, self.selected_panel_false),
                inputs=[],
                outputs=[self.selected_file_id, self.selected_panel],
                show_progress="hidden",
            )
            .then(
                fn=self.list_file,
                inputs=[self._app.user_id, self.filter],
                outputs=[self.file_list_state, self.file_list],
            )
            .then(
                fn=self.file_selected,
                inputs=[self.selected_file_id],
                outputs=[
                    self.chunks,
                    self.deselect_button,
                    self.delete_button,
                    self.download_single_button,
                    self.chat_button,
                ],
                show_progress="hidden",
            )
        )
        for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
            onDeleted = onDeleted.then(**event)

        onDeselected = self.deselect_button.click(
            fn=lambda: (None, self.selected_panel_false),
            inputs=[],
            outputs=[self.selected_file_id, self.selected_panel],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[self.selected_file_id],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
            ],
            show_progress="hidden",
        )
        if self._app.f_user_management:
            onDeselected = onDeselected.then(
                fn=self.selected_file_team_choices,
                inputs=[self.selected_file_id, self._app.user_id],
                outputs=[self.file_team_ids, self.file_team_save_button],
                show_progress="hidden",
            )

        self.chat_button.click(
            fn=self.set_file_id_selector,
            inputs=[self.selected_file_id],
            outputs=[
                self._index.get_selector_component_ui().selector,
                self._index.get_selector_component_ui().mode,
                self._app.tabs,
            ],
        )

        if not KH_SSO_ENABLED:
            self.download_all_button.click(
                fn=self.download_all_files,
                inputs=[],
                outputs=self.download_all_button,
                show_progress="hidden",
            )

        self.delete_all_button.click(
            self.show_delete_all_confirm,
            [self.file_list],
            [
                self.delete_all_button,
                self.delete_all_button_confirm,
                self.delete_all_button_cancel,
            ],
        )
        self.delete_all_button_cancel.click(
            lambda: [
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ],
            None,
            [
                self.delete_all_button,
                self.delete_all_button_confirm,
                self.delete_all_button_cancel,
            ],
        )

        self.delete_all_button_confirm.click(
            fn=self.delete_all_files,
            inputs=[self.file_list, self._app.user_id],
            outputs=[],
            show_progress="hidden",
        ).then(
            fn=self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
        ).then(
            lambda: [
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ],
            None,
            [
                self.delete_all_button,
                self.delete_all_button_confirm,
                self.delete_all_button_cancel,
            ],
        )

        if not KH_SSO_ENABLED:
            self.download_single_button.click(
                fn=self.download_single_file,
                inputs=[self.is_zipped_state, self.selected_file_id, self._app.user_id],
                outputs=[self.is_zipped_state, self.download_single_button],
                show_progress="hidden",
            )
        else:
            self.download_single_button.click(
                fn=self.download_single_file_simple,
                inputs=[self.is_zipped_state, self.chunks, self.selected_file_id, self._app.user_id],
                outputs=[self.is_zipped_state, self.download_single_button],
                show_progress="hidden",
            )

        onUploaded = (
            self.upload_button.click(
                fn=lambda: gr.update(visible=True),
                outputs=[self.upload_progress_panel],
            )
            .then(
                fn=self.index_fn,
                inputs=[
                    self.files,
                    self.urls,
                    self.reindex,
                    self._app.settings_state,
                    self._app.user_id,
                    self.document_team_ids,
                ],
                outputs=[self.upload_result, self.upload_info],
                concurrency_limit=20,
            )
            .then(
                fn=lambda: gr.update(value=""),
                outputs=[self.urls],
            )
        )

        uploadedEvent = onUploaded.then(
            fn=self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
            concurrency_limit=20,
        )
        for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
            uploadedEvent = uploadedEvent.then(**event)

        _ = onUploaded.success(
            fn=lambda: None,
            outputs=[self.files],
        )

        self.btn_close_upload_progress_panel.click(
            fn=lambda: (gr.update(visible=False), "", ""),
            outputs=[self.upload_progress_panel, self.upload_result, self.upload_info],
        )

        onFileSelected = self.file_list.select(
            fn=self.interact_file_list,
            inputs=[self.file_list],
            outputs=[self.selected_file_id, self.selected_panel],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[self.selected_file_id],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
            ],
            show_progress="hidden",
        )
        if self._app.f_user_management:
            onFileSelected = onFileSelected.then(
                fn=self.selected_file_team_choices,
                inputs=[self.selected_file_id, self._app.user_id],
                outputs=[self.file_team_ids, self.file_team_save_button],
                show_progress="hidden",
            )
            onFileTeamSaved = self.file_team_save_button.click(
                fn=self.save_selected_file_teams,
                inputs=[self.selected_file_id, self._app.user_id, self.file_team_ids],
                outputs=[self.file_team_ids],
                show_progress="hidden",
            ).then(
                fn=self.list_file,
                inputs=[self._app.user_id, self.filter],
                outputs=[self.file_list_state, self.file_list],
                show_progress="hidden",
            )
            for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
                onFileTeamSaved = onFileTeamSaved.then(**event)

        self.group_list.select(
            fn=self.interact_group_list,
            inputs=[self.group_list_state, self._app.user_id],
            outputs=[
                self.group_label,
                self.selected_group_id,
                self.group_name,
                self.group_files,
                self.group_team_ids,
            ],
            show_progress="hidden",
        ).then(
            fn=lambda: (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=True),
            ),
            outputs=[
                self._group_info_panel,
                self.group_add_button,
                self.group_close_button,
                self.group_delete_button,
                self.group_chat_button,
            ],
        )

        self.filter.submit(
            fn=self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
            show_progress="hidden",
        )

        self.group_add_button.click(
            fn=self.prepare_new_group,
            inputs=[self._app.user_id],
            outputs=[
                self.group_add_button,
                self.group_label,
                self._group_info_panel,
                self.group_name,
                self.group_files,
                self.group_team_ids,
                self.selected_group_id,
            ],
        )

        self.group_chat_button.click(
            fn=self.set_group_id_selector,
            inputs=[self.selected_group_id, self._app.user_id],
            outputs=[
                self._index.get_selector_component_ui().selector,
                self._index.get_selector_component_ui().mode,
                self._app.tabs,
            ],
        )

        onGroupClosedEvent = {
            "fn": lambda: [
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                None,
            ],
            "outputs": [
                self.group_add_button,
                self._group_info_panel,
                self.group_close_button,
                self.group_delete_button,
                self.group_chat_button,
                self.selected_group_id,
            ],
        }
        self.group_close_button.click(**onGroupClosedEvent)
        onGroupSaved = (
            self.group_save_button.click(
                fn=self.save_group,
                inputs=[
                    self.selected_group_id,
                    self.group_name,
                    self.group_files,
                    self.group_team_ids,
                    self._app.user_id,
                ],
            )
            .then(
                self.list_group,
                inputs=[self._app.user_id, self.file_list_state],
                outputs=[self.group_list_state, self.group_list],
            )
            .then(**onGroupClosedEvent)
        )
        onGroupDeleted = (
            self.group_delete_button.click(
                fn=self.delete_group,
                inputs=[self.selected_group_id, self._app.user_id],
            )
            .then(
                self.list_group,
                inputs=[self._app.user_id, self.file_list_state],
                outputs=[self.group_list_state, self.group_list],
            )
            .then(**onGroupClosedEvent)
        )

        for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
            onGroupDeleted = onGroupDeleted.then(**event)
            onGroupSaved = onGroupSaved.then(**event)

    def _on_app_created(self):
        """Called when the app is created"""
        if KH_DEMO_MODE:
            return

        self._app.app.load(
            self.list_file,
            inputs=[self._app.user_id, self.filter],
            outputs=[self.file_list_state, self.file_list],
        ).then(
            self.list_group,
            inputs=[self._app.user_id, self.file_list_state],
            outputs=[self.group_list_state, self.group_list],
        ).then(
            self.list_file_names,
            inputs=[self.file_list_state],
            outputs=[self.group_files],
        )
        if self._app.f_user_management:
            self._app.app.load(
                self.list_document_team_choices,
                inputs=[self._app.user_id],
                outputs=[self.document_team_ids],
            )

    def _may_extract_zip(self, files, zip_dir: str):
        """Handle zip files"""
        zip_files = [file for file in files if file.endswith(".zip")]
        remaining_files = [file for file in files if not file.endswith("zip")]
        errors: list[str] = []

        # Clean-up <zip_dir> before unzip to remove old files
        shutil.rmtree(zip_dir, ignore_errors=True)

        # Unzip
        for zip_file in zip_files:
            # Prepare new zip output dir, separated for each files
            basename = os.path.splitext(os.path.basename(zip_file))[0]
            zip_out_dir = os.path.join(zip_dir, basename)
            os.makedirs(zip_out_dir, exist_ok=True)

            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                zip_ref.extractall(zip_out_dir)

        n_zip_file = 0
        for root, dirs, files in os.walk(zip_dir):
            for file in files:
                ext = os.path.splitext(file)[1]

                # only allow supported file-types ( not zip )
                if ext not in [".zip"] and ext in self._supported_file_types:
                    remaining_files += [os.path.join(root, file)]
                    n_zip_file += 1

        if n_zip_file > 0:
            print(f"Update zip files: {n_zip_file}")

        return remaining_files, errors

    def index_fn(
        self, files, urls, reindex: bool, settings, user_id, document_team_ids=None
    ) -> Generator[tuple[str, str], None, None]:
        """Upload and index the files

        Args:
            files: the list of files to be uploaded
            urls: list of web URLs to be indexed
            reindex: whether to reindex the files
            selected_files: the list of files already selected
            settings: the settings of the app
        """
        if not self._check_upload_permission(user_id):
            yield "", ""
            return

        if urls:
            files = [it.strip() for it in urls.split("\n")]
            errors = self.validate_urls(files)
        else:
            if not files:
                gr.Info("No uploaded file")
                yield "", ""
                return
            files, unzip_errors = self._may_extract_zip(
                files, flowsettings.KH_ZIP_INPUT_DIR
            )
            errors = self.validate_files(files)
            errors.extend(unzip_errors)

        if errors:
            gr.Warning(", ".join(errors))
            yield "", ""
            return

        gr.Info(f"Start indexing {len(files)} files...")

        # get the pipeline
        try:
            indexing_pipeline = self._index.get_indexing_pipeline(settings, user_id)
        except Exception as e:
            gr.Warning("Indexierungs-Pipeline konnte nicht initialisiert werden")
            yield "", f"Pipeline-Fehler: {e}\n{traceback.format_exc()}"
            return

        outputs, debugs = [], []
        # stream the output
        output_stream = indexing_pipeline.stream(files, reindex=reindex)
        try:
            while True:
                response = next(output_stream)
                if response is None:
                    continue
                if response.channel == "index":
                    if response.content["status"] == "success":
                        outputs.append(f"\u2705 | {response.content['file_name']}")
                    elif response.content["status"] == "failed":
                        outputs.append(
                            f"\u274c | {response.content['file_name']}: "
                            f"{response.content['message']}"
                        )
                elif response.channel == "debug":
                    debugs.append(response.text)
                yield "\n".join(outputs), "\n".join(debugs)
        except StopIteration as e:
            results, index_errors, docs = e.value
        except Exception as e:
            debugs.append(f"Error: {e}")
            debugs.append(traceback.format_exc())
            yield "\n".join(outputs), "\n".join(debugs)
            return

        n_successes = len([_ for _ in results if _])
        if n_successes:
            gr.Info(f"Successfully index {n_successes} files")
        n_errors = len([_ for _ in errors if _])
        if n_errors:
            gr.Warning(f"Have errors for {n_errors} files")

        self._apply_document_teams(results, user_id, document_team_ids)

        return results

    def index_fn_file_with_default_loaders(
        self, files, reindex: bool, settings, user_id
    ) -> list["str"]:
        """Function for quick upload with default loaders

        Args:
            files: the list of files to be uploaded
            reindex: whether to reindex the files
            selected_files: the list of files already selected
            settings: the settings of the app
        """
        print("Overriding with default loaders")
        if not self._check_upload_permission(user_id):
            return []
        exist_ids = []
        to_process_files = []
        for str_file_path in files:
            file_path = Path(str(str_file_path))
            try:
                exist_id = (
                    self._index.get_indexing_pipeline(settings, user_id)
                    .route(file_path)
                    .get_id_if_exists(file_path)
                )
            except Exception:
                exist_id = None
            if exist_id:
                exist_ids.append(exist_id)
            else:
                to_process_files.append(str_file_path)

        returned_ids = []
        settings = deepcopy(settings)
        settings[f"index.options.{self._index.id}.reader_mode"] = "default"
        settings[f"index.options.{self._index.id}.quick_index_mode"] = True
        if to_process_files:
            _iter = self.index_fn(
                to_process_files, [], reindex, settings, user_id, None
            )
            try:
                while next(_iter):
                    pass
            except StopIteration as e:
                returned_ids = e.value

        return exist_ids + returned_ids

    def index_fn_url_with_default_loaders(
        self,
        urls,
        reindex: bool,
        settings,
        user_id,
        request: gr.Request,
    ):
        if not self._check_upload_permission(user_id):
            return []
        if KH_DEMO_MODE:
            check_rate_limit("file_upload", request)

        returned_ids: list[str] = []
        settings = deepcopy(settings)
        settings[f"index.options.{self._index.id}.reader_mode"] = "default"
        settings[f"index.options.{self._index.id}.quick_index_mode"] = True

        if KH_DEMO_MODE:
            urls_splitted = urls.split("\n")
            if not all(is_arxiv_url(url) for url in urls_splitted):
                raise ValueError("All URLs must be valid arXiv URLs")

            output_files = [
                download_arxiv_pdf(
                    url,
                    output_path=os.environ.get("GRADIO_TEMP_DIR", "/tmp"),
                )
                for url in urls_splitted
            ]

            exist_ids = []
            to_process_files = []
            for str_file_path in output_files:
                file_path = Path(str_file_path)
                try:
                    exist_id = (
                        self._index.get_indexing_pipeline(settings, user_id)
                        .route(file_path)
                        .get_id_if_exists(file_path)
                    )
                except Exception:
                    exist_id = None
                if exist_id:
                    exist_ids.append(exist_id)
                else:
                    to_process_files.append(str_file_path)

            returned_ids = []
            if to_process_files:
                _iter = self.index_fn(
                    to_process_files, [], reindex, settings, user_id, None
                )
                try:
                    while next(_iter):
                        pass
                except StopIteration as e:
                    returned_ids = e.value

            returned_ids = exist_ids + returned_ids
        else:
            if urls:
                _iter = self.index_fn([], urls, reindex, settings, user_id, None)
                try:
                    while next(_iter):
                        pass
                except StopIteration as e:
                    returned_ids = e.value

        return returned_ids

    def index_files_from_dir(
        self, folder_path, reindex, settings, user_id
    ) -> Generator[tuple[str, str], None, None]:
        """This should be constructable by users

        It means that the users can build their own index.
        Build your own index:
            - Input:
                - Type: based on the type, then there are ranges of. Use can select
                multiple panels:
                    - Panels
                    - Data sources
                    - Include patterns
                    - Exclude patterns
                - Indexing functions. Can be a list of indexing functions. Each declared
                function is:
                    - Condition (the source that will go through this indexing function)
                    - Function (the pipeline that run this)
            - Output: artifacts that can be used to -> this is the artifacts that we
            wish
                - Build the UI
                    - Upload page: fixed standard, based on the type
                    - Read page: fixed standard, based on the type
                    - Delete page: fixed standard, based on the type
                - Build the index function
                - Build the chat function

        Step:
            1. Decide on the artifacts
            2. Implement the transformation from artifacts to UI
        """
        if not folder_path:
            yield "", ""
            return

        import fnmatch
        from pathlib import Path

        include_patterns: list[str] = []
        exclude_patterns: list[str] = ["*.png", "*.gif", "*/.*"]
        if include_patterns and exclude_patterns:
            raise ValueError("Cannot have both include and exclude patterns")

        # clean up the include patterns
        for idx in range(len(include_patterns)):
            if include_patterns[idx].startswith("*"):
                include_patterns[idx] = str(Path.cwd() / "**" / include_patterns[idx])
            else:
                include_patterns[idx] = str(
                    Path.cwd() / include_patterns[idx].strip("/")
                )

        # clean up the exclude patterns
        for idx in range(len(exclude_patterns)):
            if exclude_patterns[idx].startswith("*"):
                exclude_patterns[idx] = str(Path.cwd() / "**" / exclude_patterns[idx])
            else:
                exclude_patterns[idx] = str(
                    Path.cwd() / exclude_patterns[idx].strip("/")
                )

        # get the files
        files: list[str] = [str(p) for p in Path(folder_path).glob("**/*.*")]
        if include_patterns:
            for p in include_patterns:
                files = fnmatch.filter(names=files, pat=p)

        if exclude_patterns:
            for p in exclude_patterns:
                files = [f for f in files if not fnmatch.fnmatch(name=f, pat=p)]

        yield from self.index_fn(files, [], reindex, settings, user_id, None)

    def format_size_human_readable(self, num: float | str, suffix="B"):
        try:
            num = float(num)
        except ValueError:
            return num

        for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
            if abs(num) < 1024.0:
                return f"{num:3.0f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.0f}Yi{suffix}"

    def list_file(self, user_id, name_pattern=""):
        if user_id is None:
            # not signed in
            return [], pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "group": "-",
                        "size": "-",
                        "tokens": "-",
                        "loader": "-",
                        "date_created": "-",
                    }
                ]
            )

        Source = self._index._resources["Source"]
        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            statement = select(Source)
            actor = None
            scope_ids = None
            if self._app.f_user_management:
                actor = get_access_context(session, user_id)
                if not actor or not has_read_access(actor):
                    return [], pd.DataFrame.from_records(
                        [
                            {
                                "id": "-",
                                "name": "-",
                                "group": "-",
                                "size": "-",
                                "tokens": "-",
                                "loader": "-",
                                "date_created": "-",
                            }
                        ]
                    )
                scope_ids = allowed_user_ids_for_scope(session, actor)
            if scope_ids == []:
                return [], pd.DataFrame.from_records(
                    [
                        {
                            "id": "-",
                            "name": "-",
                            "group": "-",
                            "size": "-",
                            "tokens": "-",
                            "loader": "-",
                            "date_created": "-",
                        }
                    ]
                )
            if scope_ids is not None and not self._app.f_user_management:
                statement = statement.where(Source.user.in_(scope_ids))
            if self._index.config.get("private", False):
                if scope_ids is None:
                    statement = statement.where(Source.user == user_id)
            if name_pattern:
                statement = statement.where(Source.name.ilike(f"%{name_pattern}%"))

            visible_global_team_ids = globally_visible_team_ids(session) if actor else set()
            file_id_to_groups: dict[str, list[str]] = {}
            for row in session.execute(select(FileGroup)).all():
                group = row[0]
                if scope_ids is not None and getattr(group, "user", None) not in scope_ids:
                    continue
                if actor and not _group_visible_to_actor(
                    group, actor, visible_global_team_ids, scope_ids
                ):
                    continue
                for file_id in (group.data or {}).get("files", []):
                    file_id_to_groups.setdefault(file_id, []).append(group.name)

            results = []
            for each in session.execute(statement).all():
                source = each[0]
                if self._app.f_user_management and not _source_visible_to_actor(
                    source, actor, visible_global_team_ids, scope_ids
                ):
                    continue
                group_names = sorted(file_id_to_groups.get(source.id, []))
                results.append(
                    {
                        "id": source.id,
                        "name": source.name,
                        "group": ", ".join(group_names) if group_names else "-",
                        "size": self.format_size_human_readable(source.size),
                        "tokens": self.format_size_human_readable(
                            (source.note or {}).get("tokens", "-"), suffix=""
                        ),
                        "loader": (source.note or {}).get("loader", "-"),
                        "date_created": source.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        if results:
            file_list = pd.DataFrame.from_records(results)
        else:
            file_list = pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "group": "-",
                        "size": "-",
                        "tokens": "-",
                        "loader": "-",
                        "date_created": "-",
                    }
                ]
            )

        return results, file_list

    def list_file_names(self, file_list_state):
        if file_list_state:
            file_names = [(item["name"], item["id"]) for item in file_list_state]
        else:
            file_names = []

        return gr.update(choices=file_names)

    def list_group(self, user_id, file_list):
        # supply file_list to display the file names in the group
        if file_list:
            file_id_to_name = {item["id"]: item["name"] for item in file_list}
        else:
            file_id_to_name = {}

        if user_id is None:
            # not signed in
            return [], pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "teams": "-",
                        "files": "-",
                        "date_created": "-",
                    }
                ]
            )

        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            statement = select(FileGroup)
            scope_ids = self._scope_user_ids(session, user_id)
            if scope_ids == []:
                return [], pd.DataFrame.from_records(
                    [
                        {
                            "id": "-",
                            "name": "-",
                            "teams": "-",
                            "files": "-",
                            "date_created": "-",
                        }
                    ]
                )
            if scope_ids is not None:
                statement = statement.where(FileGroup.user.in_(scope_ids))
            if self._index.config.get("private", False):
                if scope_ids is None:
                    statement = statement.where(FileGroup.user == user_id)

            actor = get_access_context(session, user_id) if self._app.f_user_management else None
            visible_global_team_ids = globally_visible_team_ids(session) if actor else set()
            team_map = {team.id: team.name for team in list_teams(session)} if self._app.f_user_management else {}
            visible_source_ids = None
            if self._app.f_user_management:
                visible_source_ids, _, _ = self._visible_source_ids_for_actor(session, user_id)

            results = []
            for each in session.execute(statement).all():
                group = each[0]
                if actor and not _group_visible_to_actor(
                    group, actor, visible_global_team_ids, scope_ids
                ):
                    continue
                group_files = [
                    file_id
                    for file_id in group.data.get("files", [])
                    if visible_source_ids is None or file_id in visible_source_ids
                ]
                group_team_ids = _group_team_ids(group)
                results.append(
                    {
                        "id": group.id,
                        "name": group.name,
                        "teams": [team_map.get(team_id, team_id) for team_id in group_team_ids],
                        "team_ids": group_team_ids,
                        "files": group_files,
                        "date_created": group.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        if results:
            formated_results = deepcopy(results)
            for item in formated_results:
                team_names = item.pop("teams", [])
                item.pop("team_ids", None)
                item["teams"] = ", ".join(team_names) if team_names else "-"
                file_names = [
                    file_id_to_name.get(file_id, "-") for file_id in item["files"]
                ]
                item["files"] = ", ".join(
                    f"'{it[:MAX_FILENAME_LENGTH]}..'"
                    if len(it) > MAX_FILENAME_LENGTH
                    else f"'{it}'"
                    for it in file_names
                )
                item_count = len(file_names)
                item_postfix = "s" if item_count > 1 else ""
                item["files"] = f"[{item_count} item{item_postfix}] " + item["files"]

            group_list = pd.DataFrame.from_records(formated_results)
        else:
            group_list = pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "teams": "-",
                        "files": "-",
                        "date_created": "-",
                    }
                ]
            )

        return results, group_list

    def set_group_id_selector(self, selected_group_id, user_id):
        FileGroup = self._index._resources["FileGroup"]

        with Session(engine) as session:
            current_group = (
                session.query(FileGroup).filter_by(id=selected_group_id).first()
            )
            if current_group is None:
                raise gr.Error("No group found")
            scope_ids = self._scope_user_ids(session, user_id)
            actor = get_access_context(session, user_id) if self._app.f_user_management else None
            visible_global_team_ids = globally_visible_team_ids(session) if actor else set()
            if scope_ids is not None and current_group.user not in scope_ids:
                raise gr.Error("Keine Berechtigung für diese Gruppe")
            if actor and not _group_visible_to_actor(
                current_group, actor, visible_global_team_ids, scope_ids
            ):
                raise gr.Error("Keine Berechtigung für diese Gruppe")
            visible_source_ids, _, _ = self._visible_source_ids_for_actor(session, user_id)

        file_ids = [
            json.dumps(
                [
                    file_id
                    for file_id in current_group.data.get("files", [])
                    if not self._app.f_user_management or file_id in visible_source_ids
                ]
            )
        ]
        return [file_ids, "select", gr.Tabs(selected="chat-tab")]

    def save_group(self, group_id, group_name, group_files, group_team_ids, user_id):
        FileGroup = self._index._resources["FileGroup"]
        current_group = None

        with Session(engine) as session:
            scope_ids = self._scope_user_ids(session, user_id)
            if scope_ids == []:
                raise gr.Error("Keine Berechtigung")
            actor = get_access_context(session, user_id) if self._app.f_user_management else None
            visible_global_team_ids = globally_visible_team_ids(session) if actor else set()
            visible_source_ids, _, _ = self._visible_source_ids_for_actor(session, user_id)
            sanitized_group_files = [
                file_id
                for file_id in (group_files or [])
                if file_id in visible_source_ids or not self._app.f_user_management
            ]
            if len(sanitized_group_files) != len(group_files or []):
                raise gr.Error("Mindestens eine ausgewählte Datei ist nicht mehr sichtbar")

            resolved_group_team_ids = []
            if self._app.f_user_management:
                resolved_group_team_ids, error = self._resolve_group_team_assignment(
                    session, user_id, group_team_ids
                )
                if error:
                    raise gr.Error(error)

            if group_id:
                current_group = session.query(FileGroup).filter_by(id=group_id).first()
                if scope_ids is not None and (
                    current_group is None or current_group.user not in scope_ids
                ):
                    raise gr.Error("Keine Berechtigung")
                if actor and not _group_visible_to_actor(
                    current_group, actor, visible_global_team_ids, scope_ids
                ):
                    raise gr.Error("Keine Berechtigung")
                current_group.name = group_name
                current_group.data["files"] = sanitized_group_files
                current_group.data["team_ids"] = resolved_group_team_ids
                session.commit()
            else:
                current_group = (
                    session.query(FileGroup)
                    .filter_by(
                        name=group_name,
                        user=user_id,
                    )
                    .first()
                )
                if current_group:
                    raise gr.Error(f"Group {group_name} already exists")

                current_group = FileGroup(
                    name=group_name,
                    data={"files": sanitized_group_files, "team_ids": resolved_group_team_ids},  # type: ignore
                    user=user_id,
                )
                session.add(current_group)
                session.commit()

            group_id = current_group.id

        gr.Info(f"Group {group_name} has been saved")
        return group_id

    def delete_group(self, group_id, user_id):
        if not group_id:
            raise gr.Error("No group is selected")

        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            group = session.execute(
                select(FileGroup).where(FileGroup.id == group_id)
            ).first()
            if group:
                item = group[0]
                scope_ids = self._scope_user_ids(session, user_id)
                actor = get_access_context(session, user_id) if self._app.f_user_management else None
                visible_global_team_ids = globally_visible_team_ids(session) if actor else set()
                if scope_ids is not None and item.user not in scope_ids:
                    raise gr.Error("Keine Berechtigung")
                if actor and not _group_visible_to_actor(
                    item, actor, visible_global_team_ids, scope_ids
                ):
                    raise gr.Error("Keine Berechtigung")
                group_name = item.name
                session.delete(item)
                session.commit()
                gr.Info(f"Group {group_name} has been deleted")
            else:
                raise gr.Error("No group found")

        return None

    def interact_file_list(self, list_files, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("No file is uploaded")
            return None, self.selected_panel_false

        if not ev.selected:
            return None, self.selected_panel_false

        return list_files["id"][ev.index[0]], self.selected_panel_true.format(
            name=list_files["name"][ev.index[0]]
        )

    def interact_group_list(self, list_groups, user_id, ev: gr.SelectData):
        selected_id = ev.index[0]
        if (not ev.value or ev.value == "-") and selected_id == 0:
            raise gr.Error("No group is selected")

        selected_item = list_groups[selected_id]
        selected_group_id = selected_item["id"]
        return (
            "### Group Information",
            selected_group_id,
            selected_item["name"],
            selected_item["files"],
            self.list_group_team_choices(user_id, selected_item.get("team_ids", [])),
        )

    def validate_files(self, files: list[str]):
        """Validate if the files are valid"""
        paths = [Path(file) for file in files]
        errors = []
        if max_file_size := self._index.config.get("max_file_size", 0):
            errors_max_size = []
            for path in paths:
                if path.stat().st_size > max_file_size * 1e6:
                    errors_max_size.append(path.name)
            if errors_max_size:
                str_errors = ", ".join(errors_max_size)
                if len(str_errors) > 60:
                    str_errors = str_errors[:55] + "..."
                errors.append(
                    f"Maximum file size ({max_file_size} MB) exceeded: {str_errors}"
                )

        if max_number_of_files := self._index.config.get("max_number_of_files", 0):
            with Session(engine) as session:
                current_num_files = session.query(
                    self._index._resources["Source"].id
                ).count()
            if len(paths) + current_num_files > max_number_of_files:
                errors.append(
                    f"Maximum number of files ({max_number_of_files}) will be exceeded"
                )

        return errors

    def validate_urls(self, urls: list[str]):
        """Validate if the urls are valid"""
        errors = []
        for url in urls:
            if not url.startswith("http") and not url.startswith("https"):
                errors.append(f"Invalid url `{url}`")
        return errors


class FileSelector(BasePage):
    """File selector UI in the Chat page"""

    def __init__(self, app, index):
        super().__init__(app)
        self._index = index
        self.on_building_ui()

    def default(self):
        if self._app.f_user_management:
            return "disabled", [], -1
        return "disabled", [], 1

    def on_building_ui(self):
        default_mode, default_selector, user_id = self.default()

        self.mode = gr.Radio(
            value=default_mode,
            choices=[
                ("Alle durchsuchen", "all"),
                ("In Datei(en) suchen", "select"),
                ("In Dateigruppe(n) suchen", "group_select"),
            ],
            container=False,
        )
        self.selector = gr.Dropdown(
            label="Dateien",
            value=default_selector,
            choices=[],
            multiselect=True,
            filterable=True,
            container=False,
            interactive=True,
            visible=False,
        )
        self.group_selector = gr.Dropdown(
            label="Dateigruppen",
            value=[],
            choices=[],
            multiselect=True,
            filterable=True,
            container=False,
            interactive=True,
            visible=False,
        )
        self.team_filter = gr.Dropdown(
            label="Team",
            value="",
            choices=[("Alle Teams", "")],
            container=False,
            interactive=True,
            filterable=True,
            visible=self._app.f_user_management,
        )
        self.selector_user_id = gr.State(value=user_id)
        self.selector_choices = gr.JSON(
            value=[],
            visible=False,
        )

    def on_register_events(self):
        self.mode.change(
            fn=lambda mode, user_id: (
                gr.update(visible=mode == "select"),
                gr.update(visible=mode == "group_select"),
                gr.update(visible=self._app.f_user_management),
                user_id,
            ),
            inputs=[self.mode, self._app.user_id],
            outputs=[self.selector, self.group_selector, self.team_filter, self.selector_user_id],
        ).then(
            self.load_files,
            inputs=[
                self.selector,
                self.group_selector,
                self._app.user_id,
                self.team_filter,
                self.mode,
            ],
            outputs=[
                self.selector,
                self.selector_choices,
                self.group_selector,
                self.team_filter,
                self.mode,
            ],
            show_progress="hidden",
        )
        self.team_filter.change(
            self.load_files,
            inputs=[self.selector, self.group_selector, self._app.user_id, self.team_filter, self.mode],
            outputs=[self.selector, self.selector_choices, self.group_selector, self.team_filter, self.mode],
            show_progress="hidden",
        )
        # attach special event for the first index
        if self._index.id == 1:
            self.selector_choices.change(
                fn=None,
                inputs=[self.selector_choices],
                js=update_file_list_js,
                show_progress="hidden",
            )

    def as_gradio_component(self):
        return [self.mode, self.selector, self.selector_user_id, self.team_filter, self.group_selector]

    def get_selected_ids(self, components):
        mode, selected, user_id = components[0], components[1], components[2]
        team_filter = components[3] if len(components) > 3 else ""
        selected_groups = components[4] if len(components) > 4 else []
        if user_id is None:
            return []

        if mode == "disabled":
            return []
        elif mode == "select":
            return selected
        elif mode == "group_select":
            file_ids = []
            for group_value in selected_groups or []:
                try:
                    group_file_ids = json.loads(group_value)
                except (TypeError, json.JSONDecodeError):
                    continue
                for file_id in group_file_ids:
                    if file_id not in file_ids:
                        file_ids.append(file_id)
            return file_ids

        file_ids = []
        with Session(engine) as session:
            statement = select(self._index._resources["Source"].id)
            actor = None
            scope_ids = None
            if self._app.f_user_management:
                actor = get_access_context(session, user_id)
                if not actor or not has_read_access(actor):
                    return []
                scope_ids = allowed_user_ids_for_scope(session, actor)
                statement = select(self._index._resources["Source"])
            if self._index.config.get("private", False):
                if not self._app.f_user_management:
                    statement = statement.where(
                        self._index._resources["Source"].user == user_id
                    )
            results = session.execute(statement).all()
            if self._app.f_user_management:
                visible_global_team_ids = globally_visible_team_ids(session)
                for result in results:
                    source = result[0]
                    if not _source_visible_to_actor(source, actor, visible_global_team_ids, scope_ids):
                        continue
                    source_team_ids = _source_team_ids(source)
                    has_global_team = bool(set(source_team_ids).intersection(visible_global_team_ids))
                    if source_team_ids:
                        if team_filter:
                            if team_filter not in source_team_ids:
                                continue
                        elif not has_global_team:
                            continue
                    elif team_filter:
                        continue
                    file_ids.append(source.id)
            else:
                for (id,) in results:
                    file_ids.append(id)

        return file_ids

    def load_files(self, selected_files, selected_groups, user_id, team_filter="", current_mode="disabled"):
        options: list = []
        group_options: list = []
        available_ids = []
        available_group_values = []
        team_filter_choices = [("Alle Teams", "")]
        resolved_mode = current_mode
        if user_id is None:
            # not signed in
            return (
                gr.update(value=selected_files, choices=options),
                options,
                gr.update(value=selected_groups, choices=group_options),
                gr.update(value="", choices=team_filter_choices),
                gr.update(value=resolved_mode),
            )

        with Session(engine) as session:
            # get file list from Source table
            statement = select(self._index._resources["Source"])
            scope_ids = None
            actor = None
            if self._app.f_user_management:
                actor = get_access_context(session, user_id)
                if not actor or not has_read_access(actor):
                    return (
                        gr.update(value=selected_files, choices=options),
                        options,
                        gr.update(value=selected_groups, choices=group_options),
                        gr.update(value="", choices=team_filter_choices),
                        gr.update(value=resolved_mode),
                    )
                scope_ids = allowed_user_ids_for_scope(session, actor)

                # Team selector choices for chat-side team search/filter.
                visible_teams = list_teams(session)
                visible_team_map = {t.id: t.name for t in visible_teams}
                visible_team_ids = []
                if actor.is_admin:
                    visible_team_ids = [team.id for team in visible_teams]
                else:
                    visible_team_ids = list(dict.fromkeys(list(actor.team_ids) + [
                        team.id for team in visible_teams if bool(getattr(team, "is_global", False))
                    ]))
                for team_id in visible_team_ids:
                    team_filter_choices.append((visible_team_map.get(team_id, team_id), team_id))
            if self._index.config.get("private", False):
                if not self._app.f_user_management:
                    statement = statement.where(
                        self._index._resources["Source"].user == user_id
                    )

            if KH_DEMO_MODE:
                # limit query by MAX_FILE_COUNT
                statement = statement.limit(MAX_FILE_COUNT)

            results = session.execute(statement).all()
            visible_global_team_ids = globally_visible_team_ids(session) if actor else set()
            for result in results:
                source = result[0]
                if actor and not _source_visible_to_actor(source, actor, visible_global_team_ids, scope_ids):
                    continue
                source_team_ids = _source_team_ids(source)
                has_global_team = bool(set(source_team_ids).intersection(visible_global_team_ids))
                if self._app.f_user_management:
                    if source_team_ids:
                        if team_filter:
                            if team_filter not in source_team_ids:
                                continue
                        elif not has_global_team:
                            continue
                    elif team_filter:
                        continue
                elif team_filter and team_filter not in source_team_ids:
                    continue
                available_ids.append(source.id)
                options.append((source.name, source.id))

            available_ids_set = set(available_ids)

            FileGroup = self._index._resources["FileGroup"]
            statement = select(FileGroup)
            if scope_ids is not None:
                statement = statement.where(FileGroup.user.in_(scope_ids))
            if self._index.config.get("private", False):
                if scope_ids is None:
                    statement = statement.where(FileGroup.user == user_id)
            results = session.execute(statement).all()
            for result in results:
                item = result[0]
                if actor and not _group_visible_to_actor(
                    item, actor, visible_global_team_ids, scope_ids
                ):
                    continue
                group_files = [
                    file_id for file_id in item.data.get("files", []) if file_id in available_ids_set
                ]
                group_value = json.dumps(group_files)
                available_group_values.append(group_value)
                group_options.append((item.name, group_value))

        if selected_files:
            available_ids_set = set(available_ids)
            selected_files = [
                each for each in selected_files if each in available_ids_set
            ]

        if selected_groups:
            available_group_values_set = set(available_group_values)
            selected_groups = [
                each for each in selected_groups if each in available_group_values_set
            ]

        valid_team_ids = {value for _, value in team_filter_choices}
        current_team = team_filter if team_filter in valid_team_ids else ""
        if not current_team and actor and self._app.f_user_management:
            default_team_id = getattr(actor.access, "default_team_id", None)
            if default_team_id in valid_team_ids:
                current_team = default_team_id
                if resolved_mode == "disabled":
                    resolved_mode = "all"
        return (
            gr.update(value=selected_files, choices=options),
            options,
            gr.update(value=selected_groups, choices=group_options),
            gr.update(value=current_team, choices=team_filter_choices),
            gr.update(value=resolved_mode),
        )

    def _on_app_created(self):
        self._app.app.load(
            self.load_files,
            inputs=[self.selector, self.group_selector, self._app.user_id, self.team_filter, self.mode],
            outputs=[self.selector, self.selector_choices, self.group_selector, self.team_filter, self.mode],
        )

    def refresh_after_index(self, selected_files, selected_groups, user_id, team_filter="", current_mode="disabled"):
        selector, selector_choices, group_selector, team_filter_update, mode_update = self.load_files(
            selected_files,
            selected_groups,
            user_id,
            team_filter,
            current_mode,
        )
        next_mode = getattr(mode_update, "value", current_mode)
        if next_mode == "disabled" and selector_choices:
            mode_update = gr.update(value="select")
        return (
            selector,
            selector_choices,
            group_selector,
            team_filter_update,
            mode_update,
        )

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name=f"onFileIndex{self._index.id}Changed",
            definition={
                "fn": self.refresh_after_index,
                "inputs": [self.selector, self.group_selector, self._app.user_id, self.team_filter, self.mode],
                "outputs": [self.selector, self.selector_choices, self.group_selector, self.team_filter, self.mode],
                "show_progress": "hidden",
            },
        )
        if self._app.f_user_management:
            for event_name in ["onSignIn", "onSignOut"]:
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_files,
                        "inputs": [self.selector, self.group_selector, self._app.user_id, self.team_filter, self.mode],
                        "outputs": [self.selector, self.selector_choices, self.group_selector, self.team_filter, self.mode],
                        "show_progress": "hidden",
                    },
                )
