import gradio as gr
import pandas as pd
from ktem.app import BasePage
from ktem.db.models import Conversation, engine
from sqlmodel import Session, select


class FeedbackPage(BasePage):
    """Zeigt Chat-Bewertungen (👍/👎) aggregiert für Admins."""

    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Row():
            with gr.Column(scale=1):
                self.total_likes = gr.Number(
                    label="👍 Positive Bewertungen", value=0, interactive=False
                )
            with gr.Column(scale=1):
                self.total_dislikes = gr.Number(
                    label="👎 Negative Bewertungen", value=0, interactive=False
                )
            with gr.Column(scale=1):
                self.quote = gr.Number(
                    label="Positiv-Quote (%)", value=0, interactive=False
                )
            with gr.Column(scale=1):
                self.total_convs = gr.Number(
                    label="Chats mit Feedback", value=0, interactive=False
                )

        self.feedback_table = gr.DataFrame(
            headers=["Benutzer", "👍", "👎", "Quote"],
            interactive=False,
            label="Feedback pro Benutzer",
        )

        self.recent_feedback = gr.DataFrame(
            headers=["Benutzer", "Nachricht", "Bewertung", "Datum"],
            interactive=False,
            label="Letzte Bewertungen",
        )

        self.btn_refresh = gr.Button("Aktualisieren", variant="primary")

    def on_register_events(self):
        self.btn_refresh.click(
            self.load_feedback,
            inputs=[self._app.user_id],
            outputs=[
                self.total_likes,
                self.total_dislikes,
                self.quote,
                self.total_convs,
                self.feedback_table,
                self.recent_feedback,
            ],
            show_progress="hidden",
        )

        self._app.user_id.change(
            self.load_feedback,
            inputs=[self._app.user_id],
            outputs=[
                self.total_likes,
                self.total_dislikes,
                self.quote,
                self.total_convs,
                self.feedback_table,
                self.recent_feedback,
            ],
            show_progress="hidden",
        )

    def _parse_feedback(self):
        """Sammelt alle Likes aus allen Conversations."""
        user_feedback = {}  # user -> {"likes": int, "dislikes": int}
        recent = []
        with Session(engine) as session:
            convs = session.exec(select(Conversation)).all()
            convs_with_feedback = 0
            for c in convs:
                likes = (c.data_source or {}).get("likes", [])
                if not likes:
                    continue
                convs_with_feedback += 1
                user = c.user or "unbekannt"
                if user not in user_feedback:
                    user_feedback[user] = {"likes": 0, "dislikes": 0, "total": 0}
                for entry in likes:
                    if len(entry) >= 3:
                        index, msg, liked = entry[0], entry[1], entry[2]
                        if liked:
                            user_feedback[user]["likes"] += 1
                        else:
                            user_feedback[user]["dislikes"] += 1
                        user_feedback[user]["total"] += 1
                        recent.append({
                            "Benutzer": user,
                            "Nachricht": (msg or "")[:80],
                            "Bewertung": "👍" if liked else "👎",
                            "Datum": str(c.date_updated)[:16] if hasattr(c, "date_updated") else "-",
                        })
        return user_feedback, recent, convs_with_feedback

    def load_feedback(self, user_id=None):
        user_feedback, recent, convs_with_feedback = self._parse_feedback()

        total_likes = sum(u["likes"] for u in user_feedback.values())
        total_dislikes = sum(u["dislikes"] for u in user_feedback.values())
        total_all = total_likes + total_dislikes
        quote = round(100 * total_likes / total_all, 1) if total_all else 0

        user_rows = []
        for user, stats in sorted(user_feedback.items()):
            t = stats["total"]
            user_rows.append({
                "Benutzer": user,
                "👍": stats["likes"],
                "👎": stats["dislikes"],
                "Quote": f"{round(100 * stats['likes'] / t, 1)}%" if t else "-",
            })

        recent = sorted(recent, key=lambda r: r["Datum"], reverse=True)[:20]
        recent_rows = [{
            "Benutzer": r["Benutzer"],
            "Nachricht": r["Nachricht"],
            "Bewertung": r["Bewertung"],
            "Datum": r["Datum"],
        } for r in recent]

        return (
            total_likes,
            total_dislikes,
            quote,
            convs_with_feedback,
            pd.DataFrame(user_rows) if user_rows else pd.DataFrame(
                [{"Benutzer": "-", "👍": 0, "👎": 0, "Quote": "-"}]
            ),
            pd.DataFrame(recent_rows) if recent_rows else pd.DataFrame(
                [{"Benutzer": "-", "Nachricht": "-", "Bewertung": "-", "Datum": "-"}]
            ),
        )
