import os
from pathlib import Path
import re
from urllib.parse import quote

import gradio as gr
import requests
from decouple import config
from ktem.authz import get_access_context
from ktem.db.engine import engine
from sqlmodel import Session
from theflow.settings import settings

KH_DEMO_MODE = getattr(settings, "KH_DEMO_MODE", False)
HF_SPACE_URL = config("HF_SPACE_URL", default="")
BASE_PATH = os.environ.get("GR_FILE_ROOT_PATH", "")


def get_remote_doc(url: str) -> str:
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"Failed to fetch document from {url}: {e}")
        return ""


class HelpPage:
    def __init__(
        self,
        app,
        doc_dir: str = settings.KH_DOC_DIR,
        remote_content_url: str = "https://raw.githubusercontent.com/Cinnamon/kotaemon",
        app_version: str | None = settings.KH_APP_VERSION,
        changelogs_cache_dir: str
        | Path = (Path(settings.KH_APP_DATA_DIR) / "changelogs"),
    ):
        self._app = app
        self.doc_dir = Path(doc_dir)
        self.remote_content_url = remote_content_url
        self.app_version = app_version
        self.changelogs_cache_dir = Path(changelogs_cache_dir)
        self.changelogs_cache_dir.mkdir(parents=True, exist_ok=True)
        self.general_guide_md = self._load_local_doc("allgemeine_doku.md")
        self.user_guide_md = self._load_local_doc("user_doku.md")
        self.key_user_guide_md = self._load_local_doc("keyuser_doku.md")
        self.admin_guide_md = self._load_local_doc("admin_doku.md")

        about_md_dir = self.doc_dir / "about.md"
        if about_md_dir.exists():
            with (self.doc_dir / "about.md").open(encoding="utf-8") as fi:
                about_md = fi.read()
        else:
            about_md = get_remote_doc(
                f"{self.remote_content_url}/v{self.app_version}/docs/about.md"
            )
        if about_md:
            about_md = about_md.replace("Kotaemon", "Kaidoku")
            about_md = about_md.replace("open-source tool", "quelloffenes Werkzeug")
            about_md = about_md.replace("open source tool", "quelloffenes Werkzeug")
            about_md = about_md.replace(
                "open-source",
                "quelloffenes",
            )
            about_md = about_md.replace(
                "Open-source",
                "Quelloffenes",
            )
            with gr.Accordion("Über Kaidoku"):
                if self.app_version:
                    about_md = f"Version: {self.app_version}\n\n{about_md}"
                gr.Markdown(about_md)

        with gr.Accordion("Anleitung", open=True):
            self.quick_guide = gr.Markdown()

        with gr.Accordion("Rollen", open=False):
            self.roles_guide = gr.Markdown()

        if KH_DEMO_MODE:
            with gr.Accordion("Eigenen Space erstellen"):
                gr.Markdown(
                    "Dies ist eine Demo mit eingeschränktem Funktionsumfang. "
                    "Nutze die Schaltfläche **Space erstellen**, um kaidoku "
                    "mit allen Funktionen in deinem eigenen Space zu installieren."
                )
                gr.Button(
                    value="Eigenen Space erstellen",
                    link=HF_SPACE_URL,
                    variant="primary",
                    size="lg",
                )

        with gr.Accordion(
            "Versionsverlauf", open=False, visible=False
        ) as self.version_history_accordion:
            gr.Markdown(
                "Detaillierte Informationen zu den einzelnen Updates und "
                "Änderungen sind auf GitHub dokumentiert. "
                "Link dazu: https://github.com/blizZark89/kaidoku/releases"
            )

        if self._app.f_user_management:
            self._app.app.load(
                self._build_help_content,
                inputs=[self._app.user_id],
                outputs=[
                    self.quick_guide,
                    self.roles_guide,
                    self.version_history_accordion,
                ],
                show_progress="hidden",
            )
            self._app.user_id.change(
                self._build_help_content,
                inputs=[self._app.user_id],
                outputs=[
                    self.quick_guide,
                    self.roles_guide,
                    self.version_history_accordion,
                ],
                show_progress="hidden",
            )
        else:
            self._app.app.load(
                self._build_help_content,
                inputs=[],
                outputs=[
                    self.quick_guide,
                    self.roles_guide,
                    self.version_history_accordion,
                ],
                show_progress="hidden",
            )

    def _load_local_doc(self, filename: str) -> str:
        path = self.doc_dir / filename
        if not path.exists():
            return ""
        with path.open(encoding="utf-8") as fi:
            content = fi.read()
        return self._rewrite_local_image_paths(content)

    def _rewrite_local_image_paths(self, content: str) -> str:
        def resolve_doc_image(rel_path: str) -> str:
            rel_path = rel_path.replace("\\", "/").strip()
            abs_path = (self.doc_dir / rel_path).resolve()
            quoted_path = quote(str(abs_path).replace("\\", "/"), safe="/:")
            return f"{BASE_PATH}/file={quoted_path}"

        content = re.sub(
            r'(<img\b[^>]*\bsrc=")(images/[^"]+)(")',
            lambda match: f'{match.group(1)}{resolve_doc_image(match.group(2))}{match.group(3)}',
            content,
        )
        content = re.sub(
            r'(!\[[^\]]*\]\()(images/[^)]+)(\))',
            lambda match: f'{match.group(1)}{resolve_doc_image(match.group(2))}{match.group(3)}',
            content,
        )
        return content

    def _build_help_content(self, user_id=None):
        guide_general = self.general_guide_md
        guide_user = self.user_guide_md
        guide_key_user = self.key_user_guide_md
        guide_admin = self.admin_guide_md
        quick_guide = guide_general
        roles_guide = "\n\n---\n\n".join(
            section for section in [guide_user, guide_key_user, guide_admin] if section
        )

        if not self._app.f_user_management:
            return quick_guide, roles_guide, gr.update(visible=False)

        role = "user"
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if actor:
                if actor.is_admin:
                    role = "admin"
                elif actor.is_key_user:
                    role = "key_user"

        if role == "admin":
            return quick_guide, roles_guide, gr.update(visible=True)

        if role == "key_user":
            return quick_guide, roles_guide, gr.update(visible=False)

        return quick_guide, roles_guide, gr.update(visible=False)
