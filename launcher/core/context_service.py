from __future__ import annotations

from pathlib import Path

from launcher.core.context_model import LauncherContext
from launcher.windows.explorer_context import get_active_explorer_context


class ContextService:
    """Collects context only when the UI asks for it."""

    def current_context(self) -> LauncherContext:
        explorer_context = get_active_explorer_context()
        if explorer_context is not None:
            return explorer_context
        return LauncherContext(folder=Path.cwd(), source="fallback.cwd")
