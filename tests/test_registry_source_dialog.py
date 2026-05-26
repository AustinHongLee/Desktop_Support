from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import BLOCKED_LAYER, CleanupPlanItem  # noqa: E402
from launcher.ui.registry_source_dialog import RegistrySourceDialog, RegistryValueSnapshot  # noqa: E402


class RegistrySourceDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_lists_registry_values_and_selects_matched_value(self) -> None:
        item = CleanupPlanItem(
            id="registry:HKLM:Software\\Demo:InstallLocation",
            layer=BLOCKED_LAYER,
            kind="registry_value",
            label="HKLM\\Demo\\InstallLocation",
            action="需管理員清理",
            note="測試",
            checked_default=False,
            root_name="HKLM",
            registry_key="Software\\Demo",
            registry_value_name="InstallLocation",
            registry_value_data=r"C:\Demo",
        )
        values = [
            RegistryValueSnapshot(name="DisplayName", type_name="REG_SZ", data="Demo"),
            RegistryValueSnapshot(name="InstallLocation", type_name="REG_SZ", data=r"C:\Demo"),
        ]

        with patch("launcher.ui.registry_source_dialog.read_registry_values", return_value=values):
            dialog = RegistrySourceDialog(item)

        self.assertEqual(dialog._table.rowCount(), 2)
        self.assertEqual(dialog._table.item(1, 0).text(), "InstallLocation")
        self.assertEqual(dialog._table.selectedItems()[0].text(), "InstallLocation")

    def test_dialog_external_regedit_button_uses_registry_location(self) -> None:
        item = CleanupPlanItem(
            id="registry:HKCU:Software\\Demo:DisplayName",
            layer=BLOCKED_LAYER,
            kind="registry_value",
            label="HKCU\\Demo\\DisplayName",
            action="需管理員清理",
            note="測試",
            checked_default=False,
            root_name="HKCU",
            registry_key="Software\\Demo",
            registry_value_name="DisplayName",
            registry_value_data="Demo",
        )
        with patch("launcher.ui.registry_source_dialog.read_registry_values", return_value=[]):
            dialog = RegistrySourceDialog(item)
        captured: list[tuple[str, str]] = []

        with patch("launcher.ui.registry_source_dialog.open_registry_location", side_effect=lambda root, key: captured.append((root, key))):
            dialog.open_regedit()

        self.assertEqual(captured, [("HKCU", "Software\\Demo")])


if __name__ == "__main__":
    unittest.main()
