from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from openpyxl import Workbook  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton, QTabWidget  # noqa: E402
from pypdf import PdfWriter  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.ui.iso_pdf_naming_dialog import IsoPdfNamingDialog  # noqa: E402


class IsoAutopilotPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_autopilot_page_is_first_tab_and_blocks_without_sources(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        tabs = dialog.findChild(QTabWidget, "WorkbenchModeTabs")
        run_button = dialog.findChild(QPushButton, "AutopilotRunButton")

        self.assertIsNotNone(tabs)
        self.assertIsNotNone(run_button)
        assert tabs is not None
        assert run_button is not None
        self.assertEqual(tabs.tabText(0), "一鍵頁")
        self.assertEqual(tabs.tabText(1), "進階工作台")
        self.assertFalse(run_button.isEnabled())
        self.assertIn("紅色", dialog._autopilot_summary.text())
        self.assertEqual(dialog._autopilot_status_rows["folder"][0].property("state"), "blocked")
        self.assertEqual(dialog._autopilot_status_rows["pdf"][0].property("state"), "blocked")
        self.assertEqual(dialog._autopilot_status_rows["iso"][0].property("state"), "blocked")

    def test_autopilot_page_allows_start_when_pdf_and_iso_are_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _write_pdf(folder / "combine.pdf", pages=2)
            _write_iso_list(folder / "iso_list.xlsx")

            with patch("launcher.ui.iso_pdf_naming_dialog.find_spec", return_value=object()):
                dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))

        run_button = dialog.findChild(QPushButton, "AutopilotRunButton")
        assert run_button is not None
        self.assertTrue(run_button.isEnabled())
        self.assertEqual(dialog._autopilot_status_rows["folder"][0].property("state"), "ready")
        self.assertEqual(dialog._autopilot_status_rows["pdf"][0].property("state"), "ready")
        self.assertEqual(dialog._autopilot_status_rows["iso"][0].property("state"), "ready")
        self.assertEqual(dialog._autopilot_status_rows["ocr"][0].property("state"), "ready")
        self.assertIn("一鍵處理", run_button.text())

    def test_autopilot_page_blocks_when_iso_list_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            _write_pdf(folder / "combine.pdf", pages=1)

            with patch("launcher.ui.iso_pdf_naming_dialog.find_spec", return_value=object()):
                dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))

        run_button = dialog.findChild(QPushButton, "AutopilotRunButton")
        assert run_button is not None
        self.assertFalse(run_button.isEnabled())
        self.assertEqual(dialog._autopilot_status_rows["iso"][0].property("state"), "blocked")
        self.assertIn("ISO List", dialog._autopilot_status_rows["iso"][1].text())


def _write_pdf(path: Path, *, pages: int) -> None:
    writer = PdfWriter()
    for _index in range(pages):
        writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_iso_list(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "ISO"
    sheet.append(["流水號", "圖號"])
    sheet.append(["1", "PIPE-A"])
    sheet.append(["2", "PIPE-B"])
    workbook.save(path)


if __name__ == "__main__":
    unittest.main()
