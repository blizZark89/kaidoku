import ktem.db.base_models as base_models
from ktem.db.engine import engine
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

_base_user_team_membership = (
    import_dotted_string(settings.KH_TABLE_USER_TEAM_MEMBERSHIP, safe=False)
    if hasattr(settings, "KH_TABLE_USER_TEAM_MEMBERSHIP")
    else base_models.BaseUserTeamMembership
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


class UserTeamMembership(_base_user_team_membership, table=True):  # type: ignore
    """User-team membership table"""


if not getattr(settings, "KH_ENABLE_ALEMBIC", False):
    SQLModel.metadata.create_all(engine)
