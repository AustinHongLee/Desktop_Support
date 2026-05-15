from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from launcher.core.context_model import LauncherContext


@dataclass(frozen=True)
class ActionAccepts:
    extensions: frozenset[str] = field(default_factory=frozenset)
    min_files: int = 0
    max_files: int | None = None
    requires_folder: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ActionAccepts":
        data = data or {}
        extensions = frozenset(str(ext).lower() for ext in data.get("extensions", []))
        return cls(
            extensions=extensions,
            min_files=int(data.get("min_files", 0)),
            max_files=data.get("max_files"),
            requires_folder=bool(data.get("requires_folder", False)),
        )

    def matches(self, context: LauncherContext) -> bool:
        if self.requires_folder and context.folder is None:
            return False
        if context.file_count < self.min_files:
            return False
        if self.max_files is not None and context.file_count > int(self.max_files):
            return False
        if self.extensions and not context.files:
            return False
        if self.extensions:
            return all(path.suffix.lower() in self.extensions for path in context.files)
        return True


@dataclass(frozen=True)
class CommandSpec:
    type: str
    module: str | None = None
    entry: str | None = None
    executable: str | None = None
    args: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandSpec":
        return cls(
            type=str(data["type"]),
            module=data.get("module"),
            entry=data.get("entry"),
            executable=data.get("executable"),
            args=tuple(str(arg) for arg in data.get("args", [])),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "module": self.module,
            "entry": self.entry,
            "executable": self.executable,
            "args": list(self.args),
        }


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    title: str
    category: str
    command: CommandSpec
    plugin_id: str
    description: str = ""
    icon: str = "terminal"
    accepts: ActionAccepts = field(default_factory=ActionAccepts)
    risk: str = "low"
    plugin_path: Path | None = None
    timeout_seconds: float | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        plugin_id: str,
        plugin_path: Path,
    ) -> "ActionDefinition":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            category=str(data.get("category") or plugin_id),
            description=str(data.get("description") or ""),
            icon=str(data.get("icon") or "terminal"),
            accepts=ActionAccepts.from_dict(data.get("accepts")),
            command=CommandSpec.from_dict(data["command"]),
            risk=str(data.get("risk") or "low"),
            plugin_id=plugin_id,
            plugin_path=plugin_path,
            timeout_seconds=_optional_float(data.get("timeout_seconds")),
        )

    def matches(self, context: LauncherContext) -> bool:
        return self.accepts.matches(context)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "icon": self.icon,
            "risk": self.risk,
            "plugin_id": self.plugin_id,
            "plugin_path": str(self.plugin_path) if self.plugin_path else None,
            "timeout_seconds": self.timeout_seconds,
            "command": self.command.to_payload(),
        }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
