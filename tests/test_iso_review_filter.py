from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.plugins.iso_tools.iso_naming import IsoRecord, build_record_lookup  # noqa: E402
from launcher.plugins.iso_tools.serial_vision import SerialVisionResult  # noqa: E402
from launcher.ui.iso_pdf_naming_dialog import IsoPdfNamingDialog, _review_issue_kind, _status_issue_kind  # noqa: E402


class IsoReviewFilterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_review_issue_kind_classifies_common_problems(self) -> None:
        self.assertEqual(_review_issue_kind("信心太低 0.62"), "low_confidence")
        self.assertEqual(_review_issue_kind("ISO List 無此流水號：1037"), "not_in_iso")
        self.assertEqual(_review_issue_kind("OCR 不一致：1037"), "correction")
        self.assertEqual(_review_issue_kind("ISO List 校正：1037 -> 103"), "correction")
        self.assertEqual(_review_issue_kind("圖號/檔名與 ISO List 不一致：101 應為 A"), "correction")
        self.assertEqual(_review_issue_kind("未判讀到流水號"), "missing")

    def test_status_issue_kind_classifies_non_ocr_table_problems(self) -> None:
        self.assertEqual(_status_issue_kind("命名重複", ""), "conflict")
        self.assertEqual(_status_issue_kind("目標已存在", ""), "conflict")
        self.assertEqual(_status_issue_kind("缺少命名", ""), "missing")
        self.assertEqual(_status_issue_kind("可更名", ""), "")

    def test_problem_filter_hides_clean_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.pdf"
            second = Path(tmp) / "second.pdf"
            first.write_bytes(b"%PDF-1.4\n")
            second.write_bytes(b"%PDF-1.4\n")

            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [first, second]
            dialog._review_issues = {second: "信心太低 0.62"}
            dialog._load_rows()
            dialog._table.blockSignals(True)
            dialog._table.item(0, 5).setText("first-renamed.pdf")
            dialog._table.item(1, 5).setText("second-renamed.pdf")
            dialog._table.blockSignals(False)
            dialog._refresh_statuses()

            dialog._problem_only_check.setChecked(True)

            self.assertTrue(dialog._table.isRowHidden(0))
            self.assertFalse(dialog._table.isRowHidden(1))
            self.assertIn("問題列：1 / 2", dialog._problem_summary_label.text())

    def test_search_filter_matches_visible_table_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.pdf"
            second = Path(tmp) / "second.pdf"
            first.write_bytes(b"%PDF-1.4\n")
            second.write_bytes(b"%PDF-1.4\n")

            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [first, second]
            dialog._load_rows()
            dialog._table.blockSignals(True)
            dialog._table.item(0, 5).setText("101--PIPE-A.pdf")
            dialog._table.item(1, 5).setText("102--PIPE-B.pdf")
            dialog._table.blockSignals(False)
            dialog._refresh_statuses()

            dialog._table_search.setText("PIPE-B")

            self.assertTrue(dialog._table.isRowHidden(0))
            self.assertFalse(dialog._table.isRowHidden(1))
            self.assertIn("顯示 1", dialog._problem_summary_label.text())

    def test_next_problem_button_moves_between_visible_problem_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "first.pdf"
            second = Path(tmp) / "second.pdf"
            third = Path(tmp) / "third.pdf"
            for path in (first, second, third):
                path.write_bytes(b"%PDF-1.4\n")

            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [first, second, third]
            dialog._review_issues = {
                second: "信心太低 0.62",
                third: "ISO List 無此流水號：999",
            }
            dialog._load_rows()
            dialog._table.blockSignals(True)
            for row, name in enumerate(("101--A.pdf", "102--B.pdf", "103--C.pdf")):
                dialog._table.item(row, 5).setText(name)
            dialog._table.blockSignals(False)
            dialog._refresh_statuses()

            dialog._table.setCurrentCell(0, 1)
            dialog._select_next_problem_row()
            self.assertEqual(dialog._table.currentRow(), 1)

            dialog._select_next_problem_row()
            self.assertEqual(dialog._table.currentRow(), 2)

            dialog._select_next_problem_row()
            self.assertEqual(dialog._table.currentRow(), 1)

            dialog._table_search.setText("third")
            dialog._table.setCurrentCell(0, 1)
            dialog._select_next_problem_row()
            self.assertEqual(dialog._table.currentRow(), 2)

    def test_iso_list_correction_is_not_an_unresolved_review_issue(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())
        issue = dialog._review_issue_for_result(
            SerialVisionResult("103", 0.95, "ISO List 校正：1037 -> 103；原始信心 0.92"),
            build_record_lookup([IsoRecord(serial="103", line_no="A")]),
        )

        self.assertEqual(issue, "")

    def test_manual_serial_edit_autofills_iso_line_and_clears_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "page_001.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [source]
            dialog._records = [IsoRecord(serial="101", line_no="PIPE-A")]
            dialog._review_issues = {source: "信心太低 0.62"}
            dialog._load_rows()

            dialog._table.item(0, 3).setText("101")

            self.assertEqual(dialog._table.item(0, 4).text(), "PIPE-A")
            self.assertEqual(dialog._table.item(0, 5).text(), "101--PIPE-A.pdf")
            self.assertNotIn(source, dialog._review_issues)

    def test_manual_serial_edit_to_unknown_iso_keeps_problem_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "page_001.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [source]
            dialog._records = [IsoRecord(serial="101", line_no="PIPE-A")]
            dialog._load_rows()

            dialog._table.item(0, 3).setText("999")

            self.assertIn("ISO List 無此流水號：999", dialog._review_issues[source])
            self.assertIn("需確認", dialog._table.item(0, 6).text())

    def test_manual_line_mismatch_keeps_problem_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "page_001.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [source]
            dialog._records = [IsoRecord(serial="101", line_no="PIPE-A")]
            dialog._load_rows()

            dialog._table.item(0, 3).setText("101")
            dialog._table.item(0, 4).setText("PIPE-B")

            self.assertIn("圖號/檔名與 ISO List 不一致", dialog._review_issues[source])
            self.assertIn("需確認", dialog._table.item(0, 6).text())


if __name__ == "__main__":
    unittest.main()
