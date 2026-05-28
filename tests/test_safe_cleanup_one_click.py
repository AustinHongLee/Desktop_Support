from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import (  # noqa: E402
    BLOCKED_LAYER,
    PROCESS_LAYER,
    REGISTRY_LAYER,
    REVIEW_LAYER,
    SAFE_LAYER,
    CleanupApplyResult,
    CleanupPlan,
    CleanupPlanItem,
)
from launcher.ui.safe_cleanup.one_click_dialogs import OneClickResultDialog, OneClickSummaryDialog, default_one_click_ids  # noqa: E402


class SafeCleanupOneClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_default_one_click_ids_exclude_process_registry_and_blocked_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.txt"
            target.write_text("x", encoding="utf-8")
            plan = CleanupPlan(
                targets=(target,),
                created_at=time.time(),
                items=(
                    CleanupPlanItem(
                        id="safe",
                        layer=SAFE_LAYER,
                        kind="file",
                        label="safe",
                        action="移到隔離區",
                        note="safe",
                        checked_default=True,
                        path=str(target),
                    ),
                    CleanupPlanItem(
                        id="review",
                        layer=REVIEW_LAYER,
                        kind="folder",
                        label="review",
                        action="移到隔離區",
                        note="review",
                        checked_default=True,
                        path=str(target.parent),
                    ),
                    CleanupPlanItem(
                        id="medium_review",
                        layer=REVIEW_LAYER,
                        kind="folder",
                        label="medium review",
                        action="移到隔離區",
                        note="medium",
                        checked_default=True,
                        path=str(target.parent),
                        confidence=0.79,
                    ),
                    CleanupPlanItem(
                        id="process",
                        layer=PROCESS_LAYER,
                        kind="running_process",
                        label="process",
                        action="嘗試關閉程序",
                        note="process",
                        checked_default=True,
                        process_id=123,
                        process_path=str(target),
                        can_close=True,
                    ),
                    CleanupPlanItem(
                        id="registry",
                        layer=REGISTRY_LAYER,
                        kind="registry_value",
                        label="registry",
                        action="刪除登錄值",
                        note="registry",
                        checked_default=True,
                        root_name="HKCU",
                        registry_key="Software\\Demo",
                    ),
                    CleanupPlanItem(
                        id="blocked",
                        layer=BLOCKED_LAYER,
                        kind="registry_value",
                        label="blocked",
                        action="只列出",
                        note="blocked",
                        checked_default=True,
                        root_name="HKLM",
                        registry_key="Software\\Demo",
                    ),
                ),
            )

        self.assertEqual(default_one_click_ids(plan), {"safe", "review"})

    def test_dialogs_can_render_summary_and_result(self) -> None:
        plan = CleanupPlan(targets=(Path("C:/Demo/App.exe"),), items=(), created_at=time.time())
        summary = OneClickSummaryDialog(plan, selected_ids=set())
        self.assertEqual(summary.windowTitle(), "一鍵安全清除")

        with tempfile.TemporaryDirectory() as tmp:
            result = CleanupApplyResult(
                quarantine_dir=Path(tmp),
                manifest_path=Path(tmp) / "manifest.json",
                moved_count=1,
                registry_deleted_count=0,
                closed_process_count=0,
                state_cleaned=False,
            )
            result_dialog = OneClickResultDialog(result)
            result_dialog._open_quarantine()

        self.assertTrue(result_dialog.open_quarantine_requested)


if __name__ == "__main__":
    unittest.main()
