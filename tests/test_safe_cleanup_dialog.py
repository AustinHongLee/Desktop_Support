from __future__ import annotations

import os
import tempfile
import time
import unittest
from threading import Event
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.safe_cleanup import PROCESS_LAYER, REGISTRY_LAYER, SAFE_LAYER, CleanupPlan, CleanupPlanItem, OfficialUninstaller  # noqa: E402
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
                _wait_for_scan(dialog)

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
                _wait_for_scan(dialog)

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
                    _wait_for_scan(dialog)

        self.assertIn("應用程式執行檔", dialog._conclusion.text())
        labels = _tree_texts(dialog._info_tree)
        self.assertIn("疑似安裝資料夾", labels)
        self.assertIn("登錄檔候選", labels)

    def test_dialog_surfaces_official_uninstaller_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_root = root / "Programs" / "demo"
            app_root.mkdir(parents=True)
            target = app_root / "Demo.exe"
            target.write_text("x", encoding="utf-8")
            uninstaller = OfficialUninstaller(
                id="uninstaller:HKCU:Demo",
                root_name="HKCU",
                registry_key="Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Demo",
                display_name="Demo App",
                uninstall_command="uninstall.exe",
                match_reason="DisplayIcon 指向目標路徑",
                confidence=0.875,
            )

            with patch("launcher.core.safe_cleanup._official_uninstallers", return_value=[uninstaller]):
                with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                    dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))
                    _wait_for_scan(dialog)

        self.assertFalse(dialog._uninstall_panel.isHidden())
        self.assertIn("Demo App", dialog._uninstall_label.text())
        self.assertIn("官方解除安裝", _tree_texts(dialog._info_tree))
        self.assertIn("官方解除安裝 1", dialog._summary.text())

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
                _wait_for_scan(dialog)

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
                    _wait_for_scan(dialog)

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

    def test_dialog_accepts_typed_residue_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = root / "initial.txt"
            initial.write_text("x", encoding="utf-8")
            typed_target = Path("Tekla Structures 2026")
            captured: list[LauncherContext] = []

            dialog = SafeCleanupDialog(LauncherContext.from_paths([initial]))
            _wait_for_scan(dialog)

            def fake_build(context, *, cancel_token=None, progress=None) -> CleanupPlan:  # noqa: ANN001
                captured.append(context)
                if progress is not None:
                    progress("目標身分", 1, 1)
                return CleanupPlan(
                    targets=(typed_target,),
                    items=(
                        CleanupPlanItem(
                            id="target:typed",
                            layer=SAFE_LAYER,
                            kind="file",
                            label="typed",
                            action="無動作",
                            note="typed",
                            checked_default=False,
                        ),
                    ),
                    created_at=time.time(),
                )

            with patch("launcher.ui.safe_cleanup_dialog.build_cleanup_plan", side_effect=fake_build):
                dialog._target_path.setText(str(typed_target))
                dialog.analyze_typed_target()
                _wait_for_scan(dialog)

        self.assertEqual(captured[-1].files, (typed_target,))
        self.assertEqual(dialog._target_path.text(), str(typed_target))

    def test_dialog_shows_busy_state_before_background_scan_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "slow.txt"
            target.write_text("x", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))

                self.assertTrue(dialog._scan_active)
                self.assertFalse(dialog._apply_button.isEnabled())

                _wait_for_scan(dialog)

        self.assertFalse(dialog._scan_active)
        self.assertTrue(dialog._apply_button.isEnabled())
        self.assertIn("安全 1", dialog._summary.text())

    def test_apply_controls_disable_actions_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.txt"
            target.write_text("x", encoding="utf-8")

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))
                _wait_for_scan(dialog)

        dialog._set_apply_controls(True)

        self.assertFalse(dialog._apply_button.isEnabled())
        self.assertFalse(dialog._refresh_button.isEnabled())
        self.assertFalse(dialog._uninstall_button.isEnabled())

        dialog._set_apply_controls(False)

        self.assertTrue(dialog._apply_button.isEnabled())
        self.assertTrue(dialog._refresh_button.isEnabled())

    def test_cancel_scan_ignores_late_worker_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "late.txt"
            target.write_text("x", encoding="utf-8")
            started = Event()
            release = Event()
            late_plan = CleanupPlan(
                targets=(target,),
                items=(
                    CleanupPlanItem(
                        id="target:late",
                        layer=SAFE_LAYER,
                        kind="file",
                        label="late result",
                        action="移到隔離區",
                        note="should be ignored",
                        checked_default=True,
                        path=str(target),
                    ),
                ),
                created_at=time.time(),
            )

            def slow_build(_context, *, cancel_token=None, progress=None) -> CleanupPlan:  # noqa: ANN001
                started.set()
                while not release.is_set():
                    if cancel_token is not None and cancel_token.cancelled():
                        release.set()
                        raise RuntimeError("cancelled by token")
                    time.sleep(0.01)
                return late_plan

            with patch("launcher.ui.safe_cleanup_dialog.build_cleanup_plan", side_effect=slow_build):
                dialog = SafeCleanupDialog(LauncherContext.from_paths([target]))
                _wait_for_event(started)
                dialog.cancel_scan()
                release.set()
                _wait_for_scan(dialog)

        self.assertIn("分析已取消", dialog._summary.text())
        self.assertNotIn("late result", _tree_texts(dialog._tree))

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


def _wait_for_scan(dialog: SafeCleanupDialog) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        QApplication.processEvents()
        if not dialog._scan_active and not dialog._scan_threads:
            return
        time.sleep(0.01)
    raise AssertionError("SafeCleanupDialog background scan did not finish in time")


def _wait_for_event(event: Event) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        QApplication.processEvents()
        if event.is_set():
            return
        time.sleep(0.01)
    raise AssertionError("background worker did not start in time")


if __name__ == "__main__":
    unittest.main()
