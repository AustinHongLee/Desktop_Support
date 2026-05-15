from __future__ import annotations

from launcher.core.context_inbox import ContextInbox
from launcher.core.context_service import ContextService
from launcher.core.paths import plugin_root
from launcher.core.registry import ActionRegistry
from launcher.core.runner import ActionRunner
from launcher.core.state_store import AppStateStore
from launcher.ui.dock_window import DockWindow
from launcher.ui.tray import LauncherTray


class LauncherBootstrap:
    def create(self) -> tuple[DockWindow, LauncherTray]:
        registry = ActionRegistry(plugin_root())
        report = registry.load()
        if report.issues:
            print(f"Plugin load issues: {len(report.issues)}")
            for issue in report.issues:
                print(f"- {issue.path}: {issue.message}")
        dock = DockWindow(
            registry=registry,
            runner=ActionRunner(),
            context_service=ContextService(),
            context_inbox=ContextInbox(),
            state_store=AppStateStore(),
        )
        tray = LauncherTray(dock)
        return dock, tray
