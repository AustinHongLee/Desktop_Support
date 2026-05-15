from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.plugins.iso_tools.rename_plan import build_rename_plan  # noqa: E402
from launcher.plugins.rename_tools.rename_actions import RenameOperation  # noqa: E402
from launcher.ui.rename_plan_dialog import RenamePlanDialog  # noqa: E402


class RenamePlanDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_shows_plan_rows_and_can_write_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-001.pdf"
            plan = build_rename_plan([RenameOperation(source, target)])
            dialog = RenamePlanDialog(plan)

            self.assertIn("預計更名 1 個 PDF", dialog._summary.text())
            self.assertEqual(dialog._table.rowCount(), 1)
            self.assertEqual(dialog._table.item(0, 1).text(), "page_001.pdf")
            self.assertEqual(dialog._table.item(0, 2).text(), "101--PIPE-001.pdf")
            self.assertEqual(dialog._table.item(0, 3).text(), "將更名")

            export_path = folder / "plan.csv"
            dialog.write_csv(export_path)

            self.assertIn("101--PIPE-001.pdf", export_path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
