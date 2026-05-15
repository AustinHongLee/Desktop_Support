from __future__ import annotations

import unittest
from unittest.mock import patch

import cv2
import numpy as np

from launcher.plugins.iso_tools.serial_vision import (
    SerialRegionCalibration,
    SerialVisionRegion,
    _calibrate_region_from_rapidocr_result,
    _is_digit_candidate,
    _merge_vision_results,
    _pick_rapidocr_serial_candidate,
    detect_serial_from_bgr,
    detect_serial_two_stage_from_bgr,
    detect_serial_from_gray,
    SerialVisionResult,
)
import launcher.plugins.iso_tools.serial_vision as serial_vision


class SerialVisionTests(unittest.TestCase):
    def test_detects_top_right_serial_digits(self) -> None:
        image = np.full((3364, 4760), 255, dtype=np.uint8)
        cv2.putText(
            image,
            "101",
            (4520, 125),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.0,
            0,
            6,
            cv2.LINE_AA,
        )

        result = detect_serial_from_gray(image)

        self.assertEqual(result.text, "101")
        self.assertGreater(result.confidence, 0.55)

    def test_detects_blue_serial_without_picking_nearby_drawing_numbers(self) -> None:
        image = np.full((3364, 4760, 3), 255, dtype=np.uint8)
        cv2.putText(image, "23", (4620, 125), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 0, 0), 6, cv2.LINE_AA)
        cv2.putText(image, "562", (3600, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 4, cv2.LINE_AA)

        result = detect_serial_from_bgr(image)

        self.assertEqual(result.text, "23")
        self.assertGreater(result.confidence, 0.55)

    def test_ignores_lower_right_drawing_numbers(self) -> None:
        image = np.full((3364, 4760), 255, dtype=np.uint8)
        cv2.putText(
            image,
            "562",
            (4520, 320),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.8,
            0,
            5,
            cv2.LINE_AA,
        )

        result = detect_serial_from_gray(image)

        self.assertEqual(result.text, "")

    def test_solid_block_is_not_a_digit_candidate(self) -> None:
        self.assertFalse(
            _is_digit_candidate(
                500,
                200,
                490,
                20,
                30,
                60,
                0.96,
                x_min_ratio=0.90,
            )
        )

    def test_thin_border_line_is_not_a_digit_candidate(self) -> None:
        self.assertFalse(
            _is_digit_candidate(
                500,
                200,
                490,
                20,
                9,
                80,
                0.55,
                x_min_ratio=0.90,
            )
        )

    def test_custom_region_can_move_detection_window(self) -> None:
        image = np.full((3364, 4760), 255, dtype=np.uint8)
        cv2.putText(image, "77", (500, 500), cv2.FONT_HERSHEY_SIMPLEX, 2.0, 0, 6, cv2.LINE_AA)

        default_result = detect_serial_from_gray(image)
        custom_result = detect_serial_from_gray(
            image,
            region=SerialVisionRegion(left=0.08, top=0.13, width=0.18, height=0.14),
        )

        self.assertEqual(default_result.text, "")
        self.assertEqual(custom_result.text, "77")
        self.assertGreater(custom_result.confidence, 0.55)

    def test_rapidocr_candidate_prefers_serial_label(self) -> None:
        raw = (
            [
                [[[10, 10], [200, 10], [200, 60], [10, 60]], "流水號：144", 0.94],
                [[[100, 400], [240, 400], [240, 440], [100, 440]], "E 58730", 0.99],
            ],
            [0.1, 0.1, 0.1],
        )

        result = _pick_rapidocr_serial_candidate(raw, 400, 800)

        self.assertEqual(result.text, "144")
        self.assertGreater(result.confidence, 0.9)

    def test_calibrates_region_from_serial_label(self) -> None:
        raw = (
            [
                [[[1340, 70], [1720, 70], [1720, 145], [1340, 145]], "流水號：101", 0.93],
                [[[100, 600], [240, 600], [240, 640], [100, 640]], "E 58730", 0.99],
            ],
            [0.1, 0.1, 0.1],
        )

        calibration = _calibrate_region_from_rapidocr_result(raw, 4760, 3364)

        self.assertIsNotNone(calibration.region)
        assert calibration.region is not None
        self.assertLess(calibration.region.left, 1340 / 4760)
        self.assertLess(calibration.region.top, 70 / 3364)
        self.assertGreater(calibration.region.left + calibration.region.width, 1720 / 4760)
        self.assertGreater(calibration.region.top + calibration.region.height, 145 / 3364)
        self.assertGreater(calibration.confidence, 0.9)

    def test_calibration_requires_serial_label(self) -> None:
        raw = (
            [
                [[[100, 600], [240, 600], [240, 640], [100, 640]], "E 58730", 0.99],
            ],
            [0.1, 0.1, 0.1],
        )

        calibration = _calibrate_region_from_rapidocr_result(raw, 4760, 3364)

        self.assertIsNone(calibration.region)

    def test_two_stage_uses_calibrated_region_when_confident(self) -> None:
        image = np.full((1000, 1000, 3), 255, dtype=np.uint8)
        auto_region = SerialVisionRegion(left=0.1, top=0.1, width=0.2, height=0.1)
        fallback_region = SerialVisionRegion(left=0.6, top=0.0, width=0.3, height=0.2)
        calls: list[SerialVisionRegion | None] = []

        def fake_detect(_image, region=None):  # noqa: ANN001
            calls.append(region)
            return SerialVisionResult("101", 0.91, "OK")

        with patch.object(
            serial_vision,
            "calibrate_serial_region_from_bgr",
            return_value=SerialRegionCalibration(auto_region, 0.95, "自動校準：流水號"),
        ):
            with patch.object(serial_vision, "detect_serial_from_bgr", side_effect=fake_detect):
                result = detect_serial_two_stage_from_bgr(image, fallback_region)

        self.assertEqual(result.text, "101")
        self.assertEqual(calls, [auto_region])
        self.assertIn("自動 ROI", result.message)

    def test_two_stage_falls_back_when_auto_region_is_low_confidence(self) -> None:
        image = np.full((1000, 1000, 3), 255, dtype=np.uint8)
        auto_region = SerialVisionRegion(left=0.1, top=0.1, width=0.2, height=0.1)
        fallback_region = SerialVisionRegion(left=0.6, top=0.0, width=0.3, height=0.2)
        calls: list[SerialVisionRegion | None] = []

        def fake_detect(_image, region=None):  # noqa: ANN001
            calls.append(region)
            if region == auto_region:
                return SerialVisionResult("7", 0.42, "框線疑似數字")
            return SerialVisionResult("102", 0.93, "OK")

        with patch.object(
            serial_vision,
            "calibrate_serial_region_from_bgr",
            return_value=SerialRegionCalibration(auto_region, 0.95, "自動校準：流水號"),
        ):
            with patch.object(serial_vision, "detect_serial_from_bgr", side_effect=fake_detect):
                result = detect_serial_two_stage_from_bgr(image, fallback_region)

        self.assertEqual(result.text, "102")
        self.assertEqual(calls, [auto_region, fallback_region])
        self.assertIn("fallback ROI", result.message)

    def test_two_stage_uses_fallback_when_label_is_missing(self) -> None:
        image = np.full((1000, 1000, 3), 255, dtype=np.uint8)
        fallback_region = SerialVisionRegion(left=0.6, top=0.0, width=0.3, height=0.2)
        calls: list[SerialVisionRegion | None] = []

        def fake_detect(_image, region=None):  # noqa: ANN001
            calls.append(region)
            return SerialVisionResult("103", 0.9, "OK")

        with patch.object(
            serial_vision,
            "calibrate_serial_region_from_bgr",
            return_value=SerialRegionCalibration(None, 0.0, "找不到「流水號」文字，無法自動校準"),
        ):
            with patch.object(serial_vision, "detect_serial_from_bgr", side_effect=fake_detect):
                result = detect_serial_two_stage_from_bgr(image, fallback_region)

        self.assertEqual(result.text, "103")
        self.assertEqual(calls, [fallback_region])
        self.assertIn("fallback ROI", result.message)

    def test_ocr_suffix_can_be_corrected_by_opencv(self) -> None:
        result = _merge_vision_results(
            SerialVisionResult("44", 0.76, "OpenCV"),
            SerialVisionResult("144", 0.94, "RapidOCR"),
        )

        self.assertEqual(result.text, "44")
        self.assertGreaterEqual(result.confidence, 0.76)

    def test_ocr_trailing_noise_can_be_corrected_by_opencv(self) -> None:
        result = _merge_vision_results(
            SerialVisionResult("103", 0.78, "OpenCV"),
            SerialVisionResult("1037", 0.94, "RapidOCR"),
        )

        self.assertEqual(result.text, "103")
        self.assertGreaterEqual(result.confidence, 0.78)


if __name__ == "__main__":
    unittest.main()
