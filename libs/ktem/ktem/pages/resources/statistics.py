import re
import gradio as gr
import pandas as pd
from ktem.app import BasePage
from ktem.authz import get_access_context, managed_team_ids
from ktem.db.models import Conversation, User, UserAccess, engine
from sqlalchemy import inspect, text
from sqlmodel import Session, select


def _resolve_user_names(session: Session) -> dict[str, str]:
    """User-ID -> Username."""
    users = session.exec(select(User)).all()
    return {u.id: u.username for u in users}


def _visible_user_ids(session: Session, actor) -> set[str]:
    """Which user IDs are visible to the given actor? Never empty."""
    if not actor:
        return set()
    if actor.is_admin:
        users = session.exec(select(User)).all()
        return {u.id for u in users}
    if actor.is_key_user:
        # Own users: created_by == actor.user.id
        stmt = select(UserAccess).where(UserAccess.created_by == actor.user.id)
        created_users = {row.user_id for row in session.exec(stmt).all()}
        created_users.add(actor.user.id)
        return created_users
    # Normal user → only self
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
    """Extract source file names / IDs from citation HTML."""
    if not html:
        return []
    # Match data-src="/file=.../path/to/file.pdf"
    sources = re.findall(r'data-src="[^"]*file=([^"]+)"', html)
    # Extract filename or source ID from path
    names = []
    for src in sources:
        # Take the filename part
        name = src.rsplit("/", 1)[-1] if "/" in src else src
        names.append(name)
    return names


class StatisticsPage(BasePage):
    """Umfassende Statistiken für alle Rollen."""

    def __init__(self, app):
        self._app = app
        self._visible_users_cache = []
        self.on_building_ui()

    def on_building_ui(self):
        # Scope label
        self.scope_label = gr.Markdown("", elem_id="stats-scope")

        # User filter dropdown (admin/keyuser)
        self.filter_user = gr.Dropdown(
            label="Nutzer filtern",
            choices=[],
            value=None,
            visible=False,
            interactive=True,
        )

        with gr.Row():
            self.stats_html = gr.HTML("")

        # ── Feedback section ──
        gr.Markdown("## Bewertungen (👍/👎)")
        with gr.Row():
            with gr.Column(scale=1):
                self.total_likes = gr.Number(label="👍 Positiv", value=0, interactive=False)
            with gr.Column(scale=1):
                self.total_dislikes = gr.Number(label="👎 Negativ", value=0, interactive=False)
            with gr.Column(scale=1):
                self.like_quote = gr.Number(label="Quote (%)", value=0, interactive=False)
            with gr.Column(scale=1):
                self.feedback_count = gr.Number(label="Chats bewertet", value=0, interactive=False)

        self.recent_negative = gr.DataFrame(
            headers=["Benutzer", "Frage", "Antwort (Vorschau)", "Quellen"],
            interactive=False,
            label="Zuletzt negativ bewertet",
        )

        # ── Document usage ──
        gr.Markdown("## Dokument-Nutzung")
        with gr.Row():
            with gr.Column():
                self.top_docs = gr.DataFrame(
                    headers=["Dokument", "Zitiert in Chats"],
                    interactive=False,
                    label="Meistzitierte Dokumente",
                )
            with gr.Column():
                self.unused_docs = gr.DataFrame(
                    headers=["Dokument"],
                    interactive=False,
                    label="Ungenutzte Dokumente",
                )

        # ── Chat statistics ──
        gr.Markdown("## Chat-Statistik")
        with gr.Row():
            with gr.Column(scale=1):
                self.total_questions = gr.Number(label="Fragen gestellt", value=0, interactive=False)
            with gr.Column(scale=1):
                self.citation_hit_rate = gr.Number(label="Trefferquote (%)", value=0, interactive=False)
            with gr.Column(scale=1):
                self.total_convs_count = gr.Number(label="Chats geführt", value=0, interactive=False)

        # ── User activity (admin/keyuser) ──
        self.user_activity_section = gr.Markdown("## Nutzer-Aktivität", visible=False)
        self.user_activity_table = gr.DataFrame(
            headers=["Benutzer", "Fragen", "👍", "👎", "Letzte Aktivität"],
            interactive=False,
            label="Nutzer-Aktivität",
            visible=False,
        )

        # Refresh button
        self.btn_refresh = gr.Button("Aktualisieren", variant="primary")

    def on_register_events(self):
        self.btn_refresh.click(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_user],
            outputs=[
                self.scope_label,
                self.filter_user,
                self.stats_html,
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
            ],
            show_progress="hidden",
        )

        self._app.user_id.change(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_user],
            outputs=[
                self.scope_label,
                self.filter_user,
                self.stats_html,
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
            ],
            show_progress="hidden",
        )

        self.filter_user.change(
            self.load_statistics,
            inputs=[self._app.user_id, self.filter_user],
            outputs=[
                self.scope_label,
                self.stats_html,
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
            ],
            show_progress="hidden",
        )

    def _build_filter_choices(self, session: Session, actor, visible_ids: set[str]):
        """Build dropdown choices for user filter."""
        names = _resolve_user_names(session)
        users_list = session.exec(select(User)).all()
        self._visible_users_cache = []
        choices = []
        for u in users_list:
            if u.id in visible_ids:
                name = u.username
                choices.append((name, u.id))
                self._visible_users_cache.append(u.id)
        return choices

    def load_statistics(self, user_id=None, filter_user=None):
        """Main data loader — role-scoped."""
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            if not actor:
                return self._empty_result()

            visible_ids = _visible_user_ids(session, actor)
            scope = _scope_label(actor)

            # Build filter choices on first load
            choices = self._build_filter_choices(session, actor, visible_ids)

            # Determine effective user filter
            if actor.is_admin or actor.is_key_user:
                filter_visible = True
                if filter_user and filter_user in visible_ids:
                    effective_ids = {filter_user}
                else:
                    effective_ids = visible_ids
            else:
                filter_visible = False
                effective_ids = {actor.user.id}

            # Fetch conversations for effective users
            all_convs = []
            if effective_ids:
                for uid in effective_ids:
                    stmt = select(Conversation).where(Conversation.user == uid)
                    convs = session.exec(stmt).all()
                    all_convs.extend(convs)

            # ═══ Aggregate ═══
            names = _resolve_user_names(session)
            doc_citation_counts = {}  # doc_name → count
            unused_docs_set = set()  # placeholder — needs Source table data
            total_questions = 0
            questions_with_hits = 0
            questions_without_hits = 0
            total_convs = 0
            user_activity = {}  # user_id → {questions, likes, dislikes, last_active}
            all_negative = []
            total_likes = 0
            total_dislikes = 0
            feedback_conv_count = 0

            for c in all_convs:
                ds = c.data_source or {}
                messages = ds.get("messages", [])
                likes = ds.get("likes", [])
                retrieval_msgs = ds.get("retrieval_messages", [])

                # Questions count
                # messages = [[user_msg, bot_msg], ...]
                user_msgs = [m[0] for m in messages if m and len(m) >= 1 and m[0]]
                q_count = len(user_msgs)
                total_questions += q_count

                # User activity
                uid = c.user
                if uid not in user_activity:
                    user_activity[uid] = {"questions": 0, "likes": 0, "dislikes": 0, "last_active": ""}
                user_activity[uid]["questions"] += q_count
                date_str = str(c.date_updated)[:16] if hasattr(c, "date_updated") else ""
                if date_str > user_activity[uid]["last_active"]:
                    user_activity[uid]["last_active"] = date_str

                # Citation hit rate
                # Check if each bot response had citations or "Keine Treffer"
                for retrieval_html in retrieval_msgs:
                    if not retrieval_html:
                        continue
                    html = str(retrieval_html)
                    if "Keine Treffer" in html or "No evidence" in html:
                        questions_without_hits += 1
                    elif 'pdf-link' in html or 'citation' in html:
                        questions_with_hits += 1
                        # Extract source documents
                        sources = _parse_sources_from_html(html)
                        for s in sources:
                            doc_citation_counts[s] = doc_citation_counts.get(s, 0) + 1

                # Total conversations (any with messages)
                if messages:
                    total_convs += 1

                # Feedback analysis
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
                            # Get the corresponding bot response
                            bot_msg = ""
                            if idx < len(messages):
                                pair = messages[idx]
                                if pair and len(pair) >= 2 and pair[1]:
                                    bot_msg = str(pair[1])
                            # Get sources from corresponding retrieval
                            sources = []
                            if idx < len(retrieval_msgs) and retrieval_msgs[idx]:
                                sources = _parse_sources_from_html(str(retrieval_msgs[idx]))
                            all_negative.append({
                                "Benutzer": names.get(uid, uid),
                                "Frage": (str(msg) if msg else "")[:80],
                                "Antwort": bot_msg[:100] if bot_msg else "-",
                                "Quellen": ", ".join(sources[:3]) if sources else "-",
                            })

            # ═══ Build outputs ═══
            total_all = total_likes + total_dislikes
            like_quote_val = round(100 * total_likes / total_all, 1) if total_all else 0
            total_hits = questions_with_hits + questions_without_hits
            hit_rate = round(100 * questions_with_hits / total_hits, 1) if total_hits else 0

            # Feedback KPIs
            def _df_empty(cols, placeholder="-"):
                return pd.DataFrame([{c: placeholder for c in cols}])

            # Negative feedback table
            neg_rows = sorted(all_negative, key=lambda r: r["Benutzer"])[:20]
            neg_df = pd.DataFrame(neg_rows) if neg_rows else _df_empty(
                ["Benutzer", "Frage", "Antwort", "Quellen"]
            )

            # Top docs
            top_docs_sorted = sorted(doc_citation_counts.items(), key=lambda x: -x[1])[:15]
            top_rows = [{"Dokument": d, "Zitiert in Chats": c} for d, c in top_docs_sorted]
            top_df = pd.DataFrame(top_rows) if top_rows else _df_empty(
                ["Dokument", "Zitiert in Chats"], "Keine Daten"
            )

            # Unused docs — query from Source/index tables
            unused_rows = self._get_unused_docs(session, actor, visible_ids, set(doc_citation_counts.keys()))
            unused_df = pd.DataFrame(unused_rows) if unused_rows else _df_empty(
                ["Dokument"], "Keine ungenutzten Dokumente"
            )

            # User activity table
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

            # Show user activity only for admin/keyuser
            show_ua = actor.is_admin or actor.is_key_user
            ua_section = gr.update(visible=show_ua)
            ua_visible = gr.update(visible=show_ua)

            # Scope HTML
            scope_html = f"<div style='padding:8px 12px;background:#1e1e2e;border-radius:6px;font-weight:700;color:#f97316;font-size:16px'>{scope}</div>"

            return (
                scope_html,
                gr.update(choices=choices, visible=filter_visible),
                "",  # stats_html (reserved)
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
                ua_section,
                ua_visible,
            )

    def _get_unused_docs(self, session, actor, visible_ids, cited_names):
        """Find documents that exist but have never been cited."""
        unused = []
        # Try to query Source table from index
        # The Source table is dynamically created per index
        inspector = inspect(session.connection())
        table_names = inspector.get_table_names()
        all_sources = set()
        for tname in table_names:
            if tname.startswith("index__") and tname.endswith("__source"):
                try:
                    rows = session.exec(text(f'SELECT name FROM "{tname}"')).all()
                    for (name,) in rows:
                        all_sources.add(name)
                except Exception:
                    continue

        for name in sorted(all_sources):
            if name not in cited_names:
                unused.append({"Dokument": name})
        return unused[:30]

    def _empty_result(self):
        """Return empty defaults when no actor."""
        return (
            "Keine Daten",
            gr.update(choices=[], visible=False),
            "",
            0, 0, 0, 0,
            pd.DataFrame([{"Benutzer": "-", "Frage": "-", "Antwort": "-", "Quellen": "-"}]),
            pd.DataFrame([{"Dokument": "-", "Zitiert in Chats": "-"}]),
            pd.DataFrame([{"Dokument": "-"}]),
            0, 0, 0,
            gr.update(visible=False),
            gr.update(visible=False),
        )
