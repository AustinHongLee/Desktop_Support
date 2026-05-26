from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import InstalledApplication  # noqa: E402
from launcher.ui.installed_app_picker_dialog import InstalledApplicationPickerDialog  # noqa: E402


class InstalledApplicationPickerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_picker_filters_and_returns_selected_application(self) -> None:
        tekla = InstalledApplication(
            id="installed_app:HKLM:Tekla",
            root_name="HKLM",
            registry_key=r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tekla",
            display_name="Tekla Structures 2026",
            display_version="2026.0",
            publisher="Trimble",
            install_location=r"C:\Program Files\Tekla Structures\2026.0",
        )
        cursor = InstalledApplication(
            id="installed_app:HKCU:Cursor",
            root_name="HKCU",
            registry_key=r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Cursor",
            display_name="Cursor",
            publisher="Anysphere",
            display_icon=r'"C:\Users\a0976\AppData\Local\Programs\cursor\Cursor.exe",0',
        )
        dialog = InstalledApplicationPickerDialog(applications=[tekla, cursor])

        self.assertEqual(dialog._table.rowCount(), 2)

        dialog._search.setText("trimble")
        QApplication.processEvents()

        self.assertEqual(dialog._table.rowCount(), 1)
        self.assertEqual(dialog.selected_application(), tekla)
        self.assertEqual(dialog.selected_application().analysis_target, r"C:\Program Files\Tekla Structures\2026.0")


if __name__ == "__main__":
    unittest.main()
