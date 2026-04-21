import hashlib
import json
import logging
import os
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import gradio as gr
import pandas as pd
from sqlmodel import Session, select

import flowsettings
from ktem.authz import get_access_context, has_upload_access, list_teams
from ktem.db.models import Settings, User, engine

logger = logging.getLogger(__name__)

FILESYNC_DIR = Path(flowsettings.KH_USER_DATA_DIR) / "filesync"
FILESYNC_CONFIG_PATH = FILESYNC_DIR / "config.json"
FILESYNC_STATE_PATH = FILESYNC_DIR / "state.json"
DEFAULT_GROUP_KEY = "__default__"
DEFAULT_GROUP_LABEL = "Standard"
LEGACY_SYNC_GROUP_PREFIX = "FileSync / "


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


FILESYNC_MESSAGES = {
    "config_saved": "Konfiguration gespeichert",
    "path_missing": "Ordnerpfad fehlt",
    "local_paths_only": "Nur lokale absolute Ordnerpfade sind erlaubt",
    "absolute_path_required": "Es wird ein absoluter Ordnerpfad benötigt",
    "folder_not_found": "Ordner wurde nicht gefunden",
    "path_not_folder": "Pfad ist kein Ordner",
    "folder_not_readable": "Ordner ist nicht lesbar",
    "folder_accessible": "Ordner erreichbar",
    "path_unavailable": "Ordnerpfad nicht erreichbar",
    "no_sync_admin": "Kein Admin mit Upload-Rechten für FileSync gefunden",
    "sync_done": "Synchronisierung abgeschlossen",
    "no_changes": "Keine Änderungen gefunden",
    "sync_failed": "Synchronisierung fehlgeschlagen",
}


class FileSyncService:
    def __init__(self, app):
        self._app = app
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = None
        FILESYNC_DIR.mkdir(parents=True, exist_ok=True)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="filesync-worker",
            daemon=True,
        )
        self._thread.start()

    def notify_config_changed(self):
        self._wake_event.set()

    def supported_file_types(self) -> list[str]:
        types = []
        for page in self._file_index_pages():
            for file_type in getattr(page, "_supported_file_types", []):
                normalized = self._normalize_ext(file_type)
                if normalized and normalized not in types:
                    types.append(normalized)
        return sorted(types)

    def is_admin_user(self, user_id) -> bool:
        if not self._app.f_user_management:
            return True
        if not user_id:
            return False
        with Session(engine) as session:
            actor = get_access_context(session, user_id)
            return bool(actor and actor.is_admin)

    def team_choices(self, user_id) -> list[tuple[str, str]]:
        if not self.is_admin_user(user_id):
            return []
        with Session(engine) as session:
            return [(team.name, team.id) for team in list_teams(session)]

    def load_ui_state(self, user_id):
        config = self.load_config()
        status = self.load_runtime_state().get("status", {})
        mapping = self._sanitize_folder_team_map(config.get("folder_team_map", {}))
        folder_entries = self._folder_entries(config.get("local_folder_path", ""))
        folder_choices = [(entry["label"], entry["key"]) for entry in folder_entries]
        selected_folder = folder_entries[0]["key"] if folder_entries else None
        team_choices = self.team_choices(user_id)
        selected_teams = mapping.get(selected_folder, []) if selected_folder else []

        return (
            config.get("local_folder_path", ""),
            config.get("scan_interval_minutes", 5),
            gr.update(
                choices=self.supported_file_types(),
                value=config.get("file_type_filter", self.supported_file_types()),
            ),
            mapping,
            folder_entries,
            gr.update(choices=folder_choices, value=selected_folder),
            gr.update(choices=team_choices, value=selected_teams),
            self._mapping_preview_df(folder_entries, mapping),
            bool(status.get("path_accessible", False)),
            status.get("last_scan_timestamp", ""),
            status.get("last_successful_sync", ""),
            int(status.get("processed_files_count", 0) or 0),
            status.get("last_status", ""),
        )

    def test_path_ui(self, user_id, folder_path, folder_team_map):
        path_ok, message, _ = self._validate_folder_path(folder_path)
        mapping = self._sanitize_folder_team_map(folder_team_map)
        folder_entries = self._folder_entries(folder_path) if path_ok else []
        folder_choices = [(entry["label"], entry["key"]) for entry in folder_entries]
        selected_folder = folder_entries[0]["key"] if folder_entries else None
        team_choices = self.team_choices(user_id)
        selected_teams = mapping.get(selected_folder, []) if selected_folder else []

        return (
            folder_entries,
            mapping,
            gr.update(choices=folder_choices, value=selected_folder),
            gr.update(choices=team_choices, value=selected_teams),
            self._mapping_preview_df(folder_entries, mapping),
            path_ok,
            message,
        )

    def load_folder_team_selection(self, selected_folder, folder_team_map, user_id):
        mapping = self._sanitize_folder_team_map(folder_team_map)
        return gr.update(
            choices=self.team_choices(user_id),
            value=mapping.get(selected_folder, []) if selected_folder else [],
        )

    def update_folder_team_mapping(
        self,
        selected_folder,
        selected_team_ids,
        folder_team_map,
        detected_folders,
        user_id,
    ):
        mapping = self._sanitize_folder_team_map(folder_team_map)
        if selected_folder:
            mapping[selected_folder] = self._normalize_team_ids(selected_team_ids)
        return mapping, self._mapping_preview_df(detected_folders or [], mapping)

    def save_config_ui(
        self,
        user_id,
        folder_path,
        scan_interval_minutes,
        file_type_filter,
        folder_team_map,
    ):
        if not self.is_admin_user(user_id):
            raise gr.Error("Nur Administratoren dürfen FileSync konfigurieren")

        path_ok, message, normalized_path = self._validate_folder_path(folder_path)
        if folder_path and not path_ok:
            raise gr.Error(message)

        filters = self._normalize_filters(file_type_filter)
        if not filters:
            filters = self.supported_file_types()

        folder_entries = self._folder_entries(normalized_path or folder_path) if path_ok else []
        valid_folder_keys = {entry["key"] for entry in folder_entries}
        mapping = self._sanitize_folder_team_map(folder_team_map, valid_folder_keys)
        config = self.load_config()
        config.update(
            {
                "local_folder_path": str(normalized_path) if normalized_path else "",
                "scan_interval_minutes": max(int(scan_interval_minutes or 5), 1),
                "file_type_filter": filters,
                "folder_team_map": mapping,
                "sync_user_id": user_id,
                "updated_at": _iso_now(),
            }
        )
        self._save_json(FILESYNC_CONFIG_PATH, config)

        state = self.load_runtime_state()
        status = state.setdefault("status", {})
        status["path_accessible"] = path_ok
        status["last_status"] = FILESYNC_MESSAGES["config_saved"]
        self._save_json(FILESYNC_STATE_PATH, state)
        self.notify_config_changed()
        return self.load_ui_state(user_id)

    def run_sync_now_ui(self, user_id):
        if not self.is_admin_user(user_id):
            raise gr.Error("Nur Administratoren dürfen FileSync ausführen")
        self.run_sync_once(user_id_override=user_id, manual=True)
        return self.load_ui_state(user_id)

    def load_runtime_state(self):
        return self._load_json(
            FILESYNC_STATE_PATH,
            {
                "files": {},
                "status": {
                    "path_accessible": False,
                    "last_scan_timestamp": "",
                    "last_successful_sync": "",
                    "processed_files_count": 0,
                    "last_status": "",
                },
            },
        )

    def load_config(self):
        config = self._default_config()
        stored = self._load_json(FILESYNC_CONFIG_PATH, {})
        config.update(stored)
        config["file_type_filter"] = self._normalize_filters(config.get("file_type_filter"))
        if not config["file_type_filter"]:
            config["file_type_filter"] = self.supported_file_types()
        config["scan_interval_minutes"] = max(
            int(config.get("scan_interval_minutes", 5) or 5), 1
        )
        config["folder_team_map"] = self._sanitize_folder_team_map(
            config.get("folder_team_map", {})
        )
        return config

    def run_sync_once(self, user_id_override=None, manual=False):
        if not self._lock.acquire(blocking=False):
            return
        try:
            config = self.load_config()
            state = self.load_runtime_state()
            status = state.setdefault("status", {})
            status["last_scan_timestamp"] = _iso_now()

            path_ok, message, normalized_path = self._validate_folder_path(
                config.get("local_folder_path", "")
            )
            status["path_accessible"] = path_ok
            if not path_ok:
                status["last_status"] = message or FILESYNC_MESSAGES["path_unavailable"]
                self._save_json(FILESYNC_STATE_PATH, state)
                return

            sync_user_id = user_id_override or config.get("sync_user_id") or self._resolve_sync_user_id()
            if not sync_user_id:
                status["last_status"] = "Kein Admin mit Upload-Rechten für FileSync gefunden"
                self._save_json(FILESYNC_STATE_PATH, state)
                return

            settings = self._settings_for_user(sync_user_id)
            filters = set(self._normalize_filters(config.get("file_type_filter")))
            folder_team_map = self._sanitize_folder_team_map(config.get("folder_team_map", {}))
            tracked_files = state.setdefault("files", {})
            current_paths = set()
            processed_files_count = 0
            group_file_ids: dict[tuple[int, str], list[str]] = {}
            group_team_ids: dict[tuple[int, str], list[str]] = {}
            group_order: dict[tuple[int, str], str] = {}

            for group_key, file_path in self._iter_candidate_files(normalized_path, filters):
                current_paths.add(file_path)
                page = self._page_for_file(file_path)
                if page is None:
                    continue

                record_key = self._record_key(file_path)
                previous = tracked_files.get(record_key, {})
                current_stat = file_path.stat()
                current_meta = {
                    "mtime_ns": current_stat.st_mtime_ns,
                    "size": current_stat.st_size,
                    "group_key": group_key,
                    "index_id": page._index.id,
                }
                changed = (
                    previous.get("mtime_ns") != current_meta["mtime_ns"]
                    or previous.get("size") != current_meta["size"]
                    or previous.get("index_id") != current_meta["index_id"]
                    or previous.get("group_key") != current_meta["group_key"]
                )
                source_ids = previous.get("source_ids", [])
                current_hash = previous.get("hash", "")
                if changed:
                    current_hash = self._hash_file(file_path)
                    if current_hash == previous.get("hash") and source_ids:
                        changed = False

                if changed:
                    logger.info("FileSync processing %s", file_path)
                    new_source_ids = self._run_upload(
                        page=page,
                        file_path=file_path,
                        user_id=sync_user_id,
                        settings=settings,
                        reindex=bool(source_ids),
                        document_team_ids=folder_team_map.get(group_key, []),
                    )
                    if new_source_ids:
                        source_ids = new_source_ids
                    processed_files_count += 1

                if not source_ids:
                    continue

                tracked_files[record_key] = {
                    **current_meta,
                    "hash": current_hash,
                    "source_ids": source_ids,
                }

                grouping_key = (page._index.id, group_key)
                group_file_ids.setdefault(grouping_key, [])
                for source_id in source_ids:
                    if source_id not in group_file_ids[grouping_key]:
                        group_file_ids[grouping_key].append(source_id)
                group_team_ids[grouping_key] = folder_team_map.get(group_key, [])
                group_order[grouping_key] = self._group_label(group_key)

            removed_paths = set(tracked_files.keys()) - {self._record_key(path) for path in current_paths}
            for record_key in removed_paths:
                tracked_files.pop(record_key, None)

            for page in self._file_index_pages():
                for grouping_key, file_ids in group_file_ids.items():
                    if grouping_key[0] != page._index.id:
                        continue
                    group_key = grouping_key[1]
                    team_ids = group_team_ids.get(grouping_key, [])
                    page._apply_document_teams(file_ids, sync_user_id, team_ids)
                    self._save_group_for_page(
                        page=page,
                        user_id=sync_user_id,
                        group_key=group_key,
                        group_label=group_order[grouping_key],
                        file_ids=file_ids,
                        team_ids=team_ids,
                    )

            status["processed_files_count"] = processed_files_count
            status["last_status"] = (
                "Synchronisierung abgeschlossen"
                if processed_files_count or manual
                else "Keine Änderungen gefunden"
            )
            status["last_successful_sync"] = _iso_now()
            self._save_json(FILESYNC_STATE_PATH, state)
        except Exception as exc:
            logger.exception("FileSync failed")
            state = self.load_runtime_state()
            status = state.setdefault("status", {})
            status["last_scan_timestamp"] = _iso_now()
            status["last_status"] = f"{FILESYNC_MESSAGES['sync_failed']}: {exc}"
            self._save_json(FILESYNC_STATE_PATH, state)
        finally:
            self._lock.release()

    def _scheduler_loop(self):
        while not self._stop_event.is_set():
            config = self.load_config()
            if config.get("local_folder_path"):
                self.run_sync_once()
            timeout = max(int(config.get("scan_interval_minutes", 5) or 5), 1) * 60
            if self._wake_event.wait(timeout):
                self._wake_event.clear()

    def _default_config(self):
        return {
            "local_folder_path": "",
            "scan_interval_minutes": 5,
            "file_type_filter": self.supported_file_types(),
            "folder_team_map": {},
            "sync_user_id": None,
            "updated_at": "",
        }

    def _load_json(self, path: Path, default):
        if not path.exists():
            return deepcopy(default)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load FileSync JSON %s", path)
            return deepcopy(default)

    def _save_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _normalize_ext(self, file_type):
        if not file_type:
            return ""
        ext = str(file_type).strip().lower()
        if not ext:
            return ""
        return ext if ext.startswith(".") else f".{ext}"

    def _normalize_filters(self, filters):
        normalized = []
        for file_type in filters or []:
            ext = self._normalize_ext(file_type)
            if ext and ext not in normalized:
                normalized.append(ext)
        return normalized

    def _normalize_team_ids(self, team_ids):
        normalized = []
        for team_id in team_ids or []:
            value = str(team_id).strip()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def _sanitize_folder_team_map(self, folder_team_map, valid_folder_keys=None):
        cleaned = {}
        valid_folder_keys = set(valid_folder_keys or [])
        use_filter = bool(valid_folder_keys)
        for folder_key, team_ids in (folder_team_map or {}).items():
            key = str(folder_key).strip()
            if not key:
                continue
            if use_filter and key not in valid_folder_keys:
                continue
            cleaned[key] = self._normalize_team_ids(team_ids)
        return cleaned

    def _validate_folder_path(self, folder_path):
        path_str = str(folder_path or "").strip()
        if not path_str:
            return False, FILESYNC_MESSAGES["path_missing"], None
        if path_str.startswith(("http://", "https://", "\\\\")):
            return False, FILESYNC_MESSAGES["local_paths_only"], None
        path = Path(path_str)
        if not path.is_absolute():
            return False, "Es wird ein absoluter Ordnerpfad benötigt", None
        try:
            resolved = path.resolve(strict=True)
        except Exception:
            return False, FILESYNC_MESSAGES["folder_not_found"], None
        if not resolved.is_dir():
            return False, FILESYNC_MESSAGES["path_not_folder"], None
        if not os.access(resolved, os.R_OK):
            return False, FILESYNC_MESSAGES["folder_not_readable"], None
        return True, FILESYNC_MESSAGES["folder_accessible"], resolved

    def _folder_entries(self, folder_path):
        path_ok, _, resolved = self._validate_folder_path(folder_path)
        if not path_ok or resolved is None:
            return []
        entries = []
        root_files = [item for item in resolved.iterdir() if item.is_file()]
        subfolders = sorted(
            [item for item in resolved.iterdir() if item.is_dir()],
            key=lambda item: item.name.lower(),
        )
        if root_files or not subfolders:
            entries.append(
                {
                    "key": DEFAULT_GROUP_KEY,
                    "label": DEFAULT_GROUP_LABEL,
                    "path": str(resolved),
                }
            )
        for folder in subfolders:
            entries.append({"key": folder.name, "label": folder.name, "path": str(folder)})
        return entries

    def _mapping_preview_df(self, folder_entries, mapping):
        folder_entries = folder_entries or []
        with Session(engine) as session:
            team_name_map = {team.id: team.name for team in list_teams(session)}
        rows = []
        for entry in folder_entries:
            team_names = [team_name_map.get(team_id, team_id) for team_id in mapping.get(entry["key"], [])]
            rows.append(
                {
                    "Ordner": entry["label"],
                    "Teams": ", ".join(team_names) if team_names else "-",
                }
            )
        if not rows:
            rows = [{"Ordner": "-", "Teams": "-"}]
        return pd.DataFrame.from_records(rows)

    def _file_index_pages(self):
        pages = []
        for index in self._app.index_manager.indices:
            page = getattr(self._app, f"_index_{index.id}", None)
            if page is not None and hasattr(page, "index_fn") and hasattr(page, "save_group"):
                pages.append(page)
        return pages

    def _page_for_file(self, file_path: Path):
        ext = self._normalize_ext(file_path.suffix)
        for page in self._file_index_pages():
            supported = {
                self._normalize_ext(file_type)
                for file_type in getattr(page, "_supported_file_types", [])
            }
            if ext in supported:
                return page
        return None

    def _iter_candidate_files(self, root_path: Path, filters: set[str]):
        root_files = sorted([item for item in root_path.iterdir() if item.is_file()])
        for file_path in root_files:
            if self._normalize_ext(file_path.suffix) in filters:
                yield DEFAULT_GROUP_KEY, file_path

        subfolders = sorted([item for item in root_path.iterdir() if item.is_dir()])
        for folder in subfolders:
            for file_path in sorted([item for item in folder.rglob("*") if item.is_file()]):
                if self._normalize_ext(file_path.suffix) in filters:
                    yield folder.name, file_path

    def _hash_file(self, file_path: Path):
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _record_key(self, file_path: Path):
        return str(file_path.resolve()).lower()

    def _settings_for_user(self, user_id):
        settings_payload = self._app.default_settings.flatten()
        with Session(engine) as session:
            stored = session.exec(select(Settings).where(Settings.user == user_id)).first()
            if stored:
                settings_payload = stored.setting
        return settings_payload

    def _resolve_sync_user_id(self):
        if not self._app.f_user_management:
            return "default"
        with Session(engine) as session:
            for user in session.exec(select(User)).all():
                actor = get_access_context(session, user.id)
                if actor and actor.is_admin and has_upload_access(actor):
                    return user.id
        return None

    def _run_upload(self, page, file_path: Path, user_id, settings, reindex, document_team_ids):
        iterator = page.index_fn(
            [str(file_path)],
            [],
            reindex,
            deepcopy(settings),
            user_id,
            document_team_ids,
        )
        try:
            while True:
                next(iterator)
        except StopIteration as stop:
            return stop.value or []

    def _group_label(self, group_key):
        return DEFAULT_GROUP_LABEL if group_key == DEFAULT_GROUP_KEY else group_key

    def _sync_group_name(self, group_label):
        return group_label

    def _save_group_for_page(self, page, user_id, group_key, group_label, file_ids, team_ids):
        FileGroup = page._index._resources["FileGroup"]
        group_name = self._sync_group_name(group_label)
        legacy_group_name = f"{LEGACY_SYNC_GROUP_PREFIX}{group_label}"
        normalized_file_ids = list(dict.fromkeys(file_ids or []))
        normalized_team_ids = self._normalize_team_ids(team_ids)
        user_key = str(user_id)
        with Session(engine) as session:
            current_group = (
                session.query(FileGroup)
                .filter(
                    FileGroup.user == user_key,
                    FileGroup.name.in_([group_name, legacy_group_name]),
                )
                .first()
            )
            if current_group:
                current_group.name = group_name
                group_data = dict(current_group.data or {})
                group_data["files"] = normalized_file_ids
                group_data["team_ids"] = normalized_team_ids
                current_group.data = group_data
            else:
                current_group = FileGroup(
                    name=group_name,
                    data={
                        "files": normalized_file_ids,
                        "team_ids": normalized_team_ids,
                    },
                    user=user_key,
                )
            session.add(current_group)
            session.commit()
