from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.core.context_model import LauncherContext
from launcher.core.paths import default_state_path as _default_state_path

SCHEMA_VERSION = 1
ISO_NAMING_PROFILE_LIMIT = 50
DEFAULT_THEME_NAME = "graphite-light"
SUPPORTED_THEME_NAMES = {"graphite-light", "graphite-dark", "engineering-blue-2"}


def default_state_path() -> Path:
    return _default_state_path()


@dataclass(frozen=True)
class RecentAction:
    action_id: str
    title: str
    category: str


class AppStateStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()
        self._data = self._load()

    @property
    def edge(self) -> str:
        return str(self._data.get("edge") or "top")

    @property
    def screen_name(self) -> str | None:
        name = self._data.get("screen_name")
        return str(name) if name else None

    @property
    def auto_hide_enabled(self) -> bool:
        return bool(self._data.get("auto_hide_enabled", True))

    @property
    def auto_hide_delay_ms(self) -> int:
        value = self._data.get("auto_hide_delay_ms", 1500)
        try:
            delay = int(value)
        except (TypeError, ValueError):
            return 1500
        return min(max(delay, 300), 10000)

    @property
    def developer_mode(self) -> bool:
        return bool(self._data.get("developer_mode", False))

    def tail_offset(self, edge: str) -> float:
        offsets = self._data.get("tail_offsets", {})
        if not isinstance(offsets, dict):
            return 0.5
        try:
            value = float(offsets.get(edge, 0.5))
        except (TypeError, ValueError):
            return 0.5
        return min(max(value, 0.0), 1.0)

    @property
    def theme_name(self) -> str:
        value = str(self._data.get("theme_name") or DEFAULT_THEME_NAME)
        return value if value in SUPPORTED_THEME_NAMES else DEFAULT_THEME_NAME

    def set_edge(self, edge: str) -> None:
        if edge not in {"top", "bottom", "left", "right"}:
            raise ValueError(f"Unsupported edge: {edge}")
        self._data["edge"] = edge
        self._save()

    def set_screen_name(self, screen_name: str | None) -> None:
        if screen_name:
            self._data["screen_name"] = screen_name
        else:
            self._data.pop("screen_name", None)
        self._save()

    def set_auto_hide_enabled(self, enabled: bool) -> None:
        self._data["auto_hide_enabled"] = enabled
        self._save()

    def set_auto_hide_delay_ms(self, delay_ms: int) -> None:
        self._data["auto_hide_delay_ms"] = min(max(int(delay_ms), 300), 10000)
        self._save()

    def set_tail_offset(self, edge: str, offset: float) -> None:
        if edge not in {"top", "bottom", "left", "right"}:
            raise ValueError(f"Unsupported edge: {edge}")
        offsets = self._data.get("tail_offsets", {})
        if not isinstance(offsets, dict):
            offsets = {}
        offsets[edge] = min(max(float(offset), 0.0), 1.0)
        self._data["tail_offsets"] = offsets
        self._save()

    def set_theme_name(self, theme_name: str) -> None:
        if theme_name not in SUPPORTED_THEME_NAMES:
            raise ValueError(f"Unsupported theme: {theme_name}")
        self._data["theme_name"] = theme_name
        self._save()

    def set_developer_mode(self, enabled: bool) -> None:
        self._data["developer_mode"] = bool(enabled)
        self._save()

    def set_dock_preferences(
        self,
        *,
        edge: str,
        screen_name: str | None,
        auto_hide_enabled: bool,
        auto_hide_delay_ms: int,
        theme_name: str | None = None,
        developer_mode: bool | None = None,
    ) -> None:
        if edge not in {"top", "bottom", "left", "right"}:
            raise ValueError(f"Unsupported edge: {edge}")
        if theme_name is not None and theme_name not in SUPPORTED_THEME_NAMES:
            raise ValueError(f"Unsupported theme: {theme_name}")
        self._data["edge"] = edge
        if screen_name:
            self._data["screen_name"] = screen_name
        else:
            self._data.pop("screen_name", None)
        self._data["auto_hide_enabled"] = auto_hide_enabled
        self._data["auto_hide_delay_ms"] = min(max(int(auto_hide_delay_ms), 300), 10000)
        if theme_name is not None:
            self._data["theme_name"] = theme_name
        if developer_mode is not None:
            self._data["developer_mode"] = bool(developer_mode)
        self._save()

    def recent_actions(self) -> list[RecentAction]:
        return [
            RecentAction(
                action_id=str(item.get("id")),
                title=str(item.get("title")),
                category=str(item.get("category")),
            )
            for item in self._data.get("recent_actions", [])
            if item.get("id")
        ]

    def record_action(self, action_id: str, title: str, category: str) -> None:
        item = {"id": action_id, "title": title, "category": category}
        self._data["recent_actions"] = _prepend_unique(
            self._data.get("recent_actions", []),
            item,
            key="id",
            limit=8,
        )
        self._save()

    def recent_contexts(self) -> list[LauncherContext]:
        contexts: list[LauncherContext] = []
        for item in self._data.get("recent_contexts", []):
            try:
                contexts.append(LauncherContext.from_payload(item))
            except Exception:
                continue
        return contexts

    def record_context(self, context: LauncherContext) -> None:
        if context.folder is None and not context.files:
            return
        if context.source == "fallback.cwd":
            return
        item = context.to_payload()
        key = _context_key(item)
        items = self._data.get("recent_contexts", [])
        items = [existing for existing in items if _context_key(existing) != key]
        self._data["recent_contexts"] = [item, *items][:10]
        if context.folder is not None:
            self._record_path("recent_folders", context.folder, limit=12)
        for file_path in reversed(context.files):
            self._record_path("recent_files", file_path, limit=16)
        self._save()

    def recent_folders(self) -> list[Path]:
        return [Path(path) for path in self._data.get("recent_folders", [])]

    def recent_files(self) -> list[Path]:
        return [Path(path) for path in self._data.get("recent_files", [])]

    def clear_recent_files(self) -> None:
        self._data["recent_files"] = []
        self._save()

    def clear_recent_folders(self) -> None:
        self._data["recent_folders"] = []
        self._save()

    def iso_naming_profile(self, folder: Path) -> dict[str, Any] | None:
        record = self._iso_naming_profile_record(folder)
        if record is None:
            return None
        published = record.get("published")
        return dict(published) if isinstance(published, dict) else None

    def iso_naming_profile_draft(self, folder: Path) -> dict[str, Any] | None:
        record = self._iso_naming_profile_record(folder)
        if record is None:
            return None
        draft = record.get("draft")
        return dict(draft) if isinstance(draft, dict) else None

    def iso_naming_profile_history(self, folder: Path) -> list[dict[str, Any]]:
        record = self._iso_naming_profile_record(folder)
        if record is None:
            return []
        history = record.get("history")
        return [dict(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []

    def set_iso_naming_profile(self, folder: Path, payload: dict[str, Any]) -> None:
        record = self._iso_naming_profile_record(folder) or _empty_iso_profile_record()
        current = record.get("published")
        if isinstance(current, dict) and current != payload:
            record["history"] = _prepend_profile_history(record.get("history"), current, event="publish")
        record["published"] = dict(payload)
        record["published_at"] = _now()
        record["draft"] = None
        record["draft_updated_at"] = None
        self._set_iso_naming_profile_record(folder, record)

    def set_iso_naming_profile_draft(self, folder: Path, payload: dict[str, Any]) -> None:
        record = self._iso_naming_profile_record(folder) or _empty_iso_profile_record()
        record["draft"] = dict(payload)
        record["draft_updated_at"] = _now()
        self._set_iso_naming_profile_record(folder, record)

    def publish_iso_naming_profile(self, folder: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self._iso_naming_profile_record(folder) or _empty_iso_profile_record()
        next_profile = dict(payload) if payload is not None else record.get("draft")
        if not isinstance(next_profile, dict):
            raise ValueError("沒有可發布的 ISO profile 草稿。")
        current = record.get("published")
        if isinstance(current, dict) and current != next_profile:
            record["history"] = _prepend_profile_history(record.get("history"), current, event="publish")
        record["published"] = dict(next_profile)
        record["published_at"] = _now()
        record["draft"] = None
        record["draft_updated_at"] = None
        self._set_iso_naming_profile_record(folder, record)
        return dict(next_profile)

    def revert_iso_naming_profile(self, folder: Path) -> dict[str, Any]:
        record = self._iso_naming_profile_record(folder)
        if record is None:
            raise ValueError("找不到可回復的 ISO profile。")
        history = record.get("history")
        if not isinstance(history, list) or not history:
            raise ValueError("沒有 ISO profile 歷史版本可回復。")
        previous = history.pop(0)
        previous_profile = previous.get("profile") if isinstance(previous, dict) else None
        if not isinstance(previous_profile, dict):
            raise ValueError("ISO profile 歷史版本格式不正確。")
        current = record.get("published")
        if isinstance(current, dict):
            history = _prepend_profile_history(history, current, event="revert_from")
        record["published"] = dict(previous_profile)
        record["published_at"] = _now()
        record["history"] = history[:ISO_NAMING_PROFILE_LIMIT]
        self._set_iso_naming_profile_record(folder, record)
        return dict(previous_profile)

    def _iso_naming_profile_record(self, folder: Path) -> dict[str, Any] | None:
        profiles = self._data.get("iso_naming_profiles", {})
        if not isinstance(profiles, dict):
            return None
        payload = profiles.get(_path_key(folder))
        if not isinstance(payload, dict):
            return None
        if _is_iso_profile_record(payload):
            return {
                "schema_version": 2,
                "published": dict(payload["published"]) if isinstance(payload.get("published"), dict) else None,
                "published_at": payload.get("published_at"),
                "draft": dict(payload["draft"]) if isinstance(payload.get("draft"), dict) else None,
                "draft_updated_at": payload.get("draft_updated_at"),
                "history": [dict(item) for item in payload.get("history", []) if isinstance(item, dict)],
            }
        return {
            "schema_version": 2,
            "published": dict(payload),
            "published_at": None,
            "draft": None,
            "draft_updated_at": None,
            "history": [],
        }

    def _set_iso_naming_profile_record(self, folder: Path, record: dict[str, Any]) -> None:
        key = _path_key(folder)
        profiles = self._data.get("iso_naming_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        order = [str(item) for item in self._data.get("iso_naming_profile_order", [])]
        order = [key, *[item for item in order if item != key]][:ISO_NAMING_PROFILE_LIMIT]
        profiles[key] = dict(record)
        self._data["iso_naming_profile_order"] = order
        self._data["iso_naming_profiles"] = {
            item: profiles[item] for item in order if item in profiles
        }
        self._save()

    def _record_path(self, list_key: str, path: Path, *, limit: int) -> None:
        value = str(path)
        items = [str(item) for item in self._data.get(list_key, []) if str(item) != value]
        self._data[list_key] = [value, *items][:limit]

    def _load(self) -> dict[str, Any]:
        try:
            if not self.path.exists():
                return {}
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._data["schema_version"] = SCHEMA_VERSION
            temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return


def _prepend_unique(
    items: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    key: str,
    limit: int,
) -> list[dict[str, Any]]:
    return [item, *[existing for existing in items if existing.get(key) != item.get(key)]][:limit]


def _context_key(item: dict[str, Any]) -> str:
    files = "|".join(str(path) for path in item.get("files", []))
    return f"{item.get('folder')}|{files}"


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve())


def _empty_iso_profile_record() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "published": None,
        "published_at": None,
        "draft": None,
        "draft_updated_at": None,
        "history": [],
    }


def _is_iso_profile_record(payload: dict[str, Any]) -> bool:
    return payload.get("schema_version") == 2 and any(key in payload for key in ("published", "draft", "history"))


def _prepend_profile_history(history: Any, profile: dict[str, Any], *, event: str) -> list[dict[str, Any]]:
    items = [dict(item) for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    return [
        {
            "event": event,
            "created_at": _now(),
            "profile": dict(profile),
        },
        *items,
    ][:ISO_NAMING_PROFILE_LIMIT]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
