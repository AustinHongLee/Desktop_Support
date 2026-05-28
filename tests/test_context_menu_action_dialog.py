from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

from launcher.ui.context_menu_action_dialog import ContextMenuActionDialog  # noqa: E402
from launcher.windows.context_menu_registry import ContextMenuEntry, ContextMenuLocation  # noqa: E402


class ContextMenuActionDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_default_template_builds_launcher_context_request(self) -> None:
        dialog = ContextMenuActionDialog()

        request = dialog.build_request()

        self.assertEqual(request.label, "送到工程工具列")
        self.assertIn("--set-context", request.command)
        self.assertEqual(request.target.label, "資料夾空白處")

    def test_iso_template_builds_direct_workbench_request(self) -> None:
        dialog = ContextMenuActionDialog()
        dialog._template_combo.setCurrentIndex(1)

        request = dialog.build_request()

        self.assertEqual(request.label, "ISO PDF 命名")
        self.assertIn("--open-iso-workbench", request.command)

    def test_safe_cleanup_template_builds_direct_workbench_request(self) -> None:
        dialog = ContextMenuActionDialog()
        dialog._template_combo.setCurrentIndex(2)

        request = dialog.build_request()

        self.assertEqual(request.label, "安全清除...")
        self.assertIn("--open-safe-cleanup", request.command)
        self.assertEqual(request.target.label, "檔案")

    def test_file_lock_template_builds_direct_workbench_request(self) -> None:
        dialog = ContextMenuActionDialog()
        dialog._template_combo.setCurrentIndex(3)

        request = dialog.build_request()

        self.assertEqual(request.label, "誰佔用這個檔案...")
        self.assertIn("--open-file-lock-checker", request.command)
        self.assertEqual(request.target.label, "檔案")

    def test_create_entry_uses_registry_request_and_accepts(self) -> None:
        dialog = ContextMenuActionDialog()
        entry = ContextMenuEntry(
            id="HKCU|shell|Software\\Classes\\*\\shell\\EngineeringLauncherCustom_Action",
            label="送到工程工具列",
            key_name="EngineeringLauncherCustom_Action",
            root_name="HKCU",
            root_handle=object(),
            location=ContextMenuLocation("檔案", "Software\\Classes\\*\\shell", "shell"),
            key_path="Software\\Classes\\*\\shell\\EngineeringLauncherCustom_Action",
            kind="shell",
            enabled=True,
            editable=True,
        )

        with patch("launcher.ui.context_menu_action_dialog.create_context_menu_entry", return_value=entry) as create:
            dialog._create_entry()

        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIs(dialog.created_entry, entry)
        create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
