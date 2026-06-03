from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.shutdown_safety import FileRelationship, ShutdownBlocker, ShutdownSafetyReport  # noqa: E402
from launcher.ui.shutdown_safety_dialog import ShutdownSafetyDialog  # noqa: E402


class ShutdownSafetyDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_lists_blocker_and_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / ".runtime" / "logs" / "job.log"
            log.parent.mkdir(parents=True)
            log.write_text("hello", encoding="utf-8")
            report = ShutdownSafetyReport(
                project_root=str(root),
                scan_reason="test.ui",
                created_at="now",
                blockers=(
                    ShutdownBlocker(
                        id="process:123",
                        pid=123,
                        process_name="python.exe",
                        parent_pid=100,
                        command_summary=f"python --project-root {root}",
                        command_line=f"python --project-root {root}",
                        executable_path="C:/Python/python.exe",
                        started_at="2026-06-02T10:00:00+08:00",
                        job_id="job-123",
                        component="tests",
                        process_role="Worker process",
                        safe_to_kill="Caution",
                        reasons=("command line contains project root", "temp output incomplete"),
                        lock_files=(str(root / ".runtime" / "running" / "job-123_123.json"),),
                        temp_dirs=(str(root / ".runtime" / "temp" / "job-123"),),
                        input_files=(str(root / "in.txt"),),
                        output_files=(str(root / "out.txt"),),
                        log_files=(str(log),),
                        relationships=(
                            FileRelationship(
                                relation="produces",
                                source=str(root / "in.txt"),
                                target=str(root / "out.txt"),
                                job_id="job-123",
                            ),
                        ),
                        kill_consequence=("目前輸出檔可能不完整。",),
                        command_line_contains_project_root=True,
                    ),
                ),
            )

            dialog = ShutdownSafetyDialog(scan_reason="test.ui", report=report)

        item = dialog._tree.topLevelItem(0)
        self.assertEqual(item.text(0), "python.exe")
        self.assertEqual(item.text(1), "123")
        self.assertEqual(item.text(3), "Caution")
        self.assertIn("job-123", dialog._details.toPlainText())
        self.assertIn("目前輸出檔可能不完整", dialog._details.toPlainText())
        self.assertIn("produces", dialog._graph.toPlainText())


if __name__ == "__main__":
    unittest.main()
