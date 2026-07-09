"""Speech settings database table."""

from typing import Type

from ktem.db.engine import engine
from sqlalchemy import JSON, Boolean, Column, String
from sqlalchemy.orm import DeclarativeBase
from theflow.settings import settings as flowsettings
from theflow.utils.modules import import_dotted_string


class Base(DeclarativeBase):
    pass


class BaseSpeechTable(Base):
    """Base table to store speech/transcription settings."""

    __abstract__ = True

    name = Column(String, primary_key=True, unique=True)
    spec = Column(JSON, default={})
    default = Column(Boolean, default=False)


_base_speech: Type[BaseSpeechTable] = (
    import_dotted_string(flowsettings.KH_TABLE_SPEECH, safe=False)
    if hasattr(flowsettings, "KH_TABLE_SPEECH")
    else BaseSpeechTable
)


class SpeechTable(_base_speech):  # type: ignore
    __tablename__ = "speech_table"


if not getattr(flowsettings, "KH_ENABLE_ALEMBIC", False):
    SpeechTable.metadata.create_all(engine)