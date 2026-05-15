from __future__ import annotations

import csv
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from launcher.plugins.iso_tools.rename_plan import build_rename_plan
from launcher.plugins.rename_tools.rename_actions import RenameOperation


class IsoRenamePlanTests(unittest.TestCase):
    def test_build_plan_exports_excel_friendly_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            target = folder / "101--PIPE-001.pdf"
            plan = build_rename_plan([RenameOperation(source, target)])

            rows = list(csv.DictReader(StringIO(plan.to_csv_text())))

            self.assertEqual(plan.operation_count, 1)
            self.assertEqual(plan.warning_count, 0)
            self.assertEqual(rows[0]["apply"], "YES")
            self.assertEqual(rows[0]["original_name"], "page_001.pdf")
            self.assertEqual(rows[0]["new_name"], "101--PIPE-001.pdf")
            self.assertEqual(rows[0]["status"], "ready")
            self.assertEqual(rows[0]["source_path"], str(source))
            self.assertEqual(rows[0]["target_path"], str(target))

    def test_review_issue_is_carried_into_plan_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_003.pdf"
            target = folder / "103--PIPE-003.pdf"
            plan = build_rename_plan(
                [RenameOperation(source, target)],
                review_issues={source: "ISO List 無此流水號：1037"},
            )

            self.assertEqual(plan.warning_count, 1)
            self.assertEqual(plan.rows[0].status, "warning")
            self.assertIn("1037", plan.to_csv_text())


if __name__ == "__main__":
    unittest.main()
