import ktem.db.base_models as base_models
from ktem.db.engine import engine
from sqlalchemy import inspect, text
from sqlmodel import SQLModel
from theflow.settings import settings
from theflow.utils.modules import import_dotted_string

_base_conv = (
    import_dotted_string(settings.KH_TABLE_CONV, safe=False)
    if hasattr(settings, "KH_TABLE_CONV")
    else base_models.BaseConversation
)

_base_user = (
    import_dotted_string(settings.KH_TABLE_USER, safe=False)
    if hasattr(settings, "KH_TABLE_USER")
    else base_models.BaseUser
)

_base_settings = (
    import_dotted_string(settings.KH_TABLE_SETTINGS, safe=False)
    if hasattr(settings, "KH_TABLE_SETTINGS")
    else base_models.BaseSettings
)

_base_issue_report = (
    import_dotted_string(settings.KH_TABLE_ISSUE_REPORT, safe=False)
    if hasattr(settings, "KH_TABLE_ISSUE_REPORT")
    else base_models.BaseIssueReport
)

_base_team = (
    import_dotted_string(settings.KH_TABLE_TEAM, safe=False)
    if hasattr(settings, "KH_TABLE_TEAM")
    else base_models.BaseTeam
)

_base_user_access = (
    import_dotted_string(settings.KH_TABLE_USER_ACCESS, safe=False)
    if hasattr(settings, "KH_TABLE_USER_ACCESS")
    else base_models.BaseUserAccess
)


class Conversation(_base_conv, table=True):  # type: ignore
    """Conversation record"""


class User(_base_user, table=True):  # type: ignore
    """User table"""


class Settings(_base_settings, table=True):  # type: ignore
    """Record of settings"""


class IssueReport(_base_issue_report, table=True):  # type: ignore
    """Record of issues"""


class Team(_base_team, table=True):  # type: ignore
    """Team table"""


class UserAccess(_base_user_access, table=True):  # type: ignore
    """User role, team and permissions"""


def _ensure_team_global_schema():
    inspector = inspect(engine)
    table_name = Team.__tablename__
    if not inspector.has_table(table_name):
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "is_global" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                f'ALTER TABLE "{table_name}" ADD COLUMN is_global BOOLEAN DEFAULT 0'
            )
        )
        connection.execute(
            text(f'UPDATE "{table_name}" SET is_global = 0 WHERE is_global IS NULL')
        )


def _ensure_user_access_default_team_schema():
    inspector = inspect(engine)
    table_name = UserAccess.__tablename__
    if not inspector.has_table(table_name):
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "default_team_id" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                f'ALTER TABLE "{table_name}" ADD COLUMN default_team_id VARCHAR'
            )
        )


if not getattr(settings, "KH_ENABLE_ALEMBIC", False):
    SQLModel.metadata.create_all(engine)
    _ensure_team_global_schema()
    _ensure_user_access_default_team_schema()
