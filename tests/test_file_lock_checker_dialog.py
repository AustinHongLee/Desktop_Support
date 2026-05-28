from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.file_locks import FileLockReport, LockingProcess  # noqa: E402
from launcher.core.safe_cleanup import ScanCancelled  # noqa: E402
from launcher.ui.file_lock_checker_dialog import FileLockCheckerDialog, _LockScanWorker  # noqa: E402


class FileLockCheckerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_renders_locking_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "locked.txt"
            target.write_text("x", encoding="utf-8")
            report = FileLockReport(
                targets=(target,),
                processes=(
                    LockingProcess(
                        pid=123,
                        name="editor.exe",
                        path=Path("C:/Tools/editor.exe"),
                        reason="Windows 回報此程序可能正在使用目標檔案。",
                        can_close=True,
                        locked_paths=(target,),
                    ),
                ),
            )

            with patch("launcher.ui.file_lock_checker_dialog.find_locking_processes", return_value=report):
                dialog = FileLockCheckerDialog(LauncherContext.from_paths([target]))
                _wait_for_scan(dialog)

        self.assertEqual(dialog.windowTitle(), "檔案佔用檢查器")
        self.assertIn("找到 1 個", dialog._summary.text())
        item = dialog._tree.topLevelItem(0)
        self.assertEqual(item.text(0), "editor.exe")
        self.assertEqual(item.text(1), "123")
        self.assertEqual(item.text(4), str(target))
        self.assertTrue(dialog._normal_close_button.isEnabled())
        self.assertTrue(dialog._force_close_button.isEnabled())

    def test_dialog_disables_close_for_protected_processes(self) -> None:
        report = FileLockReport(
            targets=(Path("C:/Temp/locked.txt"),),
            processes=(
                LockingProcess(
                    pid=4,
                    name="System",
                    path=None,
                    reason="系統程序",
                    can_close=False,
                    close_block_reason="系統/服務/Explorer 類型",
                ),
            ),
        )

        with patch("launcher.ui.file_lock_checker_dialog.find_locking_processes", return_value=report):
            dialog = FileLockCheckerDialog(LauncherContext.from_paths([Path("C:/Temp/locked.txt")]))
            _wait_for_scan(dialog)

        self.assertEqual(dialog._tree.topLevelItem(0).text(2), "保留：系統/服務/Explorer 類型")
        self.assertFalse(dialog._normal_close_button.isEnabled())
        self.assertFalse(dialog._force_close_button.isEnabled())

    def test_copy_selected_path_uses_clipboard(self) -> None:
        report = FileLockReport(
            targets=(Path("C:/Temp/locked.txt"),),
            processes=(
                LockingProcess(
                    pid=123,
                    name="editor.exe",
                    path=Path("C:/Tools/editor.exe"),
                    reason="測試",
                    can_close=True,
                ),
            ),
        )

        with patch("launcher.ui.file_lock_checker_dialog.find_locking_processes", return_value=report):
            dialog = FileLockCheckerDialog(LauncherContext.from_paths([Path("C:/Temp/locked.txt")]))
            _wait_for_scan(dialog)
            dialog.copy_selected_path()

        self.assertEqual(QApplication.clipboard().text(), "C:\\Tools\\editor.exe")

    def test_worker_reports_cancelled_scan(self) -> None:
        emitted: list[bool] = []
        worker = _LockScanWorker((Path("C:/Temp/locked.txt"),))
        worker.cancelled.connect(lambda: emitted.append(True))

        with patch("launcher.ui.file_lock_checker_dialog.find_locking_processes", side_effect=ScanCancelled("cancelled")):
            worker.run()

        self.assertEqual(emitted, [True])


def _wait_for_scan(dialog: FileLockCheckerDialog) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        QApplication.processEvents()
        if dialog._scan_thread is None:
            return
        time.sleep(0.01)
    raise AssertionError("FileLockCheckerDialog background scan did not finish in time")


if __name__ == "__main__":
    unittest.main()
