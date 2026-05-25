from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.ui.explorer_context_menu_dialog import ExplorerContextMenuDialog, _resolved_icon_path  # noqa: E402
from launcher.windows.context_menu_registry import (  # noqa: E402
    CONTEXT_MENU_TARGETS,
    ContextMenuEntry,
    ContextMenuLocation,
    ContextMenuTargetStatus,
    ExplorerContextMenuStatus,
)


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
        entry = ContextMenuEntry(
            id="HKCU|shell|Software\\Classes\\Directory\\Background\\shell\\Code",
            label="使用 Visual Studio 開啟",
            key_name="Code",
            root_name="HKCU",
            root_handle=object(),
            location=ContextMenuLocation("資料夾空白處", "Software\\Classes\\Directory\\Background\\shell", "shell"),
            key_path="Software\\Classes\\Directory\\Background\\shell\\Code",
            kind="shell",
            enabled=True,
            editable=True,
            command="code.exe",
        )

        with patch("launcher.ui.explorer_context_menu_dialog.context_menu_status", return_value=status):
            with patch("launcher.ui.explorer_context_menu_dialog.list_context_menu_entries", return_value=[entry]):
                dialog = ExplorerContextMenuDialog()

        self.assertEqual(dialog.windowTitle(), "右鍵登錄管理員")
        self.assertIn("掃描 1 項", dialog._summary.text())
        self.assertEqual(dialog._table.rowCount(), 1)
        self.assertEqual(dialog._table.item(0, 1).text(), "使用 Visual Studio 開啟")
        self.assertFalse(dialog._table.item(0, 0).icon().isNull())
        self.assertFalse(dialog._table.item(0, 1).icon().isNull())
        self.assertIn("Command / CLSID：code.exe", dialog._detail.toPlainText())

    def test_icon_path_parser_handles_quoted_exe_and_index(self) -> None:
        path = Path(__file__)

        resolved = _resolved_icon_path(f'"{path}",0 --flag')

        self.assertEqual(resolved, path)


if __name__ == "__main__":
    unittest.main()
