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
from launcher.core.safe_cleanup import PROCESS_LAYER, REGISTRY_LAYER, CleanupPlanItem  # noqa: E402
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
        self.assertEqual(dialog._target_path.text(), str(target))
        self.assertIn("a.txt", dialog._identity.text())
        self.assertGreater(dialog._info_tree.topLevelItemCount(), 0)
        first_child = dialog._tree.topLevelItem(0).child(0)
        self.assertEqual(first_child.checkState(0), Qt.CheckState.Checked)

    def test_dialog_info_tree_summarizes_related_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "ABC.pdf"
            related = root / "ABC_page_001.pdf"
            target.write_text("x", encoding="utf-8")
            related.write_text("y", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))

        labels = _tree_texts(dialog._info_tree)
        self.assertIn("目標身分", labels)
        self.assertIn("關聯資訊", labels)
        self.assertIn("同名 / 衍生檔", labels)
        self.assertIn("ABC_page_001.pdf", labels)

    def test_dialog_conclusion_identifies_app_executable_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_root = root / "Programs" / "cursor"
            app_root.mkdir(parents=True)
            target = app_root / "Cursor.exe"
            target.write_text("x", encoding="utf-8")
            registry_item = CleanupPlanItem(
                id="registry:HKCU:x:DisplayIcon",
                layer=REGISTRY_LAYER,
                kind="registry_value",
                label="HKCU\\Cursor\\DisplayIcon",
                action="刪除登錄值",
                note="測試",
                checked_default=False,
                root_name="HKCU",
                registry_key="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Cursor",
                registry_value_name="DisplayIcon",
                registry_value_data=str(target),
            )

            with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[registry_item]):
                    dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))

        self.assertIn("應用程式執行檔", dialog._conclusion.text())
        labels = _tree_texts(dialog._info_tree)
        self.assertIn("疑似安裝資料夾", labels)
        self.assertIn("登錄檔候選", labels)

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

    def test_process_items_are_disabled_until_close_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "app.exe"
            target.write_text("x", encoding="utf-8")
            process_item = CleanupPlanItem(
                id="process:123",
                layer=PROCESS_LAYER,
                kind="running_process",
                label="app.exe (PID 123)",
                action="嘗試關閉程序",
                note="程序執行檔就是目前目標。",
                checked_default=False,
                process_id=123,
                process_name="app.exe",
                process_path=str(target),
                can_close=True,
            )

            with patch("launcher.core.safe_cleanup._running_process_items", return_value=[process_item]):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))

        process_child = None
        for index in range(dialog._tree.topLevelItemCount()):
            group = dialog._tree.topLevelItem(index)
            if "執行中" in group.text(0):
                process_child = group.child(0)
                break
        self.assertIsNotNone(process_child)
        assert process_child is not None
        self.assertFalse(bool(process_child.flags() & Qt.ItemFlag.ItemIsEnabled))

        dialog._include_process.setChecked(True)

        self.assertTrue(bool(process_child.flags() & Qt.ItemFlag.ItemIsEnabled))
        self.assertIn("執行中", dialog._summary.text())

def _tree_texts(tree) -> set[str]:  # noqa: ANN001
    texts: set[str] = set()
    for top_index in range(tree.topLevelItemCount()):
        _collect_item_texts(tree.topLevelItem(top_index), texts)
    return texts


def _collect_item_texts(item, texts: set[str]) -> None:  # noqa: ANN001
    for column in range(item.columnCount()):
        text = item.text(column)
        if text:
            texts.add(text)
    for index in range(item.childCount()):
        _collect_item_texts(item.child(index), texts)


if __name__ == "__main__":
    unittest.main()
