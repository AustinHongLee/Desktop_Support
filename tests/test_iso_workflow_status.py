from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import Workbook  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox  # noqa: E402
from pypdf import PdfWriter  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.plugins.iso_tools.iso_naming import IsoRecord  # noqa: E402
from launcher.plugins.iso_tools.serial_vision import SerialVisionResult  # noqa: E402
from launcher.ui.iso_pdf_naming_dialog import IsoPdfNamingDialog  # noqa: E402


class IsoWorkflowStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_workflow_chips_exist_in_header(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        chips = dialog.findChildren(QLabel, "WorkflowStepChip")

        self.assertEqual(len(chips), 5)
        self.assertEqual(chips[0].text(), "1 來源：未選")
        self.assertEqual(chips[0].property("state"), "empty")

    def test_workflow_chips_reflect_pages_and_iso_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "page_001.pdf").write_bytes(b"%PDF-1.4\n")
            (folder / "page_002.pdf").write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))

            dialog._records = [IsoRecord("1", "PIPE-A")]
            dialog._regenerate_names()

            self.assertEqual(dialog._workflow_source_chip.property("state"), "ready")
            self.assertIn("2 頁", dialog._workflow_source_chip.text())
            self.assertEqual(dialog._workflow_iso_chip.property("state"), "ready")
            self.assertIn("1 筆", dialog._workflow_iso_chip.text())

    def test_opening_workbench_auto_loads_xlsx_and_splits_single_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "combine.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_blank_page(width=72, height=72)
            with pdf.open("wb") as handle:
                writer.write(handle)

            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "ISO"
            sheet.append(["流水號", "圖號"])
            sheet.append(["1", "PIPE-A"])
            sheet.append(["2", "PIPE-B"])
            workbook.save(folder / "iso_list.xlsx")

            dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))

            self.assertEqual(dialog._page_folder, folder / "combine_pages")
            self.assertEqual(len(dialog._pdfs), 2)
            self.assertEqual(len(dialog._records), 2)
            self.assertEqual(dialog._workflow_source_chip.property("state"), "ready")
            self.assertEqual(dialog._workflow_iso_chip.property("state"), "ready")

    def test_problem_guidance_points_to_manual_edit_and_apply_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "page_001.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))

            dialog._records = [IsoRecord("1", "PIPE-A")]
            dialog._regenerate_names()
            dialog._set_review_issue(0, "信心太低 0.52")
            dialog._refresh_statuses()

            self.assertIn("sort/流水號", dialog._review_guidance_label.text())
            self.assertIn("確認此列", dialog._review_guidance_label.text())
            self.assertFalse(dialog._apply_rename_button.isEnabled())

            dialog._clear_review_issue(0)
            dialog._refresh_statuses()

            self.assertIn("套用更名", dialog._review_guidance_label.text())
            self.assertTrue(dialog._apply_rename_button.isEnabled())

    def test_user_can_adopt_low_confidence_detected_serial_after_confirming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "page_001.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))

            dialog._records = [IsoRecord("2", "PIPE-B")]
            dialog._regenerate_names()
            dialog._set_review_issue(0, "信心太低 0.50")
            result = SerialVisionResult("2", 0.50, "低信心測試")
            dialog._vision_results[pdf] = result
            dialog._set_vision_cell(0, result)
            dialog._table.setCurrentCell(0, 3)

            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                dialog._apply_detected_serial_to_row()

            self.assertEqual(dialog._table.item(0, 3).text(), "2")
            self.assertEqual(dialog._table.item(0, 4).text(), "PIPE-B")
            self.assertNotIn(pdf, dialog._review_issues)


if __name__ == "__main__":
    unittest.main()
