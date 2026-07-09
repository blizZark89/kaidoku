"""Speech-to-Text settings manager."""

from typing import Optional, Type

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SpeechTable, engine


class SpeechManager:
    """Manage speech/transcription configuration."""

    def __init__(self):
        self._configs: dict[str, dict] = {}
        self._default: str = ""
        self.load()

    def load(self):
        """Load speech configs from database."""
        self._configs, self._default = {}, ""
        with Session(engine) as session:
            stmt = select(SpeechTable)
            items = session.execute(stmt)
            for (item,) in items:
                self._configs[item.name] = {
                    "name": item.name,
                    "spec": item.spec,
                    "default": item.default,
                }
                if item.default:
                    self._default = item.name

    def info(self) -> dict:
        """List all speech configs."""
        return self._configs

    def get_default(self) -> Optional[dict]:
        """Get the default speech configuration."""
        if self._default and self._default in self._configs:
            return self._configs[self._default]
        # Return first available config if no default is set
        if self._configs:
            return next(iter(self._configs.values()))
        return None

    def get_default_spec(self) -> Optional[dict]:
        """Get the spec of the default speech configuration."""
        default = self.get_default()
        if default:
            return default.get("spec", {})
        return None

    def add(self, name: str, spec: dict, default: bool):
        """Add a new speech config."""
        if not name:
            raise ValueError("Name must not be empty")
        try:
            with Session(engine) as session:
                if default:
                    session.query(SpeechTable).update({"default": False})
                    session.commit()
                item = SpeechTable(name=name, spec=spec, default=default)
                session.add(item)
                session.commit()
        except Exception as e:
            raise ValueError(f"Failed to add speech config {name}: {e}")
        self.load()

    def delete(self, name: str):
        """Delete a speech config."""
        try:
            with Session(engine) as session:
                item = session.query(SpeechTable).filter_by(name=name).first()
                session.delete(item)
                session.commit()
        except Exception as e:
            raise ValueError(f"Failed to delete speech config {name}: {e}")
        self.load()

    def update(
        self, name: str, spec: dict, default: bool, new_name: str = ""
    ):
        """Update a speech config, optionally renaming it."""
        if not name:
            raise ValueError("Name must not be empty")
        if new_name and new_name != name:
            if new_name in self._configs:
                raise ValueError(
                    f"Speech config '{new_name}' already exists."
                )
            self.delete(name)
            self.add(new_name, spec=spec, default=default)
            return
        try:
            with Session(engine) as session:
                if default:
                    session.query(SpeechTable).update({"default": False})
                    session.commit()
                item = session.query(SpeechTable).filter_by(name=name).first()
                if not item:
                    raise ValueError(f"Speech config {name} not found")
                item.spec = spec
                item.default = default
                session.commit()
        except Exception as e:
            raise ValueError(f"Failed to update speech config {name}: {e}")
        self.load()


speech_manager = SpeechManager()