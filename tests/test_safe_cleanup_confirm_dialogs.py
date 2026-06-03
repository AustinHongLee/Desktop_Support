from __future__ import annotations

import os
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import BLOCKED_LAYER, REGISTRY_LAYER, CleanupPlan, CleanupPlanItem  # noqa: E402
from launcher.ui.safe_cleanup.confirm_dialogs import RiskActionConfirmDialog  # noqa: E402


class SafeCleanupConfirmDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_registry_confirmation_requires_acknowledgement_and_ignores_blocked(self) -> None:
        registry = CleanupPlanItem(
            id="registry",
            layer=REGISTRY_LAYER,
            kind="registry_value",
            label="HKCU\\Demo",
            action="刪除登錄值",
            note="registry",
            checked_default=False,
            root_name="HKCU",
            registry_key="Software\\Demo",
        )
        blocked = CleanupPlanItem(
            id="blocked",
            layer=BLOCKED_LAYER,
            kind="registry_value",
            label="HKLM\\Demo",
            action="只列出",
            note="blocked",
            checked_default=False,
            root_name="HKLM",
            registry_key="Software\\Demo",
        )
        plan = CleanupPlan(targets=(Path("Demo"),), items=(registry, blocked), created_at=time.time())
        dialog = RiskActionConfirmDialog(plan, {"registry", "blocked"})

        self.assertFalse(dialog._ok_button.isEnabled())
        dialog._understand.setChecked(True)

        self.assertTrue(dialog._ok_button.isEnabled())
        self.assertEqual(dialog.confirmed_ids(), {"registry"})


if __name__ == "__main__":
    unittest.main()
