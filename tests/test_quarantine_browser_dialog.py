from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.safe_cleanup import apply_cleanup_plan, build_cleanup_plan  # noqa: E402
from launcher.ui.quarantine_browser_dialog import QuarantineBrowserDialog  # noqa: E402


class QuarantineBrowserDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_lists_quarantine_sessions_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "old.log"
            target.write_text("log", encoding="utf-8")
            quarantine = root / "quarantine"

            with patch("launcher.core.safe_cleanup._registry_reference_items", return_value=[]):
                plan = build_cleanup_plan(LauncherContext.from_paths([target]), state_path=root / "state.json")
            result = apply_cleanup_plan(plan, {plan.items[0].id}, quarantine_root=quarantine)

            dialog = QuarantineBrowserDialog(quarantine_root=quarantine)

        self.assertEqual(dialog.windowTitle(), "隔離區管理")
        self.assertEqual(dialog._session_table.rowCount(), 1)
        self.assertEqual(dialog._record_table.rowCount(), 1)
        self.assertIn("old.log", dialog._record_table.item(0, 1).text())
        self.assertEqual(dialog._sessions[0].path, result.quarantine_dir)


if __name__ == "__main__":
    unittest.main()
