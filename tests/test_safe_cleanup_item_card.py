from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import BLOCKED_LAYER, REGISTRY_LAYER, REVIEW_LAYER, CleanupEvidence, CleanupPlanItem, ItemImpact  # noqa: E402
from launcher.ui.safe_cleanup.item_card import ItemCard  # noqa: E402


class SafeCleanupItemCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_review_card_shows_top_two_evidence(self) -> None:
        item = CleanupPlanItem(
            id="review",
            layer=REVIEW_LAYER,
            kind="associated_file",
            label="Demo.tmp",
            action="移到隔離區",
            note="測試",
            checked_default=False,
            path=r"C:\Temp\Demo.tmp",
            evidence=(
                CleanupEvidence("同名", "名稱接近目標", 0.6, "positive"),
                CleanupEvidence("位置", "位於暫存區", 0.4, "positive"),
                CleanupEvidence("多餘", "第三條不顯示", 0.1, "positive"),
            ),
        )
        card = ItemCard()
        card.set_item(item, ItemImpact(0, 0, 0, 0))

        self.assertEqual(card._evidence_layout.count(), 2)
        self.assertFalse(card.is_checked())

    def test_registry_card_requires_unlock_before_check(self) -> None:
        item = CleanupPlanItem(
            id="registry",
            layer=REGISTRY_LAYER,
            kind="registry_value",
            label="HKCU\\Demo",
            action="刪除登錄值",
            note="測試",
            checked_default=False,
            root_name="HKCU",
            registry_key="Software\\Demo",
        )
        card = ItemCard()
        card.set_item(item, ItemImpact(0, 0, 0, 0))

        card.set_checked(True)
        self.assertFalse(card.is_checked())

        card.set_unlocked(True)
        card.set_checked(True)

        self.assertTrue(card.is_checked())

    def test_blocked_card_never_checks(self) -> None:
        item = CleanupPlanItem(
            id="blocked",
            layer=BLOCKED_LAYER,
            kind="registry_value",
            label="HKLM\\Demo",
            action="只列出",
            note="測試",
            checked_default=True,
            root_name="HKLM",
            registry_key="Software\\Demo",
        )
        card = ItemCard()
        card.set_item(item, ItemImpact(0, 0, 0, 0))
        card.set_unlocked(True)
        card.set_checked(True)

        self.assertFalse(card.is_checked())


if __name__ == "__main__":
    unittest.main()
