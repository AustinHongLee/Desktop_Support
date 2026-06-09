from __future__ import annotations

import unittest

from launcher.plugins.iso_tools.roi_calibration import confidence_distribution, serial_calibration_payload
from launcher.plugins.iso_tools.serial_vision import SerialRegionCalibration, SerialVisionRegion


class IsoRoiCalibrationTests(unittest.TestCase):
    def test_confidence_distribution_buckets_rows(self) -> None:
        rows = [
            {"page": 1, "source_name": "p1.pdf", "confidence": 0.91},
            {"page": 2, "source_name": "p2.pdf", "confidence": 0.62},
            {"page": 3, "source_name": "p3.pdf", "confidence": 0.0},
        ]

        result = confidence_distribution(rows, threshold=0.70)

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["ready"], 1)
        self.assertEqual(result["low"], 1)
        self.assertEqual(result["missing"], 1)
        self.assertEqual([sample["bucket"] for sample in result["samples"]], ["ready", "low", "missing"])

    def test_serial_calibration_payload_keeps_region_values(self) -> None:
        calibration = SerialRegionCalibration(
            region=SerialVisionRegion(left=0.1, top=0.2, width=0.3, height=0.4),
            confidence=0.88,
            message="ok",
        )

        result = serial_calibration_payload(calibration)

        self.assertEqual(result["region"], {"left": 0.1, "top": 0.2, "width": 0.3, "height": 0.4})
        self.assertEqual(result["confidence"], 0.88)
        self.assertEqual(result["message"], "ok")


if __name__ == "__main__":
    unittest.main()
