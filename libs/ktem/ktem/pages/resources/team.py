import uuid
from typing import Optional

import gradio as gr
import pandas as pd
from ktem.app import BasePage
from sqlalchemy import inspect

from ktem.authz import (
    get_access_context,
    list_teams,
    parse_team_ids,
)
from ktem.db.models import Team, UserAccess, engine
from sqlalchemy import text
from sqlmodel import Session, select


def _resolve_actor(session: Session, actor_user_id: Optional[str]):
    actor = get_access_context(session, actor_user_id)
    return actor


def _team_table_has_name_lower(session: Session) -> bool:
    """Check if the team table still has the legacy name_lower column."""
    inspector = inspect(session.connection())
    columns = [col["name"] for col in inspector.get_columns("team")]
    return "name_lower" in columns


class TeamManagement(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        self.team_state = gr.State(value=None)
        self.team_list = gr.DataFrame(
            headers=["id", "name", "global"], interactive=False
        )
        self.selected_team_id = gr.State(value=None)
        self.team_name_new = gr.Textbox(label="Teamname")
        self.team_global_edit = gr.Checkbox(label="Globales Team", value=False)
        self.btn_team_save = gr.Button("Global-Status speichern")
        with gr.Row():
            self.btn_team_create = gr.Button("Team erstellen")
            self.btn_team_delete = gr.Button("Team löschen")

    def on_register_events(self):
        self._app.user_id.change(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
            show_progress="hidden",
        )

        self.btn_team_create.click(
            self.create_team,
            inputs=[self._app.user_id, self.team_name_new],
            outputs=[self.team_name_new],
            show_progress="hidden",
        ).then(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
        )

        self.team_list.select(
            self.select_team,
            inputs=[self.team_state],
            outputs=[self.selected_team_id],
            show_progress="hidden",
        )
        self.selected_team_id.change(
            self.on_selected_team_change,
            inputs=[self.team_state, self.selected_team_id],
            outputs=[self.team_global_edit],
            show_progress="hidden",
        )

        self.btn_team_save.click(
            self.save_team_global_status,
            inputs=[self._app.user_id, self.selected_team_id, self.team_global_edit],
            outputs=[self.team_global_edit],
            show_progress="hidden",
        ).then(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
        )

        self.btn_team_delete.click(
            self.delete_team,
            inputs=[self._app.user_id, self.selected_team_id],
            outputs=[self.selected_team_id],
            show_progress="hidden",
        ).then(
            self.list_teams_ui,
            inputs=[self._app.user_id],
            outputs=[self.team_state, self.team_list],
        )

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.list_teams_ui,
                "inputs": [self._app.user_id],
                "outputs": [self.team_state, self.team_list],
            },
        )
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": lambda: (
                    [],
                    pd.DataFrame.from_records(
                        [{"id": "-", "name": "-", "global": "-"}]
                    ),
                    None,
                    False,
                ),
                "outputs": [
                    self.team_state,
                    self.team_list,
                    self.selected_team_id,
                    self.team_global_edit,
                ],
            },
        )

    def list_teams_ui(self, actor_user_id):
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                return [], pd.DataFrame.from_records(
                    [{"id": "-", "name": "-", "global": "-"}]
                )

            teams = list_teams(session)
            rows = [
                {
                    "id": t.id,
                    "name": t.name,
                    "global": bool(getattr(t, "is_global", False)),
                }
                for t in teams
            ]
            if not rows:
                rows = [{"id": "-", "name": "-", "global": "-"}]
            return rows, pd.DataFrame.from_records(rows)

    def on_selected_team_change(self, team_rows, selected_team_id):
        if not selected_team_id:
            return gr.update(value=False)
        for row in team_rows or []:
            if row.get("id") == selected_team_id:
                return gr.update(value=bool(row.get("global", False)))
        return gr.update(value=False)

    def select_team(self, team_rows, ev: gr.SelectData):
        if (ev.value == "-" and ev.index[0] == 0) or not ev.selected:
            return None
        return team_rows[ev.index[0]]["id"]

    def create_team(self, actor_user_id, team_name):
        team_name = (team_name or "").strip()
        if not team_name:
            gr.Warning("Teamname darf nicht leer sein")
            return team_name
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                gr.Warning("Nur Admin darf Teams erstellen")
                return team_name

            exists = session.exec(
                select(Team).where(Team.name == team_name)
            ).first()
            if exists:
                gr.Warning(f'Team "{team_name}" existiert bereits')
                return team_name

            # Backward compatibility for existing databases that still have
            # the legacy `name_lower` column on team table.
            if _team_table_has_name_lower(session):
                session.exec(
                    text(
                        "INSERT INTO team (id, name, name_lower, is_global, owner_user_id) VALUES (:id, :name, :name_lower, :is_global, :owner_user_id)"
                    ).bindparams(
                        id=uuid.uuid4().hex,
                        name=team_name,
                        name_lower=team_name.lower(),
                        is_global=False,
                        owner_user_id=actor.user.id,
                    )
                )
                session.commit()
            else:
                session.add(
                    Team(
                        name=team_name,
                        is_global=False,
                        owner_user_id=actor.user.id,
                    )
                )
                session.commit()
            gr.Info(f'Team "{team_name}" erstellt')
            return ""

    def save_team_global_status(self, actor_user_id, team_id, is_global):
        if not team_id:
            gr.Warning("Kein Team ausgewählt")
            return gr.update(value=bool(is_global))
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                gr.Warning("Nur Admin darf Team-Status ändern")
                return gr.update(value=bool(is_global))

            team = session.exec(select(Team).where(Team.id == team_id)).first()
            if not team:
                gr.Warning("Team nicht gefunden")
                return gr.update(value=bool(is_global))

            team.is_global = bool(is_global)
            session.add(team)
            session.commit()
            gr.Info(f'Team "{team.name}" aktualisiert')
            return gr.update(value=bool(team.is_global))

    def delete_team(self, actor_user_id, team_id):
        if not team_id:
            gr.Warning("Kein Team ausgewählt")
            return None
        with Session(engine) as session:
            actor = _resolve_actor(session, actor_user_id)
            if not actor or not actor.is_admin:
                gr.Warning("Nur Admin darf Teams löschen")
                return team_id

            team = session.exec(select(Team).where(Team.id == team_id)).first()
            if not team:
                gr.Warning("Team nicht gefunden")
                return None
            if team.owner_user_id and team.owner_user_id != actor.user.id:
                gr.Warning("Nur der Ersteller darf dieses Team löschen")
                return team_id

            accesses = session.exec(select(UserAccess)).all()
            in_membership_use = any(
                team_id in parse_team_ids(access.team_id)
                for access in accesses
            )
            in_default_use = any(
                access.default_team_id == team_id for access in accesses
            )
            if in_membership_use or in_default_use:
                gr.Warning(
                    "Team kann nicht gelöscht werden, solange Benutzer zugeordnet sind oder es als Standardteam verwendet wird"
                )
                return team_id

            session.delete(team)
            session.commit()
            gr.Info(f'Team "{team.name}" gelöscht')
            return None
