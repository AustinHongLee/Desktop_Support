from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.core.context_model import LauncherContext
from launcher.core.context_service import ContextService


class ContextServiceTests(unittest.TestCase):
    def test_current_context_uses_explorer_when_available(self) -> None:
        explorer_context = LauncherContext(folder=Path("C:/Engineering"), source="explorer.test")

        with patch("launcher.core.context_service.get_active_explorer_context", return_value=explorer_context):
            context = ContextService().current_context()

        self.assertEqual(context, explorer_context)

    def test_current_context_marks_cwd_as_fallback(self) -> None:
        with patch("launcher.core.context_service.get_active_explorer_context", return_value=None):
            context = ContextService().current_context()

        self.assertEqual(context.folder, Path.cwd())
        self.assertEqual(context.source, "fallback.cwd")


if __name__ == "__main__":
    unittest.main()

