from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import REVIEW_LAYER, CleanupEvidence, CleanupPlanItem, ItemImpact  # noqa: E402
from launcher.ui.safe_cleanup.detail_panel import DetailPanel  # noqa: E402


class SafeCleanupDetailPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_detail_panel_renders_evidence_and_clears(self) -> None:
        item = CleanupPlanItem(
            id="review",
            layer=REVIEW_LAYER,
            kind="associated_file",
            label="Demo.tmp",
            action="移到隔離區",
            note="測試",
            checked_default=False,
            path=r"C:\Temp\Demo.tmp",
            evidence=(CleanupEvidence("同名", "名稱接近目標", 0.6, "positive"),),
        )
        panel = DetailPanel()
        panel.set_item(item, ItemImpact(shortcut_count=1, registry_ref_count=0, process_count=0, derived_count=0))

        text = panel.text_edit.toPlainText()
        self.assertIn("證據帳本", text)
        self.assertIn("捷徑引用", text)

        panel.clear()

        self.assertIn("尚未選擇項目", panel.text_edit.toPlainText())


if __name__ == "__main__":
    unittest.main()
