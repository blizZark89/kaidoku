import html
import json
import os
import shutil
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Generator

import gradio as gr
import pandas as pd
from gradio.data_classes import FileData
from gradio.utils import NamedString
from ktem.app import BasePage
from ktem.db.engine import engine
from ktem.db.models import User
from ktem.pages.resources.user import (
    default_team_state,
    get_team_choices,
    normalize_team_state,
)
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

fetch_document_visibility_state_js = """
function(userId, currentValue) {
    return [userId, getStorage('kaidoku_document_visibility_state', currentValue || '')];
}
"""

save_document_visibility_state_js = """
function(documentState) {
    const serialized = JSON.stringify(documentState || {documents: {}});
    setStorage('kaidoku_document_visibility_state', serialized);
    return serialized;
}
"""

fetch_selector_access_state_js = """
function(userId, currentTeamValue, currentDocumentValue) {
    const teamKey = `kaidoku_team_state_${userId || 'anonymous'}`;
    return [
        userId,
        getStorage(teamKey, currentTeamValue || ''),
        getStorage('kaidoku_document_visibility_state', currentDocumentValue || ''),
    ];
}
"""

fetch_file_team_state_js = """
function(userId, currentValue) {
    const key = `kaidoku_team_state_${userId || 'anonymous'}`;
    return [userId, getStorage(key, currentValue || '')];
}
"""


def default_document_visibility_state():
    return {"documents": {}}


def normalize_document_visibility_state(document_state):
    state = default_document_visibility_state()
    if not isinstance(document_state, dict):
        return state

    documents = {}
    for document_id, entry in document_state.get("documents", {}).items():
        if not isinstance(entry, dict):
            continue
        doc_id = str(document_id).strip()
        owner_id = str(entry.get("ownerId", "")).strip()
        team_ids = entry.get("teamIds", [])
        if not isinstance(team_ids, list):
            team_ids = []
        if doc_id:
            documents[doc_id] = {
                "ownerId": owner_id,
                "teamIds": [str(team_id).strip() for team_id in team_ids if str(team_id).strip()],
            }

    state["documents"] = documents
    return state


def get_current_username_lower(user_id):
    if user_id is None:
        return ""

    with Session(engine) as session:
        user = session.execute(select(User).where(User.id == user_id)).first()

    if not user:
        return ""

    return user[0].username_lower


def get_current_user_team_ids(user_id, team_state):
    username_lower = get_current_username_lower(user_id)
    if not username_lower:
        return []

    state = normalize_team_state(team_state)
    return state["user_teams"].get(username_lower, [])


def get_document_access(source, document_visibility_state):
    state = normalize_document_visibility_state(document_visibility_state)
    entry = state["documents"].get(source.id, {})
    return {
        "ownerId": str(entry.get("ownerId") or source.user or ""),
        "teamIds": list(entry.get("teamIds", [])),
    }


def get_team_name_lookup(team_state):
    state = normalize_team_state(team_state)
    return {team_id: team_name for team_name, team_id in get_team_choices(state)}


def get_document_visibility_meta(source, user_id, team_state, document_visibility_state):
    access = get_document_access(source, document_visibility_state)
    owner_id = access["ownerId"]
    team_ids = access["teamIds"]
    user_team_ids = get_current_user_team_ids(user_id, team_state)
    is_owner = owner_id == str(user_id)
    shared_team_ids = [team_id for team_id in team_ids if team_id in user_team_ids]
    is_visible = is_owner or bool(shared_team_ids)
    return {
        "ownerId": owner_id,
        "teamIds": team_ids,
        "userTeamIds": user_team_ids,
        "sharedTeamIds": shared_team_ids,
        "isOwner": is_owner,
        "isVisible": is_visible,
    }


def get_visibility_label(team_ids, team_lookup):
    if not team_ids:
        return "Privat"
    names = [team_lookup[team_id] for team_id in team_ids if team_id in team_lookup]
    return ", ".join(names) if names else "Privat"


def get_visibility_badges_html(team_ids, team_lookup):
    if not team_ids:
        return (
            "<span style='display:inline-block;padding:4px 10px;border-radius:999px;"
            "background:#f5d7d7;border:1px solid #d96c6c;font-size:12px;'>Privat</span>"
        )

    return "".join(
        (
            "<span style='display:inline-block;padding:4px 10px;margin:0 6px 6px 0;"
            "border-radius:999px;background:var(--background-fill-secondary);"
            "border:1px solid var(--border-color-primary);font-size:12px;'>"
            f"{html.escape(team_lookup[team_id])}</span>"
        )
        for team_id in team_ids
        if team_id in team_lookup
    )


def get_document_origin_label(is_owner, team_ids):
    if is_owner:
        return "Mein Dokument"
    if team_ids:
        return "Geteilt über Team"
    return "Privates Dokument"


def get_user_team_badges_html(user_id, team_state):
    team_lookup = get_team_name_lookup(team_state)
    user_team_ids = get_current_user_team_ids(user_id, team_state)
    if not user_team_ids:
        return "<div>Keine Teams zugeordnet</div>"
    return get_visibility_badges_html(user_team_ids, team_lookup)


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

    def render_file_list(self):
        self.file_team_state = gr.State(value=default_team_state())
        self.file_team_state_storage = gr.Textbox(visible=False, value="")
        self.document_visibility_state = gr.State(value=default_document_visibility_state())
        self.document_visibility_storage = gr.Textbox(visible=False, value="")
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
                    "sichtbarkeit",
                    "herkunft",
                    "size",
                    "tokens",
                    "loader",
                    "date_created",
                ],
                column_widths=[0, 28, 22, 15, 8, 7, 10, 18],
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
                self.current_user_teams = gr.HTML("Keine Teams zugeordnet")
                self.selected_panel = gr.Markdown(self.selected_panel_false)
                self.selected_file_origin = gr.Markdown(visible=False)
                self.selected_file_visibility = gr.HTML(visible=False)
                self.selected_file_owner = gr.Markdown(visible=False)
                self.selected_file_team_ids = gr.State(value=[])
                self.selected_file_owner_id = gr.State(value="")
                self.selected_file_team_select = gr.Dropdown(
                    label="Für Teams freigeben",
                    choices=[],
                    value=[],
                    multiselect=True,
                    allow_custom_value=False,
                    visible=False,
                )
                self.selected_file_save_teams = gr.Button(
                    "Team-Freigabe speichern",
                    variant="primary",
                    visible=False,
                )

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
                "files",
                "date_created",
            ],
            column_widths=[0, 25, 55, 20],
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

        team_state_input = self.file_team_state
        document_state_input = self.document_visibility_state

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
            for event_name in ["onSignIn", "onSignOut"]:
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_file_team_state,
                        "inputs": [self._app.user_id, self.file_team_state_storage],
                        "outputs": [self.file_team_state],
                        "show_progress": "hidden",
                        "js": fetch_file_team_state_js,
                    },
                )
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_document_visibility_state,
                        "inputs": [self._app.user_id, self.document_visibility_storage],
                        "outputs": [self.document_visibility_state],
                        "show_progress": "hidden",
                        "js": fetch_document_visibility_state_js,
                    },
                )
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.list_file,
                        "inputs": [
                            self._app.user_id,
                            self.filter,
                            team_state_input,
                            self.document_visibility_state,
                        ],
                        "outputs": [self.file_list_state, self.file_list],
                        "show_progress": "hidden",
                    },
                )
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.list_group,
                        "inputs": [self._app.user_id, self.file_list_state],
                        "outputs": [self.group_list_state, self.group_list],
                        "show_progress": "hidden",
                    },
                )
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.list_file_names,
                        "inputs": [self.file_list_state],
                        "outputs": [self.group_files],
                        "show_progress": "hidden",
                    },
                )

    def file_selected(self, file_id, user_id=None, team_state=None, document_visibility_state=None):
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
        visibility = {"isOwner": False}
        if file_id is not None:
            Source = self._index._resources["Source"]
            with Session(engine) as session:
                source_row = session.execute(select(Source).where(Source.id == file_id)).first()
            if source_row:
                visibility = get_document_visibility_meta(
                    source_row[0], user_id, team_state, document_visibility_state
                )

        selected_updates = self.get_selected_document_updates(
            file_id,
            user_id,
            team_state,
            document_visibility_state,
        )
        return (
            gr.update(value="".join(chunks), visible=file_id is not None),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None and visibility["isOwner"]),
            gr.update(visible=file_id is not None),
            gr.update(visible=file_id is not None),
            *selected_updates,
        )

    def delete_event(self, file_id):
        file_name = ""
        with Session(engine) as session:
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
            if source:
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

    def download_single_file(self, is_zipped_state, file_id):
        with Session(engine) as session:
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
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
            new_button = gr.DownloadButton(label="Herunterladen", value=None)
        else:
            new_button = gr.DownloadButton(
                label=DOWNLOAD_MESSAGE, value=f"{zip_file_path}.zip"
            )

        return not is_zipped_state, new_button

    def download_single_file_simple(self, is_zipped_state, file_html, file_id):
        with Session(engine) as session:
            source = session.execute(
                select(self._index._resources["Source"]).where(
                    self._index._resources["Source"].id == file_id
                )
            ).first()
        if source:
            target_file_name = Path(source[0].name)

        # create a temporary file with a path to export
        output_file_path = os.path.join(
            flowsettings.KH_ZIP_OUTPUT_DIR, target_file_name.stem + ".html"
        )
        with open(output_file_path, "w") as f:
            f.write(file_html)

        if is_zipped_state:
            new_button = gr.DownloadButton(label="Herunterladen", value=None)
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

    def delete_all_files(self, file_list):
        for file_id in file_list.id.values:
            self.delete_event(file_id)

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
                                value="Bitte warte, bis die Indexierung "
                                "abgeschlossen ist, bevor du deine Frage hinzufügst."
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
                            fn=lambda: gr.update(value="Indexierung abgeschlossen."),
                            outputs=self._app.chat_page.quick_file_upload_status,
                        )
                        .then(
                            fn=self.list_file,
                            inputs=[
                                self._app.user_id,
                                self.filter,
                                self.file_team_state,
                                self.document_visibility_state,
                            ],
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
                            value="Bitte warte, bis die Indexierung "
                            "abgeschlossen ist, bevor du deine Frage hinzufügst."
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
                    fn=lambda: gr.update(value="Indexierung abgeschlossen."),
                    outputs=self._app.chat_page.quick_file_upload_status,
                )

                if not KH_DEMO_MODE:
                    quickURLUploadedEvent = quickURLUploadedEvent.then(
                        fn=self.list_file,
                        inputs=[
                            self._app.user_id,
                            self.filter,
                            self.file_team_state,
                            self.document_visibility_state,
                        ],
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

        if self._app.f_user_management:
            source_team_state = self._app.resources_page.user_management.team_state
            source_team_state.change(
                fn=lambda team_state: team_state,
                inputs=[source_team_state],
                outputs=[self.file_team_state],
                show_progress="hidden",
            ).then(
                fn=self.list_file,
                inputs=[
                    self._app.user_id,
                    self.filter,
                    self.file_team_state,
                    self.document_visibility_state,
                ],
                outputs=[self.file_list_state, self.file_list],
                show_progress="hidden",
            ).then(
                fn=self.file_selected,
                inputs=[
                    self.selected_file_id,
                    self._app.user_id,
                    self.file_team_state,
                    self.document_visibility_state,
                ],
                outputs=[
                    self.chunks,
                    self.deselect_button,
                    self.delete_button,
                    self.download_single_button,
                    self.chat_button,
                    self.current_user_teams,
                    self.selected_file_origin,
                    self.selected_file_visibility,
                    self.selected_file_owner,
                    self.selected_file_team_ids,
                    self.selected_file_owner_id,
                    self.selected_file_team_select,
                    self.selected_file_save_teams,
                ],
                show_progress="hidden",
            )

        onDeleted = (
            self.delete_button.click(
                fn=self.delete_event,
                inputs=[self.selected_file_id],
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
                inputs=[
                    self._app.user_id,
                    self.filter,
                    self.file_team_state,
                    self.document_visibility_state,
                ],
                outputs=[self.file_list_state, self.file_list],
            )
            .then(
                fn=self.file_selected,
                inputs=[
                    self.selected_file_id,
                    self._app.user_id,
                    self.file_team_state,
                    self.document_visibility_state,
                ],
                outputs=[
                    self.chunks,
                    self.deselect_button,
                    self.delete_button,
                    self.download_single_button,
                    self.chat_button,
                    self.current_user_teams,
                    self.selected_file_origin,
                    self.selected_file_visibility,
                    self.selected_file_owner,
                    self.selected_file_team_ids,
                    self.selected_file_owner_id,
                    self.selected_file_team_select,
                    self.selected_file_save_teams,
                ],
                show_progress="hidden",
            )
        )
        for event in self._app.get_event(f"onFileIndex{self._index.id}Changed"):
            onDeleted = onDeleted.then(**event)

        self.deselect_button.click(
            fn=lambda: (None, self.selected_panel_false),
            inputs=[],
            outputs=[self.selected_file_id, self.selected_panel],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[
                self.selected_file_id,
                self._app.user_id,
                self.file_team_state,
                self.document_visibility_state,
            ],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
                self.current_user_teams,
                self.selected_file_origin,
                self.selected_file_visibility,
                self.selected_file_owner,
                self.selected_file_team_ids,
                self.selected_file_owner_id,
                self.selected_file_team_select,
                self.selected_file_save_teams,
            ],
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
            inputs=[self.file_list],
            outputs=[],
            show_progress="hidden",
        ).then(
            fn=self.list_file,
            inputs=[
                self._app.user_id,
                self.filter,
                self.file_team_state,
                self.document_visibility_state,
            ],
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
                inputs=[self.is_zipped_state, self.selected_file_id],
                outputs=[self.is_zipped_state, self.download_single_button],
                show_progress="hidden",
            )
        else:
            self.download_single_button.click(
                fn=self.download_single_file_simple,
                inputs=[self.is_zipped_state, self.chunks, self.selected_file_id],
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
            inputs=[
                self._app.user_id,
                self.filter,
                self.file_team_state,
                self.document_visibility_state,
            ],
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

        self.file_list.select(
            fn=self.interact_file_list,
            inputs=[self.file_list],
            outputs=[self.selected_file_id, self.selected_panel],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[
                self.selected_file_id,
                self._app.user_id,
                self.file_team_state,
                self.document_visibility_state,
            ],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
                self.current_user_teams,
                self.selected_file_origin,
                self.selected_file_visibility,
                self.selected_file_owner,
                self.selected_file_team_ids,
                self.selected_file_owner_id,
                self.selected_file_team_select,
                self.selected_file_save_teams,
            ],
            show_progress="hidden",
        )

        self.group_list.select(
            fn=self.interact_group_list,
            inputs=[self.group_list_state],
            outputs=[
                self.group_label,
                self.selected_group_id,
                self.group_name,
                self.group_files,
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
            inputs=[
                self._app.user_id,
                self.filter,
                self.file_team_state,
                self.document_visibility_state,
            ],
            outputs=[self.file_list_state, self.file_list],
            show_progress="hidden",
        )

        self.selected_file_save_teams.click(
            fn=self.save_document_teams,
            inputs=[
                self.selected_file_id,
                self.selected_file_team_select,
                self._app.user_id,
                self.file_team_state,
                self.document_visibility_state,
            ],
            outputs=[self.document_visibility_state],
            show_progress="hidden",
        ).then(
            fn=None,
            inputs=[self.document_visibility_state],
            outputs=[self.document_visibility_storage],
            js=save_document_visibility_state_js,
        ).then(
            fn=self.list_file,
            inputs=[
                self._app.user_id,
                self.filter,
                self.file_team_state,
                self.document_visibility_state,
            ],
            outputs=[self.file_list_state, self.file_list],
            show_progress="hidden",
        ).then(
            fn=self.file_selected,
            inputs=[
                self.selected_file_id,
                self._app.user_id,
                self.file_team_state,
                self.document_visibility_state,
            ],
            outputs=[
                self.chunks,
                self.deselect_button,
                self.delete_button,
                self.download_single_button,
                self.chat_button,
                self.current_user_teams,
                self.selected_file_origin,
                self.selected_file_visibility,
                self.selected_file_owner,
                self.selected_file_team_ids,
                self.selected_file_owner_id,
                self.selected_file_team_select,
                self.selected_file_save_teams,
            ],
            show_progress="hidden",
        )

        self.group_add_button.click(
            fn=lambda: [
                gr.update(visible=False),
                gr.update(value="### Add new group"),
                gr.update(visible=True),
                gr.update(value=""),
                gr.update(value=[]),
                None,
            ],
            outputs=[
                self.group_add_button,
                self.group_label,
                self._group_info_panel,
                self.group_name,
                self.group_files,
                self.selected_group_id,
            ],
        )

        self.group_chat_button.click(
            fn=self.set_group_id_selector,
            inputs=[self.selected_group_id],
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
                inputs=[self.selected_group_id],
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
            self.load_file_team_state,
            inputs=[self._app.user_id, self.file_team_state_storage],
            outputs=[self.file_team_state],
            show_progress="hidden",
            js=fetch_file_team_state_js,
        ).then(
            self.load_document_visibility_state,
            inputs=[self._app.user_id, self.document_visibility_storage],
            outputs=[self.document_visibility_state],
            show_progress="hidden",
            js=fetch_document_visibility_state_js,
        ).then(
            self.list_file,
            inputs=[
                self._app.user_id,
                self.filter,
                self.file_team_state,
                self.document_visibility_state,
            ],
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
        self, files, urls, reindex: bool, settings, user_id
    ) -> Generator[tuple[str, str], None, None]:
        """Upload and index the files

        Args:
            files: the list of files to be uploaded
            urls: list of web URLs to be indexed
            reindex: whether to reindex the files
            selected_files: the list of files already selected
            settings: the settings of the app
        """
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
        indexing_pipeline = self._index.get_indexing_pipeline(settings, user_id)

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
            yield "\n".join(outputs), "\n".join(debugs)
            return

        n_successes = len([_ for _ in results if _])
        if n_successes:
            gr.Info(f"Successfully index {n_successes} files")
        n_errors = len([_ for _ in errors if _])
        if n_errors:
            gr.Warning(f"Have errors for {n_errors} files")

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
        exist_ids = []
        to_process_files = []
        for str_file_path in files:
            file_path = Path(str(str_file_path))
            exist_id = (
                self._index.get_indexing_pipeline(settings, user_id)
                .route(file_path)
                .get_id_if_exists(file_path)
            )
            if exist_id:
                exist_ids.append(exist_id)
            else:
                to_process_files.append(str_file_path)

        returned_ids = []
        settings = deepcopy(settings)
        settings[f"index.options.{self._index.id}.reader_mode"] = "default"
        settings[f"index.options.{self._index.id}.quick_index_mode"] = True
        if to_process_files:
            _iter = self.index_fn(to_process_files, [], reindex, settings, user_id)
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
                exist_id = (
                    self._index.get_indexing_pipeline(settings, user_id)
                    .route(file_path)
                    .get_id_if_exists(file_path)
                )
                if exist_id:
                    exist_ids.append(exist_id)
                else:
                    to_process_files.append(str_file_path)

            returned_ids = []
            if to_process_files:
                _iter = self.index_fn(to_process_files, [], reindex, settings, user_id)
                try:
                    while next(_iter):
                        pass
                except StopIteration as e:
                    returned_ids = e.value

            returned_ids = exist_ids + returned_ids
        else:
            if urls:
                _iter = self.index_fn([], urls, reindex, settings, user_id)
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

        yield from self.index_fn(files, [], reindex, settings, user_id)

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

    def get_visible_sources(self, user_id, team_state, document_visibility_state):
        if user_id is None:
            return []

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            statement = select(Source)
            if KH_DEMO_MODE:
                statement = statement.limit(MAX_FILE_COUNT)
            rows = session.execute(statement).all()

        visible_sources = []
        for (source,) in rows:
            visibility = get_document_visibility_meta(
                source,
                user_id,
                team_state,
                document_visibility_state,
            )
            if visibility["isVisible"]:
                visible_sources.append((source, visibility))

        return visible_sources

    def list_file(self, user_id, name_pattern="", team_state=None, document_visibility_state=None):
        if user_id is None:
            # not signed in
            return [], pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "sichtbarkeit": "-",
                        "herkunft": "-",
                        "size": "-",
                        "tokens": "-",
                        "loader": "-",
                        "date_created": "-",
                    }
                ]
            )

        team_lookup = get_team_name_lookup(team_state)
        visible_sources = self.get_visible_sources(
            user_id,
            team_state,
            document_visibility_state,
        )
        results = []
        for source, visibility in visible_sources:
            if name_pattern and name_pattern.lower() not in source.name.lower():
                continue
            results.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "ownerId": visibility["ownerId"],
                    "teamIds": visibility["teamIds"],
                    "sichtbarkeit": get_visibility_label(
                        visibility["teamIds"], team_lookup
                    ),
                    "herkunft": get_document_origin_label(
                        visibility["isOwner"], visibility["teamIds"]
                    ),
                    "size": self.format_size_human_readable(source.size),
                    "tokens": self.format_size_human_readable(
                        source.note.get("tokens", "-"), suffix=""
                    ),
                    "loader": source.note.get("loader", "-"),
                    "date_created": source.date_created.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        if results:
            file_list = pd.DataFrame.from_records(
                [
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "sichtbarkeit": item["sichtbarkeit"],
                        "herkunft": item["herkunft"],
                        "size": item["size"],
                        "tokens": item["tokens"],
                        "loader": item["loader"],
                        "date_created": item["date_created"],
                    }
                    for item in results
                ]
            )
        else:
            file_list = pd.DataFrame.from_records(
                [
                    {
                        "id": "-",
                        "name": "-",
                        "sichtbarkeit": "-",
                        "herkunft": "-",
                        "size": "-",
                        "tokens": "-",
                        "loader": "-",
                        "date_created": "-",
                    }
                ]
            )

        return results, file_list

    def get_selected_document_updates(
        self,
        file_id,
        user_id,
        team_state,
        document_visibility_state,
    ):
        team_lookup = get_team_name_lookup(team_state)
        user_team_ids = get_current_user_team_ids(user_id, team_state)
        user_team_choices = [
            (team_name, team_id)
            for team_name, team_id in get_team_choices(normalize_team_state(team_state))
            if team_id in set(user_team_ids)
        ]
        if file_id is None:
            hidden_dropdown = gr.update(
                visible=False,
                choices=user_team_choices,
                value=[],
            )
            return (
                gr.update(value=f"<div><strong>Meine Teams:</strong> {get_user_team_badges_html(user_id, team_state)}</div>"),
                gr.update(visible=False, value=""),
                gr.update(visible=False, value=""),
                gr.update(visible=False, value=""),
                [],
                "",
                hidden_dropdown,
                gr.update(visible=False),
            )

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            source_row = session.execute(select(Source).where(Source.id == file_id)).first()

        if not source_row:
            return self.get_selected_document_updates(
                None, user_id, team_state, document_visibility_state
            )

        source = source_row[0]
        visibility = get_document_visibility_meta(
            source, user_id, team_state, document_visibility_state
        )
        editable = visibility["isOwner"]
        owner_value = visibility["ownerId"] or "-"
        selected_team_ids = visibility["teamIds"]

        return (
            gr.update(value=f"<div><strong>Meine Teams:</strong> {get_user_team_badges_html(user_id, team_state)}</div>"),
            gr.update(
                visible=True,
                value=f"**Status:** {get_document_origin_label(editable, selected_team_ids)}",
            ),
            gr.update(
                visible=True,
                value=get_visibility_badges_html(selected_team_ids, team_lookup),
            ),
            gr.update(visible=True, value=f"**Besitzer-ID:** `{owner_value}`"),
            selected_team_ids,
            owner_value,
            gr.update(
                visible=editable,
                choices=user_team_choices,
                value=[team_id for team_id in selected_team_ids if team_id in set(user_team_ids)],
            ),
            gr.update(visible=editable),
        )

    def save_document_teams(
        self,
        file_id,
        selected_team_ids,
        user_id,
        team_state,
        document_visibility_state,
    ):
        document_visibility_state = normalize_document_visibility_state(
            document_visibility_state
        )
        if not file_id:
            gr.Warning("Keine Datei ausgewählt")
            return document_visibility_state

        Source = self._index._resources["Source"]
        with Session(engine) as session:
            source_row = session.execute(select(Source).where(Source.id == file_id)).first()

        if not source_row:
            gr.Warning("Datei nicht gefunden")
            return document_visibility_state

        source = source_row[0]
        visibility = get_document_visibility_meta(
            source, user_id, team_state, document_visibility_state
        )
        if not visibility["isOwner"]:
            gr.Warning("Nur der Besitzer kann die Team-Freigabe ändern")
            return document_visibility_state

        valid_team_ids = set(get_current_user_team_ids(user_id, team_state))
        filtered_team_ids = [
            team_id for team_id in (selected_team_ids or []) if team_id in valid_team_ids
        ]
        document_visibility_state["documents"][file_id] = {
            "ownerId": visibility["ownerId"],
            "teamIds": filtered_team_ids,
        }
        gr.Info("Team-Freigabe gespeichert")
        return document_visibility_state

    def load_document_visibility_state(self, user_id, document_visibility_storage):
        state = default_document_visibility_state()
        if document_visibility_storage:
            try:
                state = normalize_document_visibility_state(
                    json.loads(document_visibility_storage)
                )
            except Exception:
                state = default_document_visibility_state()
        return state

    def load_file_team_state(self, user_id, file_team_state_storage):
        team_state = default_team_state()
        if file_team_state_storage:
            try:
                team_state = normalize_team_state(json.loads(file_team_state_storage))
            except Exception:
                team_state = default_team_state()
        return team_state

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
                        "files": "-",
                        "date_created": "-",
                    }
                ]
            )

        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            statement = select(FileGroup)
            if self._index.config.get("private", False):
                statement = statement.where(FileGroup.user == user_id)

            results = [
                {
                    "id": each[0].id,
                    "name": each[0].name,
                    "files": each[0].data.get("files", []),
                    "date_created": each[0].date_created.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for each in session.execute(statement).all()
            ]

        if results:
            formated_results = deepcopy(results)
            for item in formated_results:
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
                        "files": "-",
                        "date_created": "-",
                    }
                ]
            )

        return results, group_list

    def set_group_id_selector(self, selected_group_id):
        FileGroup = self._index._resources["FileGroup"]

        # check if group_name exist
        with Session(engine) as session:
            current_group = (
                session.query(FileGroup).filter_by(id=selected_group_id).first()
            )

        file_ids = [json.dumps(current_group.data["files"])]
        return [file_ids, "select", gr.Tabs(selected="chat-tab")]

    def save_group(self, group_id, group_name, group_files, user_id):
        FileGroup = self._index._resources["FileGroup"]
        current_group = None

        # check if group_name exist
        with Session(engine) as session:
            if group_id:
                current_group = session.query(FileGroup).filter_by(id=group_id).first()
                # update current group with new info
                current_group.name = group_name
                current_group.data["files"] = group_files  # Update the files
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
                    data={"files": group_files},  # type: ignore
                    user=user_id,
                )
                session.add(current_group)
                session.commit()

            group_id = current_group.id

        gr.Info(f"Group {group_name} has been saved")
        return group_id

    def delete_group(self, group_id):
        if not group_id:
            raise gr.Error("No group is selected")

        FileGroup = self._index._resources["FileGroup"]
        with Session(engine) as session:
            group = session.execute(
                select(FileGroup).where(FileGroup.id == group_id)
            ).first()
            if group:
                item = group[0]
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

    def interact_group_list(self, list_groups, ev: gr.SelectData):
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
            return "disabled", [], -1, []
        return "disabled", [], 1, []

    def on_building_ui(self):
        default_mode, default_selector, user_id, default_team_filter = self.default()

        self.mode = gr.Radio(
            value=default_mode,
            choices=[
                ("Alle durchsuchen", "all"),
                ("In Datei(en) suchen", "select"),
                ("In Teams suchen", "teams"),
            ],
            container=False,
        )
        self.selector = gr.Dropdown(
            label="Dateien",
            value=default_selector,
            choices=[],
            multiselect=True,
            container=False,
            interactive=True,
            visible=False,
        )
        self.selector_user_id = gr.State(value=user_id)
        self.team_selector = gr.Dropdown(
            label="Teams",
            value=default_team_filter,
            choices=[],
            multiselect=True,
            container=False,
            interactive=True,
            visible=False,
        )
        self.selector_team_state = gr.State(value=default_team_state())
        self.selector_team_state_storage = gr.Textbox(visible=False, value="")
        self.selector_document_state = gr.State(value=default_document_visibility_state())
        self.selector_document_state_storage = gr.Textbox(visible=False, value="")
        self.selector_choices = gr.JSON(
            value=[],
            visible=False,
        )

    def on_register_events(self):
        self.mode.change(
            fn=lambda mode, user_id: (
                gr.update(visible=mode == "select"),
                user_id,
                gr.update(visible=mode == "teams"),
            ),
            inputs=[self.mode, self._app.user_id],
            outputs=[self.selector, self.selector_user_id, self.team_selector],
        )
        # attach special event for the first index
        if self._index.id == 1:
            self.selector_choices.change(
                fn=None,
                inputs=[self.selector_choices],
                js=update_file_list_js,
                show_progress="hidden",
            )
        if self._app.f_user_management:
            source_team_state = self._app.resources_page.user_management.team_state
            source_team_state.change(
                fn=lambda team_state: team_state,
                inputs=[source_team_state],
                outputs=[self.selector_team_state],
                show_progress="hidden",
            ).then(
                fn=self.load_files,
                inputs=[
                    self.selector,
                    self._app.user_id,
                    self.selector_team_state,
                    self.selector_document_state,
                    self.team_selector,
                ],
                outputs=[self.selector, self.selector_choices, self.team_selector],
                show_progress="hidden",
            )

    def as_gradio_component(self):
        return [
            self.mode,
            self.selector,
            self.selector_user_id,
            self.team_selector,
            self.selector_team_state,
            self.selector_document_state,
        ]

    def get_selected_ids(self, components):
        mode, selected, user_id = components[0], components[1], components[2]
        team_filter_ids = components[3] if len(components) > 3 else []
        team_state = components[4] if len(components) > 4 else None
        document_visibility_state = (
            components[5] if len(components) > 5 else default_document_visibility_state()
        )
        if user_id is None:
            return []

        if mode == "disabled":
            return []
        elif mode == "select":
            return selected

        index_page = self._index.get_index_page_ui()
        visible_sources = index_page.get_visible_sources(
            user_id, team_state, document_visibility_state
        )
        file_ids = []
        for source, visibility in visible_sources:
            if mode == "teams" and not visibility["isOwner"]:
                effective_filters = team_filter_ids or visibility["userTeamIds"]
                if not set(visibility["teamIds"]).intersection(effective_filters):
                    continue
            file_ids.append(source.id)

        return file_ids

    def load_files(
        self,
        selected_files,
        user_id,
        team_state,
        document_visibility_state,
        selected_team_filters,
    ):
        options: list = []
        available_ids = []
        team_state = normalize_team_state(team_state)
        user_team_ids = get_current_user_team_ids(user_id, team_state)
        team_choices = get_team_choices(team_state)
        selected_team_filters = [
            team_id for team_id in (selected_team_filters or []) if team_id in {id_ for _, id_ in team_choices}
        ]
        if not selected_team_filters:
            selected_team_filters = user_team_ids
        if user_id is None:
            # not signed in
            return (
                gr.update(value=selected_files, choices=options),
                options,
                gr.update(choices=[], value=[]),
            )

        index_page = self._index.get_index_page_ui()
        visible_sources = index_page.get_visible_sources(
            user_id, team_state, document_visibility_state
        )
        for source, _ in visible_sources:
            available_ids.append(source.id)
            options.append((source.name, source.id))

        with Session(engine) as session:
            # get group list from FileGroup table
            FileGroup = self._index._resources["FileGroup"]
            statement = select(FileGroup)
            if self._index.config.get("private", False):
                statement = statement.where(FileGroup.user == user_id)
            results = session.execute(statement).all()
            for result in results:
                item = result[0]
                options.append(
                    (f"group: '{item.name}'", json.dumps(item.data.get("files", [])))
                )

        if selected_files:
            available_ids_set = set(available_ids)
            selected_files = [
                each for each in selected_files if each in available_ids_set
            ]

        return (
            gr.update(value=selected_files, choices=options),
            options,
            gr.update(choices=team_choices, value=selected_team_filters),
        )

    def load_selector_access_state(
        self, user_id, selector_team_state_storage, selector_document_state_storage
    ):
        team_state = default_team_state()
        if selector_team_state_storage:
            try:
                team_state = normalize_team_state(json.loads(selector_team_state_storage))
            except Exception:
                team_state = default_team_state()

        document_state = default_document_visibility_state()
        if selector_document_state_storage:
            try:
                document_state = normalize_document_visibility_state(
                    json.loads(selector_document_state_storage)
                )
            except Exception:
                document_state = default_document_visibility_state()

        return team_state, document_state

    def _on_app_created(self):
        self._app.app.load(
            self.load_selector_access_state,
            inputs=[
                self._app.user_id,
                self.selector_team_state_storage,
                self.selector_document_state_storage,
            ],
            outputs=[self.selector_team_state, self.selector_document_state],
            show_progress="hidden",
            js=fetch_selector_access_state_js,
        ).then(
            self.load_files,
            inputs=[
                self.selector,
                self._app.user_id,
                self.selector_team_state,
                self.selector_document_state,
                self.team_selector,
            ],
            outputs=[self.selector, self.selector_choices, self.team_selector],
        )

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name=f"onFileIndex{self._index.id}Changed",
            definition={
                "fn": self.load_files,
                "inputs": [
                    self.selector,
                    self._app.user_id,
                    self.selector_team_state,
                    self.selector_document_state,
                    self.team_selector,
                ],
                "outputs": [self.selector, self.selector_choices, self.team_selector],
                "show_progress": "hidden",
            },
        )
        if self._app.f_user_management:
            for event_name in ["onSignIn", "onSignOut"]:
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_selector_access_state,
                        "inputs": [
                            self._app.user_id,
                            self.selector_team_state_storage,
                            self.selector_document_state_storage,
                        ],
                        "outputs": [
                            self.selector_team_state,
                            self.selector_document_state,
                        ],
                        "show_progress": "hidden",
                        "js": fetch_selector_access_state_js,
                    },
                )
                self._app.subscribe_event(
                    name=event_name,
                    definition={
                        "fn": self.load_files,
                        "inputs": [
                            self.selector,
                            self._app.user_id,
                            self.selector_team_state,
                            self.selector_document_state,
                            self.team_selector,
                        ],
                        "outputs": [self.selector, self.selector_choices, self.team_selector],
                        "show_progress": "hidden",
                    },
                )
