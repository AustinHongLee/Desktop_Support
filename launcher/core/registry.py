from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from launcher.core.action_model import ActionDefinition
from launcher.core.context_model import LauncherContext

_DEV_ONLY_ACTION_IDS = {"diagnostics.wait_cancel", "diagnostics.wait_timeout"}


@dataclass(frozen=True)
class PluginDefinition:
    id: str
    title: str
    path: Path


@dataclass(frozen=True)
class PluginLoadIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class RegistryLoadReport:
    plugin_count: int
    action_count: int
    issues: tuple[PluginLoadIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.issues


class ActionRegistry:
    def __init__(self, plugin_root: Path) -> None:
        self.plugin_root = plugin_root
        self.plugins: dict[str, PluginDefinition] = {}
        self.actions: dict[str, ActionDefinition] = {}
        self.last_report = RegistryLoadReport(plugin_count=0, action_count=0)

    def load(self) -> RegistryLoadReport:
        plugins: dict[str, PluginDefinition] = {}
        actions: dict[str, ActionDefinition] = {}
        issues: list[PluginLoadIssue] = []
        if not self.plugin_root.exists():
            report = RegistryLoadReport(plugin_count=0, action_count=0)
            self.plugins = plugins
            self.actions = actions
            self.last_report = report
            return report

        for plugin_path in sorted(path for path in self.plugin_root.iterdir() if path.is_dir()):
            plugin_file = plugin_path / "plugin.json"
            actions_file = plugin_path / "actions.json"
            if not plugin_file.exists() or not actions_file.exists():
                continue
            try:
                plugin = self._load_plugin(plugin_file, plugin_path)
            except Exception as exc:
                issues.append(PluginLoadIssue(plugin_file, f"plugin.json 讀取失敗：{exc}"))
                continue
            if plugin.id in plugins:
                issues.append(PluginLoadIssue(plugin_file, f"重複的 plugin id：{plugin.id}"))
                continue
            try:
                loaded_actions = self._load_actions(actions_file, plugin)
            except Exception as exc:
                issues.append(PluginLoadIssue(actions_file, f"actions.json 讀取失敗：{exc}"))
                continue
            plugins[plugin.id] = plugin
            for action in loaded_actions:
                if action.id in actions:
                    issues.append(PluginLoadIssue(actions_file, f"重複的 action id：{action.id}"))
                    continue
                actions[action.id] = action

        self.plugins = plugins
        self.actions = actions
        report = RegistryLoadReport(
            plugin_count=len(plugins),
            action_count=len(actions),
            issues=tuple(issues),
        )
        self.last_report = report
        return report

    def reload(self) -> RegistryLoadReport:
        return self.load()

    def all_actions(self) -> list[ActionDefinition]:
        return sorted(self.actions.values(), key=lambda action: (action.category, action.title))

    def visible_actions(self, *, developer_mode: bool) -> list[ActionDefinition]:
        actions = self.all_actions()
        if developer_mode:
            return actions
        return [action for action in actions if action.id not in _DEV_ONLY_ACTION_IDS]

    def matching_actions(self, context: LauncherContext) -> list[ActionDefinition]:
        return [action for action in self.all_actions() if action.matches(context)]

    def matching_visible_actions(self, context: LauncherContext, *, developer_mode: bool) -> list[ActionDefinition]:
        return [action for action in self.visible_actions(developer_mode=developer_mode) if action.matches(context)]

    @staticmethod
    def _load_plugin(plugin_file: Path, plugin_path: Path) -> PluginDefinition:
        data = json.loads(plugin_file.read_text(encoding="utf-8"))
        return PluginDefinition(
            id=str(data["id"]),
            title=str(data.get("title") or data["id"]),
            path=plugin_path,
        )

    @staticmethod
    def _load_actions(actions_file: Path, plugin: PluginDefinition) -> list[ActionDefinition]:
        data = json.loads(actions_file.read_text(encoding="utf-8"))
        actions = data.get("actions", data) if isinstance(data, dict) else data
        if not isinstance(actions, list):
            raise ValueError(f"actions.json must contain a list or an actions list: {actions_file}")
        return [ActionRegistry._action_from_item(action, plugin) for action in actions]

    @staticmethod
    def _action_from_item(action: Any, plugin: PluginDefinition) -> ActionDefinition:
        if not isinstance(action, dict):
            raise ValueError("action item must be an object")
        return ActionDefinition.from_dict(action, plugin_id=plugin.id, plugin_path=plugin.path)
