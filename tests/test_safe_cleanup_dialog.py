from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.safe_cleanup import REGISTRY_LAYER, CleanupPlanItem  # noqa: E402
from launcher.ui.safe_cleanup_dialog import SafeCleanupDialog  # noqa: E402


class SafeCleanupDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_renders_layers_and_default_safe_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.txt"
            target.write_text("x", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))

        self.assertEqual(dialog.windowTitle(), "安全清除工作台")
        self.assertIn("安全 1", dialog._summary.text())
        first_child = dialog._tree.topLevelItem(0).child(0)
        self.assertEqual(first_child.checkState(0), Qt.CheckState.Checked)

    def test_registry_items_are_disabled_until_high_risk_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "app.exe"
            target.write_text("x", encoding="utf-8")
            registry_item = CleanupPlanItem(
                id="registry:HKCU:x:InstallPath",
                layer=REGISTRY_LAYER,
                kind="registry_value",
                label="HKCU\\InstallPath",
                action="刪除登錄值",
                note="測試",
                checked_default=False,
                root_name="HKCU",
                registry_key="Software\\Demo",
                registry_value_name="InstallPath",
                registry_value_data=str(target),
            )

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[registry_item]):
                dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))

        registry_child = None
        for index in range(dialog._tree.topLevelItemCount()):
            group = dialog._tree.topLevelItem(index)
            if "登錄檔" in group.text(0):
                registry_child = group.child(0)
                break
        self.assertIsNotNone(registry_child)
        assert registry_child is not None
        self.assertFalse(bool(registry_child.flags() & Qt.ItemFlag.ItemIsEnabled))

        dialog._include_registry.setChecked(True)

        self.assertTrue(bool(registry_child.flags() & Qt.ItemFlag.ItemIsEnabled))


if __name__ == "__main__":
    unittest.main()
