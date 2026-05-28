from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import SAFE_LAYER, CleanupPlan, CleanupPlanItem, compute_impact  # noqa: E402
from launcher.ui.components.card import Card  # noqa: E402
from launcher.ui.safe_cleanup.header_card import TargetHeaderCard  # noqa: E402
from launcher.ui.safe_cleanup.overview_tab import OverviewTab  # noqa: E402
from launcher.ui.safe_cleanup.risk_badge import RiskBadge  # noqa: E402
from launcher.ui.safe_cleanup.risk_meter import RiskMeter  # noqa: E402


class SafeCleanupComponentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_card_and_badge_are_importable_widgets(self) -> None:
        card = Card()
        badge = RiskBadge(layer=SAFE_LAYER)

        self.assertEqual(card.objectName(), "Card")
        self.assertEqual(badge.property("layer"), SAFE_LAYER)

    def test_header_overview_and_meter_accept_cleanup_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.txt"
            target.write_text("x", encoding="utf-8")
            plan = CleanupPlan(
                targets=(target,),
                created_at=time.time(),
                items=(
                    CleanupPlanItem(
                        id="target",
                        layer=SAFE_LAYER,
                        kind="file",
                        label="target.txt",
                        action="移到隔離區",
                        note="safe",
                        checked_default=True,
                        path=str(target),
                        size_bytes=1,
                    ),
                ),
            )

            header = TargetHeaderCard()
            header.set_plan(plan)
            overview = OverviewTab()
            overview.set_plan(plan)
            meter = RiskMeter()
            meter.set_plan(plan)

        self.assertEqual(header.target_path_edit.text(), str(target))
        self.assertTrue(overview.one_click_button.isEnabled())
        self.assertGreaterEqual(meter.sizeHint().width(), 200)

    def test_compute_impact_counts_related_evidence(self) -> None:
        target = CleanupPlanItem(
            id="target",
            layer=SAFE_LAYER,
            kind="file",
            label="Demo.exe",
            action="移到隔離區",
            note="safe",
            checked_default=True,
            path=r"C:\Demo\Demo.exe",
        )
        plan = CleanupPlan(
            targets=(Path(r"C:\Demo\Demo.exe"),),
            created_at=time.time(),
            items=(
                target,
                CleanupPlanItem(
                    id="shortcut",
                    layer=SAFE_LAYER,
                    kind="shortcut",
                    label="Demo.lnk",
                    action="移到隔離區",
                    note="shortcut",
                    checked_default=True,
                    path=r"C:\Users\User\Desktop\Demo.exe.lnk",
                ),
                CleanupPlanItem(
                    id="registry",
                    layer=SAFE_LAYER,
                    kind="registry_value",
                    label="DisplayIcon",
                    action="刪除登錄值",
                    note="registry",
                    checked_default=False,
                    registry_value_data=r"C:\Demo\Demo.exe",
                ),
            ),
        )

        impact = compute_impact(plan, target)

        self.assertEqual(impact.shortcut_count, 1)
        self.assertEqual(impact.registry_ref_count, 1)


if __name__ == "__main__":
    unittest.main()

