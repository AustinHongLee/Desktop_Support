from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.core.context_model import LauncherContext
from launcher.core.file_locks import close_locking_process, find_locking_processes, targets_from_context
from launcher.core.safe_cleanup import ScanCancelled, ScanCancelToken, _RunningProcess


class FileLocksTests(unittest.TestCase):
    def test_targets_from_context_prefers_files(self) -> None:
        context = LauncherContext.from_paths([Path("C:/Temp/a.txt")], folder=Path("C:/Temp"), source="test")

        self.assertEqual(targets_from_context(context), (Path("C:/Temp/a.txt"),))

    def test_find_locking_processes_merges_restart_manager_and_path_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "locked.txt"
            target.write_text("x", encoding="utf-8")
            rm_process = _RunningProcess(
                pid=123,
                name="editor.exe",
                path=Path("C:/Tools/editor.exe"),
                reason="Restart Manager",
            )
            path_process = _RunningProcess(
                pid=456,
                name="worker.exe",
                path=target,
                reason="path match",
            )

            with patch("launcher.core.file_locks._restart_manager_processes", return_value=[rm_process]):
                with patch("launcher.core.file_locks._matching_running_processes", return_value=[path_process]):
                    with patch("launcher.core.file_locks._can_close_process", return_value=(True, "")):
                        report = find_locking_processes((target,))

        self.assertEqual([process.pid for process in report.processes], [123, 456])
        self.assertTrue(all(process.can_close for process in report.processes))
        self.assertEqual(report.processes[0].locked_paths, (target,))
        self.assertEqual(report.scanned_resource_count, 1)

    def test_folder_targets_register_child_files_with_restart_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "pending"
            nested.mkdir()
            locked = nested / "report.docx"
            locked.write_text("x", encoding="utf-8")
            process = _RunningProcess(
                pid=321,
                name="WINWORD.EXE",
                path=Path("C:/Program Files/Microsoft Office/root/Office16/WINWORD.EXE"),
                reason="Restart Manager",
            )

            def rm_processes(files: list[Path]) -> list[_RunningProcess]:
                return [process] if files == [locked] else []

            with patch("launcher.core.file_locks._restart_manager_processes", side_effect=rm_processes):
                with patch("launcher.core.file_locks._matching_running_processes", return_value=[]):
                    with patch("launcher.core.file_locks._can_close_process", return_value=(True, "")):
                        report = find_locking_processes((root,))

        self.assertEqual([process.pid for process in report.processes], [321])
        self.assertEqual(report.processes[0].locked_paths, (locked,))
        self.assertGreaterEqual(report.scanned_resource_count, 1)

    def test_find_locking_processes_marks_blocked_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("x", encoding="utf-8")
            process = _RunningProcess(
                pid=4,
                name="System",
                path=None,
                reason="Restart Manager",
                app_type=1000,
            )

            with patch("launcher.core.file_locks._restart_manager_processes", return_value=[process]):
                with patch("launcher.core.file_locks._matching_running_processes", return_value=[]):
                    with patch("launcher.core.file_locks._can_close_process", return_value=(False, "系統程序")):
                        report = find_locking_processes((target,))

        self.assertEqual(report.can_close_count, 0)
        self.assertEqual(report.processes[0].close_block_reason, "系統程序")

    def test_program_files_desktop_app_can_be_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            program_files = root / "Program Files"
            app_path = program_files / "Tracker Software" / "PDF Editor" / "PDFXEdit.exe"
            process = _RunningProcess(
                pid=123,
                name="PDF-XChange Editor",
                path=app_path,
                reason="Windows 回報此程序可能正在使用目標檔案。",
            )
            target = root / "157.pdf"
            target.write_text("x", encoding="utf-8")

            with patch.dict(os.environ, {"ProgramFiles": str(program_files), "WINDIR": str(root / "Windows"), "SystemRoot": str(root / "Windows")}):
                with patch("launcher.core.file_locks._restart_manager_processes", return_value=[process]):
                    with patch("launcher.core.file_locks._matching_running_processes", return_value=[]):
                        report = find_locking_processes((target,))

        self.assertEqual(report.processes[0].can_close, True)
        self.assertEqual(report.processes[0].close_block_reason, "")

    def test_windows_process_path_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            windows = root / "Windows"
            process = _RunningProcess(
                pid=456,
                name="explorer.exe",
                path=windows / "explorer.exe",
                reason="path match",
            )
            target = root / "157.pdf"
            target.write_text("x", encoding="utf-8")

            with patch.dict(os.environ, {"WINDIR": str(windows), "SystemRoot": str(windows)}):
                with patch("launcher.core.file_locks._restart_manager_processes", return_value=[process]):
                    with patch("launcher.core.file_locks._matching_running_processes", return_value=[]):
                        report = find_locking_processes((target,))

        self.assertEqual(report.processes[0].can_close, False)
        self.assertIn("程序位於系統保護範圍", report.processes[0].close_block_reason)

    def test_close_locking_process_can_force_taskkill(self) -> None:
        with patch("launcher.core.file_locks.sys.platform", "win32"):
            with patch("launcher.core.file_locks.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stderr = ""
                run.return_value.stdout = ""
                with patch("launcher.core.file_locks._wait_for_process_exit") as wait:
                    close_locking_process(123, force=True)

        run.assert_called_once()
        self.assertIn("/F", run.call_args.args[0])
        wait.assert_called_once_with(123)

    def test_find_locking_processes_honors_cancel_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "locked.txt").write_text("x", encoding="utf-8")
            token = ScanCancelToken()
            token.cancel()

            with self.assertRaises(ScanCancelled):
                find_locking_processes((root,), cancel_token=token)


if __name__ == "__main__":
    unittest.main()
