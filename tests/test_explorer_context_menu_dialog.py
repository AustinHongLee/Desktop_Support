from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.ui.explorer_context_menu_dialog import ExplorerContextMenuDialog  # noqa: E402
from launcher.windows.context_menu_registry import CONTEXT_MENU_TARGETS, ContextMenuTargetStatus, ExplorerContextMenuStatus  # noqa: E402


class ExplorerContextMenuDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_renders_status_without_touching_registry(self) -> None:
        target = CONTEXT_MENU_TARGETS[0]
        status = ExplorerContextMenuStatus(
            pythonw=Path("C:/Tool/.venv/Scripts/pythonw.exe"),
            pythonw_exists=True,
            targets=(ContextMenuTargetStatus(target, True, "expected", "expected", True),),
        )

        with patch("launcher.ui.explorer_context_menu_dialog.context_menu_status", return_value=status):
            dialog = ExplorerContextMenuDialog()

        self.assertIn("已安裝", dialog._summary.text())
        self.assertIn("檔案：正確", dialog._detail.toPlainText())


if __name__ == "__main__":
    unittest.main()
