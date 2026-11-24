import re
import gradio as gr
import pandas as pd
from ktem.app import BasePage
from ktem.authz import get_access_context
from ktem.db.models import Conversation, Team, User, UserAccess, engine
from sqlalchemy import inspect, text
from sqlmodel import Session, select


def _resolve_user_names(session: Session) -> dict[str, str]:
    users = session.exec(select(User)).all()
    return {u.id: u.username for u in users}


def _visible_user_ids(session: Session, actor) -> set[str]:
    if not actor:
        return set()
    if actor.is_admin:
        users = session.exec(select(User)).all()
        return {u.id for u in users}
    if actor.is_key_user:
        stmt = select(UserAccess).where(UserAccess.created_by == actor.user.id)
        created_users = {row.user_id for row in session.exec(stmt).all()}
        created_users.add(actor.user.id)
        return created_users
    return {actor.user.id}


def _scope_label(actor) -> str:
    if not actor:
        return "Keine Daten"
    if actor.is_admin:
        return "Gesamt-Übersicht (Admin)"
    if actor.is_key_user:
        return "Team-Übersicht (Key-User)"
    return "Meine Daten"


def _parse_sources_from_html(html: str) -> list[str]:
    if not html:
        return []
    sources = re.findall(r'data-src="[^"]*file=([^"]+)"', html)
    names = []
    for src in sources:
        name = src.rsplit("/", 1)[-1] if "/" in src else src
        names.append(name)
    return names


class StatisticsPage(BasePage):

    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        self.scope_label = gr.Markdown("", elem_id="stats-scope")

        # Filter-Dropdowns (initial versteckt, werden von load_statistics sichtbar)
        with gr.Row():
            self.filter_team = gr.Dropdown(
                label="Team filtern",
                choices=[],
                value=None,
                visible=False,
                interactive=True,
            )
            self.filter_user = gr.Dropdown(
                label="Nutzer filtern",
                choices=[],
                value=None,
                visible=False,
                interactive=True,
            )

        # ── Feedback ──
        gr.Markdown("## Bewertungen (👍/👎)")
        with gr.Row():
            self.total_likes = gr.Number(label="👍 Positiv", value=0, interactive=False)
            self.total_dislikes = gr.Number(label="👎 Negativ", value=0, interactive=False)
            self.like_quote = gr.Number(label="Quote (%)", value=0, interactive=False)
            self.feedback_count = gr.Number(label="Chats bewertet", value=0, interactive=False)

        self.recent_negative = gr.DataFrame(
            headers=["Benutzer", "Frage", "Antwort (Vorschau)", "Quellen"],
            interactive=False,
            label="Zuletzt negativ bewertet",
        )

        # ── Dokument-Nutzung ──
        gr.Markdown("## Dokument-Nutzung")
        with gr.Row():
            self.top_docs = gr.DataFrame(
                headers=["Dokument", "Zitiert in Chats"],
                interactive=False,
                label="Meistzitierte Dokumente",
            )
            self.unused_docs = gr.DataFrame(
                headers=["Dokument"],
                interactive=False,
                label="Ungenutzte Dokumente",
            )

        # ── Chat-Statistik ──
        gr.Markdown("## Chat-Statistik")
        with gr.Row():
            self.total_questions = gr.Number(label="Fragen gestellt", value=0, interactive=False)
            self.citation_hit_rate = gr.Number(label="Trefferquote (%)", value=0, interactive=False)
            self.total_convs_count = gr.Number(label="Chats geführt", value=0, interactive=False)

        # ── Nutzer-Aktivität (admin/keyuser) ──
        self.user_activity_section = gr.Markdown("## Nutzer-Aktivität", visible=False)
        self.user_activity_table = gr.DataFrame(
            headers=["Benutzer", "Fragen", "👍", "👎", "Letzte Aktivität"],
            interactive=False,
            label="Nutzer-Aktivität",
            visible=False,
        )

        self.btn_refresh = gr.Button("Aktualisieren", variant="primary")

    def on_register_events(self):
        # Alle Outputs — gleiche Liste für alle Events
        all_outputs = [
            self.scope_label,
            self.filter_team,
            self.filter_user,
            self.total_likes,
            self.total_dislikes,
            self.like_quote,
            self.feedback_count,
            self.recent_negative,
            self.top_docs,
            self.unused_docs,
            self.total_questions,
            self.citation_hit_rate,
            self.total_convs_count,
            self.user_activity_section,
            self.user_activity_table,
        ]

        # Button
        self.btn_refresh.click(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_team, self.filter_user],
            outputs=all_outputs,
        )

        # Tab geöffnet / Login
        self._app.user_id.change(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_team, self.filter_user],
            outputs=all_outputs,
        )

        # Team-Filter geändert
        self.filter_team.change(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_team, self.filter_user],
            outputs=all_outputs,
        )

        # Nutzer-Filter geändert
        self.filter_user.change(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_team, self.filter_user],
            outputs=all_outputs,
        )

    def load_statistics(self, user_id=None, filter_team=None, filter_user=None):
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor:
                return self._empty_result()

            visible_ids = _visible_user_ids(session, actor)
            scope = _scope_label(actor)
            names = _resolve_user_names(session)

            # ── Dropdown-Choices bauen ──
            # Team-Filter
            if actor.is_admin:
                team_choices = [(t.name, t.id) for t in session.exec(select(Team)).all()]
            elif actor.is_key_user:
                all_teams = session.exec(select(Team)).all()
                team_choices = [(t.name, t.id) for t in all_teams
                                if getattr(t, "owner_user_id", None) == actor.user.id]
            else:
                team_choices = []

            # Nutzer-Filter
            user_choices = []
            for u in session.exec(select(User)).all():
                if u.id in visible_ids:
                    user_choices.append((u.username, u.id))

            # ── Sichtbarkeit ──
            is_privileged = actor.is_admin or actor.is_key_user
            team_visible = is_privileged and len(team_choices) > 0
            user_visible = is_privileged

            # ── Effektive User-IDs ──
            if filter_team and is_privileged:
                # Nutzer im gewählten Team
                stmt = select(UserAccess).where(UserAccess.team_id.like(f"%{filter_team}%"))
                team_user_ids = {row.user_id for row in session.exec(stmt).all()}
                effective_ids = (visible_ids & team_user_ids) if visible_ids else team_user_ids
            else:
                effective_ids = visible_ids

            if filter_user and filter_user in effective_ids:
                effective_ids = {filter_user}

            # ── Daten laden ──
            all_convs = []
            for uid in effective_ids:
                all_convs.extend(session.exec(
                    select(Conversation).where(Conversation.user == uid)
                ).all())

            existing_sources = self._get_existing_source_names(session)
            doc_citation_counts = {}
            total_questions = 0
            questions_with_hits = 0
            questions_without_hits = 0
            total_convs = 0
            user_activity = {}
            all_negative = []
            total_likes = 0
            total_dislikes = 0
            feedback_conv_count = 0

            for c in all_convs:
                ds = c.data_source or {}
                messages = ds.get("messages", [])
                likes = ds.get("likes", [])
                retrieval_msgs = ds.get("retrieval_messages", [])

                user_msgs = [m[0] for m in messages if m and len(m) >= 1 and m[0]]
                q_count = len(user_msgs)
                total_questions += q_count

                uid = c.user
                if uid not in user_activity:
                    user_activity[uid] = {"questions": 0, "likes": 0, "dislikes": 0, "last_active": ""}
                user_activity[uid]["questions"] += q_count
                date_str = str(c.date_updated)[:16] if hasattr(c, "date_updated") else ""
                if date_str > user_activity[uid]["last_active"]:
                    user_activity[uid]["last_active"] = date_str

                for retrieval_html in retrieval_msgs:
                    html = str(retrieval_html) if retrieval_html else ""
                    if "Keine Treffer" in html or "No evidence" in html:
                        questions_without_hits += 1
                    elif "pdf-link" in html or "citation" in html:
                        questions_with_hits += 1
                        for s in _parse_sources_from_html(html):
                            if s in existing_sources:
                                doc_citation_counts[s] = doc_citation_counts.get(s, 0) + 1

                if messages:
                    total_convs += 1

                if likes:
                    feedback_conv_count += 1
                for entry in likes:
                    if len(entry) >= 3:
                        idx, msg, liked = entry[0], entry[1], entry[2]
                        if liked:
                            total_likes += 1
                            user_activity[uid]["likes"] += 1
                        else:
                            total_dislikes += 1
                            user_activity[uid]["dislikes"] += 1
                            bot_msg = ""
                            if idx < len(messages):
                                pair = messages[idx]
                                if pair and len(pair) >= 2 and pair[1]:
                                    bot_msg = str(pair[1])
                            sources = []
                            if idx < len(retrieval_msgs) and retrieval_msgs[idx]:
                                sources = _parse_sources_from_html(str(retrieval_msgs[idx]))
                            filtered_srcs = [s for s in sources if s in existing_sources]
                            all_negative.append({
                                "Benutzer": names.get(uid, uid),
                                "Frage": (str(msg) if msg else "")[:80],
                                "Antwort": bot_msg[:100] if bot_msg else "-",
                                "Quellen": ", ".join(filtered_srcs[:3]) if filtered_srcs else "-",
                            })

            # ── Berechnungen ──
            total_all = total_likes + total_dislikes
            like_quote_val = round(100 * total_likes / total_all, 1) if total_all else 0
            total_hits = questions_with_hits + questions_without_hits
            hit_rate = round(100 * questions_with_hits / total_hits, 1) if total_hits else 0

            def _df_empty(cols, placeholder="-"):
                return pd.DataFrame([{c: placeholder for c in cols}])

            neg_rows = sorted(all_negative, key=lambda r: r["Benutzer"])[:20]
            neg_df = pd.DataFrame(neg_rows) if neg_rows else _df_empty(
                ["Benutzer", "Frage", "Antwort", "Quellen"]
            )

            filtered_citations = {k: v for k, v in doc_citation_counts.items() if k in existing_sources}
            top_docs_sorted = sorted(filtered_citations.items(), key=lambda x: -x[1])[:15]
            top_rows = [{"Dokument": d, "Zitiert in Chats": c} for d, c in top_docs_sorted]
            top_df = pd.DataFrame(top_rows) if top_rows else _df_empty(
                ["Dokument", "Zitiert in Chats"], "Keine Daten"
            )

            unused_rows = self._get_unused_docs(session, actor, visible_ids, set(doc_citation_counts.keys()))
            unused_df = pd.DataFrame(unused_rows) if unused_rows else _df_empty(
                ["Dokument"], "Keine ungenutzten Dokumente"
            )

            ua_rows = []
            for uid, stats in sorted(user_activity.items(), key=lambda x: -x[1]["questions"]):
                ua_rows.append({
                    "Benutzer": names.get(uid, uid),
                    "Fragen": stats["questions"],
                    "👍": stats["likes"],
                    "👎": stats["dislikes"],
                    "Letzte Aktivität": stats["last_active"],
                })
            ua_df = pd.DataFrame(ua_rows) if ua_rows else _df_empty(
                ["Benutzer", "Fragen", "👍", "👎", "Letzte Aktivität"]
            )

            show_ua = is_privileged
            scope_html = f"<div style='padding:8px 12px;background:#1e1e2e;border-radius:6px;font-weight:700;color:#f97316;font-size:16px'>{scope}</div>"

            return (
                scope_html,
                gr.update(choices=team_choices, visible=team_visible),
                gr.update(choices=user_choices, visible=user_visible),
                total_likes,
                total_dislikes,
                like_quote_val,
                feedback_conv_count,
                neg_df,
                top_df,
                unused_df,
                total_questions,
                hit_rate,
                total_convs,
                gr.update(visible=show_ua),
                gr.update(visible=show_ua, value=ua_df),
            )

    def _get_existing_source_names(self, session) -> set[str]:
        inspector = inspect(session.connection())
        sources = set()
        for tname in inspector.get_table_names():
            if tname.startswith("index__") and tname.endswith("__source"):
                try:
                    rows = session.exec(text(f'SELECT name FROM "{tname}"')).all()
                    for (name,) in rows:
                        sources.add(name)
                except Exception:
                    continue
        return sources

    def _get_unused_docs(self, session, actor, visible_ids, cited_names):
        all_sources = self._get_existing_source_names(session)
        return [{"Dokument": n} for n in sorted(all_sources - cited_names)][:30]

    def _empty_result(self):
        return (
            "Keine Daten",
            gr.update(choices=[], visible=False),
            gr.update(choices=[], visible=False),
            0, 0, 0, 0,
            pd.DataFrame([{"Benutzer": "-", "Frage": "-", "Antwort": "-", "Quellen": "-"}]),
            pd.DataFrame([{"Dokument": "-", "Zitiert in Chats": "-"}]),
            pd.DataFrame([{"Dokument": "-"}]),
            0, 0, 0,
            gr.update(visible=False),
            gr.update(visible=False),
        )
