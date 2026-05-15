from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from launcher.core.context_model import LauncherContext

SCHEMA_VERSION = 1
ISO_NAMING_PROFILE_LIMIT = 50
DEFAULT_THEME_NAME = "graphite-light"
SUPPORTED_THEME_NAMES = {"graphite-light", "engineering-blue-2"}


def default_state_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "EngineeringLauncher" / "state.json"
    return Path.home() / ".engineering_launcher" / "state.json"


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
        profiles = self._data.get("iso_naming_profiles", {})
        if not isinstance(profiles, dict):
            return None
        payload = profiles.get(_path_key(folder))
        return dict(payload) if isinstance(payload, dict) else None

    def set_iso_naming_profile(self, folder: Path, payload: dict[str, Any]) -> None:
        key = _path_key(folder)
        profiles = self._data.get("iso_naming_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        order = [str(item) for item in self._data.get("iso_naming_profile_order", [])]
        order = [key, *[item for item in order if item != key]][:ISO_NAMING_PROFILE_LIMIT]
        profiles[key] = dict(payload)
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
