from importlib.metadata import version
from pathlib import Path

import gradio as gr
import requests
from decouple import config
from ktem.authz import get_access_context
from ktem.db.engine import engine
from sqlmodel import Session
from theflow.settings import settings

KH_DEMO_MODE = getattr(settings, "KH_DEMO_MODE", False)
HF_SPACE_URL = config("HF_SPACE_URL", default="")


def get_remote_doc(url: str) -> str:
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"Failed to fetch document from {url}: {e}")
        return ""


def download_changelogs(release_url: str) -> str:
    try:
        res = requests.get(release_url).json()
        changelogs = res.get("body", "")
        return changelogs
    except Exception as e:
        print(f"Failed to fetch changelogs from {release_url}: {e}")
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

        if self.app_version:
            changelogs = ""
            if (self.changelogs_cache_dir / f"{version}.md").exists():
                with open(self.changelogs_cache_dir / f"{version}.md", "r") as fi:
                    changelogs = fi.read()
            else:
                release_url_base = "https://api.github.com/repos/Cinnamon/kotaemon/releases"
                changelogs = download_changelogs(
                    release_url=f"{release_url_base}/tags/v{self.app_version}"
                )
                if not self.changelogs_cache_dir.exists():
                    self.changelogs_cache_dir.mkdir(parents=True, exist_ok=True)
                with open(self.changelogs_cache_dir / f"{self.app_version}.md", "w") as fi:
                    fi.write(changelogs)

            if changelogs:
                with gr.Accordion(f"Änderungsprotokoll (v{self.app_version})"):
                    gr.Markdown(changelogs)

        if self._app.f_user_management:
            self._app.app.load(
                self._build_quick_guide,
                inputs=[self._app.user_id],
                outputs=[self.quick_guide],
                show_progress="hidden",
            )
            self._app.user_id.change(
                self._build_quick_guide,
                inputs=[self._app.user_id],
                outputs=[self.quick_guide],
                show_progress="hidden",
            )
        else:
            self._app.app.load(
                self._build_quick_guide,
                inputs=[],
                outputs=[self.quick_guide],
                show_progress="hidden",
            )

    def _build_quick_guide(self, user_id=None):
        guide_common = """### Anleitung

1. **Anmelden:**
   Melde dich mit deinem Benutzerkonto im System an. Stelle sicher, dass deine Zugangsdaten korrekt sind. Falls du dein Passwort vergessen hast oder keinen Zugriff erh\u00e4ltst, wende dich an den Support.

2. **Daten hochladen:**
   Wechsle in den Reiter `Dateien`. Dort kannst du Dokumente (z. B. PDFs, Word-Dateien) oder URLs hochladen.
   Nach dem Upload m\u00fcssen die Inhalte indexiert werden, damit sie im Chat verwendet werden k\u00f6nnen. Achte darauf, dass die Daten vollst\u00e4ndig verarbeitet wurden, bevor du sie nutzt.

3. **Chat verwenden:**
   Im Reiter `Chat` kannst du Fragen stellen und mit den hochgeladenen bzw. freigegebenen Daten arbeiten.
   Formuliere deine Fragen m\u00f6glichst klar und konkret, um bessere Ergebnisse zu erhalten. Du kannst auch Folgefragen stellen, um Antworten zu vertiefen.

4. **Einstellungen pr\u00fcfen:**
   Unter `Einstellungen` kannst du dein Profil verwalten, die Sprache anpassen und ggf. Modelloptionen konfigurieren.
   Pr\u00fcfe regelm\u00e4\u00dfig, ob deine Einstellungen deinen Anforderungen entsprechen (z. B. bevorzugte Sprache oder Ausgabeformat).

---

#### Zus\u00e4tzliche Hinweise (f\u00fcr alle Rollen)

* **Datenqualit\u00e4t beachten:** Hochgeladene Inhalte sollten strukturiert und gut lesbar sein, um optimale Ergebnisse zu erzielen.
* **Zugriffsrechte:** Du siehst nur Daten, f\u00fcr die du freigeschaltet bist. Wenn etwas fehlt, k\u00f6nnte es an fehlenden Berechtigungen liegen.
* **Support:** Falls dir Daten, Teams oder bestimmte Funktionen fehlen oder unklar sind, wende dich bitte an das KI-Kernteam. Sie unterst\u00fctzen dich gerne weiter und helfen dabei, offene Fragen zu kl\u00e4ren oder fehlende Zug\u00e4nge bereitzustellen.
""".encode('utf-8').decode('unicode_escape')

        if not self._app.f_user_management:
            return guide_common

        role = "user"
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if actor:
                if actor.is_admin:
                    role = "admin"
                elif actor.is_key_user:
                    role = "key_user"

        if role == "admin":
            return guide_common + """

---

#### F\u00fcr Admins

5. **Benutzer und Teams verwalten:**
   Unter `Ressourcen -> Benutzer` kannst du neue Benutzer anlegen, Teams erstellen und bestehende Strukturen verwalten.
   Weise Benutzern passende Rollen und Teams zu, damit sie Zugriff auf die richtigen Daten haben.

6. **Zugriffe steuern:**
   Definiere Upload- und Leserechte entsprechend der jeweiligen Rolle.
   Achte darauf, dass sensible Daten nur f\u00fcr berechtigte Personen zug\u00e4nglich sind.

7. **System\u00fcbersicht behalten:**
   \u00dcberpr\u00fcfe regelm\u00e4\u00dfig Benutzeraktivit\u00e4ten, Teamstrukturen und Datenzugriffe, um eine saubere Organisation sicherzustellen.
""".encode('utf-8').decode('unicode_escape')

        if role == "key_user":
            return guide_common + """

---

#### F\u00fcr Key User

5. **Team-Benutzer verwalten:**
   Unter `Ressourcen -> Benutzer` kannst du die Benutzer deines Teams verwalten.
   Pr\u00fcfe Teamzuordnungen und stelle sicher, dass alle Mitglieder die richtigen Zugriffsrechte haben.

6. **Daten im Team organisieren:**
   Unterst\u00fctze dein Team dabei, Daten sinnvoll zu strukturieren und aktuell zu halten, damit alle effizient arbeiten k\u00f6nnen.

7. **Ansprechpartner im Team:**
   Sei erste Anlaufstelle f\u00fcr Fragen innerhalb deines Teams und koordiniere bei Bedarf die Abstimmung mit dem KI-Kernteam.
""".encode('utf-8').decode('unicode_escape')

        return guide_common
