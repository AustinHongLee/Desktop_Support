from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REVIEW_LAYER, SAFE_LAYER, CleanupPlan, CleanupPlanItem  # noqa: E402
from launcher.ui.safe_cleanup.suggestion_tab import SuggestionTab  # noqa: E402


class SafeCleanupSuggestionTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_selected_ids_filter_and_process_unlock(self) -> None:
        safe = CleanupPlanItem(
            id="safe",
            layer=SAFE_LAYER,
            kind="file",
            label="safe.txt",
            action="移到隔離區",
            note="safe",
            checked_default=True,
            path=r"C:\Temp\safe.txt",
        )
        review = CleanupPlanItem(
            id="review",
            layer=REVIEW_LAYER,
            kind="associated_file",
            label="review.tmp",
            action="移到隔離區",
            note="review",
            checked_default=True,
            path=r"C:\Temp\review.tmp",
        )
        process = CleanupPlanItem(
            id="process",
            layer=PROCESS_LAYER,
            kind="running_process",
            label="Demo.exe",
            action="嘗試關閉程序",
            note="process",
            checked_default=False,
            process_id=123,
            process_name="Demo.exe",
            can_close=True,
        )
        blocked = CleanupPlanItem(
            id="blocked",
            layer=BLOCKED_LAYER,
            kind="registry_value",
            label="HKLM",
            action="只列出",
            note="blocked",
            checked_default=True,
            root_name="HKLM",
            registry_key="Software\\Demo",
        )
        plan = CleanupPlan(targets=(Path(r"C:\Temp\safe.txt"),), items=(safe, review, process, blocked), created_at=time.time())
        tab = SuggestionTab()
        tab.set_plan(plan)

        self.assertEqual(tab.selected_item_ids(), {"safe"})
        self.assertFalse(tab._item_cards["review"].is_checked())
        tab._item_cards["review"].set_checked(True)
        self.assertIn("review", tab.selected_item_ids())
        tab.focus_layer(PROCESS_LAYER)
        self.assertEqual(tab.current_item(), process)

        tab._item_cards["process"].set_checked(True)
        self.assertNotIn("process", tab.selected_item_ids())

        tab._sidebar._unlock_checks[PROCESS_LAYER].setChecked(True)
        tab._item_cards["process"].set_checked(True)

        self.assertIn("process", tab.selected_item_ids())
        self.assertNotIn("blocked", tab.selected_item_ids())


if __name__ == "__main__":
    unittest.main()
