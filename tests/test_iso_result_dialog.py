from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from launcher.ui.iso_pdf.result_dialog import IsoAutopilotResultDialog, IsoAutopilotResultSummary  # noqa: E402
from launcher.ui.theme import preferences_stylesheet  # noqa: E402


class IsoAutopilotResultDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_result_dialog_shows_metrics_and_actions(self) -> None:
        summary = IsoAutopilotResultSummary(
            total_pdfs=17,
            ready_count=16,
            warning_count=1,
            blocked_count=0,
            message="一鍵命名草稿已完成。",
            detail="第 3 列需要確認",
            can_open_rename_plan=True,
            can_view_problems=True,
        )

        dialog = IsoAutopilotResultDialog(summary)
        labels = {label.text() for label in dialog.findChildren(QLabel)}
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}

        self.assertIn("17", labels)
        self.assertIn("16", labels)
        self.assertIn("需確認", labels)
        self.assertTrue(buttons["開啟更名確認"].isEnabled())
        self.assertTrue(buttons["查看問題列"].isEnabled())

    def test_result_dialog_disables_unavailable_actions(self) -> None:
        summary = IsoAutopilotResultSummary(
            total_pdfs=0,
            ready_count=0,
            warning_count=0,
            blocked_count=1,
            message="資料夾沒有 PDF。",
            detail="",
        )

        dialog = IsoAutopilotResultDialog(summary)
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}

        self.assertFalse(buttons["開啟更名確認"].isEnabled())
        self.assertFalse(buttons["查看問題列"].isEnabled())

    def test_preferences_stylesheet_includes_result_metric_rules(self) -> None:
        stylesheet = preferences_stylesheet()

        self.assertIn("QFrame#ResultMetric", stylesheet)
        self.assertIn("QLabel#ResultMetricValue", stylesheet)


if __name__ == "__main__":
    unittest.main()
