from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.plugins.iso_tools.serial_vision import SerialVisionRegion  # noqa: E402
from launcher.ui.iso_pdf.region_selector import RegionSelector, _normalized_region  # noqa: E402


class RegionSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_region_selector_can_be_imported_and_created(self) -> None:
        selector = RegionSelector()

        self.assertEqual(selector.objectName(), "RegionSelector")
        self.assertGreaterEqual(selector.minimumHeight(), 230)

    def test_region_normalization_clamps_to_page_bounds(self) -> None:
        region = _normalized_region(SerialVisionRegion(left=0.99, top=-0.25, width=0.9, height=0.0))

        self.assertLessEqual(region.left + region.width, 1.0)
        self.assertGreaterEqual(region.top, 0.0)
        self.assertGreaterEqual(region.width, 0.025)
        self.assertGreaterEqual(region.height, 0.025)


if __name__ == "__main__":
    unittest.main()
