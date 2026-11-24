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

HELP_IMAGE_LIGHTBOX = """
<style>
#help-lightbox {
    display: none;
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: rgba(0,0,0,0.85);
    z-index: 9999;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}
#help-lightbox-close {
    position: absolute;
    top: 16px; right: 24px;
    color: #fff;
    font-size: 32px;
    font-weight: bold;
    cursor: pointer;
    z-index: 10001;
    line-height: 1;
    user-select: none;
}
#help-lightbox-close:hover {
    color: #f97316;
}
#help-lightbox-hint {
    color: #aaa;
    font-size: 14px;
    margin-bottom: 12px;
    user-select: none;
}
#help-lightbox-img {
    max-width: 90vw;
    max-height: 80vh;
    object-fit: contain;
    border-radius: 8px;
    box-shadow: 0 0 40px rgba(0,0,0,0.5);
    cursor: default;
}
</style>
<div id="help-lightbox">
    <span id="help-lightbox-close" title="Schließen">&times;</span>
    <span id="help-lightbox-hint">Zum Schließen ESC oder X drücken</span>
    <img id="help-lightbox-img" src="">
</div>
"""

HELP_ACCORDION_CSS = """
<style>
/* Hilfe-Akkordeon-Titel fett + orange beim Öffnen */
.gr-accordion > .label-wrap > span {
    font-weight: 700 !important;
    font-size: 15px !important;
}
.gr-accordion > .label-wrap.open > span {
    color: #f97316 !important;
}
</style>
"""

HELP_IMAGE_LIGHTBOX_JS = """
<script>
(function() {
    function initLightbox() {
        var lb = document.getElementById('help-lightbox');
        var lbImg = document.getElementById('help-lightbox-img');
        var lbClose = document.getElementById('help-lightbox-close');
        if (!lb || !lbImg) return false;

        function hide() {
            lb.style.display = 'none';
            lbImg.src = '';
        }

        lb.addEventListener('click', function(e) {
            if (e.target === lb) hide();
        });
        if (lbClose) lbClose.addEventListener('click', hide);
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && lb.style.display === 'flex') hide();
        });
        return true;
    }

    // Wait for lightbox DOM
    var pollLb = setInterval(function() {
        if (initLightbox()) clearInterval(pollLb);
    }, 200);

    // Bind click on ALL images — simple and reliable
    document.addEventListener('click', function(e) {
        var img = e.target.closest ? e.target.closest('img') : null;
        if (!img) return;
        if (img._helpLightboxBound) return;
        img._helpLightboxBound = true;
        img.style.cursor = 'zoom-in';

        var lb = document.getElementById('help-lightbox');
        var lbImg = document.getElementById('help-lightbox-img');
        if (lb && lbImg) {
            e.stopPropagation();
            e.preventDefault();
            lbImg.src = img.src;
            lb.style.display = 'flex';
        }
    }, true);
})();
</script>"""


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
        self.schnellstart_md = self._load_local_doc("schnellstart.md")
        self.chat_suche_md = self._load_local_doc("chat_suche.md")
        self.benutzer_teams_md = self._load_local_doc("benutzer_teams.md")
        self.dokumente_mehr_md = self._load_local_doc("dokumente_mehr.md")
        self.faq_fehler_md = self._load_local_doc("faq_fehler.md")
        self.user_guide_md = self._load_local_doc("user_doku.md")
        self.key_user_guide_md = self._load_local_doc("keyuser_doku.md")
        self.admin_guide_md = self._load_local_doc("admin_doku.md")

        gr.HTML(HELP_IMAGE_LIGHTBOX + HELP_ACCORDION_CSS)

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

        with gr.Accordion("Schnellstart", open=True):
            self.schnellstart_guide = gr.Markdown()

        with gr.Accordion("Chat & Suche", open=False):
            self.chat_suche_guide = gr.Markdown()

        with gr.Accordion("Benutzer & Teams", open=False):
            self.benutzer_teams_guide = gr.Markdown()

        with gr.Accordion("Dokumente & System", open=False):
            self.dokumente_mehr_guide = gr.Markdown()

        with gr.Accordion("FAQ & Fehler", open=False):
            self.faq_fehler_guide = gr.Markdown()

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
                    self.schnellstart_guide,
                    self.chat_suche_guide,
                    self.benutzer_teams_guide,
                    self.dokumente_mehr_guide,
                    self.faq_fehler_guide,
                    self.roles_guide,
                    self.version_history_accordion,
                ],
                show_progress="hidden",
            )
            self._app.user_id.change(
                self._build_help_content,
                inputs=[self._app.user_id],
                outputs=[
                    self.schnellstart_guide,
                    self.chat_suche_guide,
                    self.benutzer_teams_guide,
                    self.dokumente_mehr_guide,
                    self.faq_fehler_guide,
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
                    self.schnellstart_guide,
                    self.chat_suche_guide,
                    self.benutzer_teams_guide,
                    self.dokumente_mehr_guide,
                    self.faq_fehler_guide,
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
        schnellstart = self.schnellstart_md
        chat_suche = self.chat_suche_md
        benutzer_teams = self.benutzer_teams_md
        dokumente_mehr = self.dokumente_mehr_md
        faq_fehler = self.faq_fehler_md
        guide_user = self.user_guide_md
        guide_key_user = self.key_user_guide_md
        guide_admin = self.admin_guide_md
        roles_guide = "\n\n---\n\n".join(
            section for section in [guide_user, guide_key_user, guide_admin] if section
        )

        if not self._app.f_user_management:
            return schnellstart, chat_suche, benutzer_teams, dokumente_mehr, faq_fehler, roles_guide, gr.update(visible=False)

        role = "user"
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if actor:
                if actor.is_admin:
                    role = "admin"
                elif actor.is_key_user:
                    role = "key_user"

        if role == "admin":
            return schnellstart, chat_suche, benutzer_teams, dokumente_mehr, faq_fehler, roles_guide, gr.update(visible=True)

        if role == "key_user":
            return schnellstart, chat_suche, benutzer_teams, dokumente_mehr, faq_fehler, roles_guide, gr.update(visible=False)

        return schnellstart, chat_suche, benutzer_teams, dokumente_mehr, faq_fehler, roles_guide, gr.update(visible=False)
