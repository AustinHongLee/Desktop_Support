from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.safe_cleanup import PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER  # noqa: E402
from launcher.ui.safe_cleanup.filter_sidebar import FilterSidebar  # noqa: E402


class SafeCleanupFilterSidebarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_counts_filter_and_unlock_signals(self) -> None:
        sidebar = FilterSidebar()
        filters: list[str] = []
        unlocks: list[tuple[str, bool]] = []
        sidebar.filter_changed.connect(filters.append)
        sidebar.unlock_toggled.connect(lambda layer, unlocked: unlocks.append((layer, unlocked)))

        sidebar.set_layer_counts({SAFE_LAYER: 2, REVIEW_LAYER: 3})
        sidebar.set_filter(REVIEW_LAYER)
        sidebar._unlock_checks[REGISTRY_LAYER].setChecked(True)

        self.assertEqual(sidebar.current_filter(), REVIEW_LAYER)
        self.assertIn(REVIEW_LAYER, filters)
        self.assertIn((REGISTRY_LAYER, True), unlocks)
        self.assertTrue(sidebar.is_unlocked(REGISTRY_LAYER))
        self.assertFalse(sidebar.is_unlocked(PROCESS_LAYER))


if __name__ == "__main__":
    unittest.main()
