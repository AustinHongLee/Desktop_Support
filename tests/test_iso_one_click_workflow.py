from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.plugins.iso_tools.serial_vision import SerialVisionResult  # noqa: E402
from launcher.ui.iso_pdf_naming_dialog import IsoPdfNamingDialog  # noqa: E402


class IsoOneClickWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_one_click_button_is_available_in_workbench(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        button = dialog.findChild(QPushButton, "OneClickDraftButton")

        self.assertIsNotNone(button)
        assert button is not None
        self.assertEqual(button.text(), "一鍵產生命名草稿")

    def test_one_click_button_click_is_signal_safe(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())
        button = dialog.findChild(QPushButton, "OneClickDraftButton")
        assert button is not None

        with patch.object(dialog, "_ensure_workflow_pdf_pages", return_value=False) as ensure_pages:
            button.click()

        ensure_pages.assert_called_once()

    def test_workflow_can_auto_load_nearby_iso_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "page_001.pdf").write_bytes(b"%PDF-1.4\n")
            (folder / "iso_list.csv").write_text("流水號,圖號\n1,PIPE-A\n", encoding="utf-8-sig")

            dialog = IsoPdfNamingDialog(LauncherContext(folder=folder, source="test"))
            dialog._records = []
            dialog._iso_list_path = None
            dialog._iso_table = None

            loaded = dialog._ensure_workflow_iso_records()

            self.assertTrue(loaded)
            self.assertEqual(len(dialog._records), 1)
            self.assertEqual(dialog._records[0].serial, "1")
            self.assertEqual(dialog._records[0].line_no, "PIPE-A")

    def test_workflow_uses_existing_split_pages_for_combine_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            combine = folder / "combine.pdf"
            combine.write_bytes(b"%PDF-1.4\n")
            pages = folder / "combine_pages"
            pages.mkdir()
            page = pages / "combine_p001.pdf"
            page.write_bytes(b"%PDF-1.4\n")

            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._combine_pdf = combine
            dialog._page_folder = pages
            dialog._pdfs = [combine]

            ready = dialog._ensure_workflow_pdf_pages()

            self.assertTrue(ready)
            self.assertEqual(dialog._page_folder, pages)
            self.assertEqual(dialog._pdfs, [page])

    def test_batch_completion_errors_are_reported_without_escaping_slot(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        with patch.object(dialog, "_handle_batch_detect_completed", side_effect=RuntimeError("boom")):
            with patch.object(QMessageBox, "critical") as critical:
                dialog._on_batch_detect_completed(False)

                critical.assert_not_called()
                QTest.qWait(150)

        critical.assert_called_once()
        self.assertIn("boom", dialog._terminal.toPlainText())

    def test_progress_update_survives_progress_dialog_closing_during_set_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [source]
            dialog._page_folder = folder
            dialog._load_rows()
            dialog._batch_record_lookup = {}
            dialog._batch_stats = {
                "total": 1,
                "processed": 0,
                "filled": 0,
                "low_confidence": [],
                "not_in_iso": [],
                "review_required": [],
                "failed": [],
            }
            dialog._batch_progress = _ClosingProgress(dialog)

            dialog._handle_batch_detect_progress(1, 1, source, SerialVisionResult("1", 0.93, "ok"))

            self.assertEqual(dialog._table.item(0, 3).text(), "1")
            self.assertEqual(dialog._batch_stats["filled"], 1)

    def test_batch_progress_updates_preview_without_running_preview_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "page_001.pdf"
            source.write_bytes(b"%PDF-1.4\n")
            dialog = IsoPdfNamingDialog(LauncherContext.empty())
            dialog._pdfs = [source]
            dialog._page_folder = folder
            with patch.object(dialog, "_show_pdf_preview"):
                dialog._load_rows()
            dialog._batch_record_lookup = {}
            dialog._batch_stats = {
                "total": 1,
                "processed": 0,
                "filled": 0,
                "low_confidence": [],
                "not_in_iso": [],
                "review_required": [],
                "failed": [],
            }
            dialog._preview_tabs.setCurrentIndex(1)

            with patch.object(dialog, "_show_pdf_preview") as show_preview:
                dialog._handle_batch_detect_progress(1, 1, source, SerialVisionResult("1", 0.93, "ok"))

            show_preview.assert_called_once_with(source, force_reload=True, detect=False)
            self.assertEqual(dialog._preview_tabs.currentIndex(), 0)
            self.assertEqual(dialog._table.currentRow(), 0)
            self.assertIn("批次預覽：1 / 1", dialog._preview_info.text())
            self.assertIn("結果：1  信心 0.93", dialog._preview_info.text())

    def test_one_click_opens_rename_plan_after_returning_to_event_loop(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        with patch.object(dialog, "_operations", return_value=[object()]):
            with patch("launcher.ui.iso_pdf_naming_dialog._validate_operations", return_value=None):
                with patch.object(dialog, "_execute") as execute:
                    dialog._finish_one_click_workflow(False, "完成", "", False)

                    execute.assert_not_called()
                    QTest.qWait(250)

        execute.assert_called_once()

class _ClosingProgress:
    def __init__(self, dialog: IsoPdfNamingDialog) -> None:
        self._dialog = dialog
        self.label_text = ""

    def setLabelText(self, text: str) -> None:
        self.label_text = text

    def setValue(self, _value: int) -> None:
        self._dialog._batch_progress = None


if __name__ == "__main__":
    unittest.main()
