from __future__ import annotations

import unittest

from launcher.plugins.iso_tools.iso_naming import IsoRecord, build_record_lookup
from launcher.plugins.iso_tools.serial_correction import correct_result_with_iso_lookup, serial_lookup_correction
from launcher.plugins.iso_tools.serial_vision import SerialVisionResult


class IsoVisionCorrectionTests(unittest.TestCase):
    def test_corrects_trailing_border_digit_using_iso_list(self) -> None:
        lookup = build_record_lookup([IsoRecord(serial="103", line_no="A")])

        result = correct_result_with_iso_lookup(
            SerialVisionResult("1037", 0.92, "RapidOCR：流水号：1037"),
            lookup,
        )

        self.assertEqual(result.text, "103")
        self.assertGreater(result.confidence, 0.92)
        self.assertLessEqual(result.confidence, 0.98)
        self.assertIn("ISO List 校正", result.message)
        self.assertIn("原始信心 0.92", result.message)

    def test_iso_correction_boosts_but_does_not_overtrust_weak_source(self) -> None:
        lookup = build_record_lookup([IsoRecord(serial="103", line_no="A")])

        result = correct_result_with_iso_lookup(
            SerialVisionResult("1037", 0.62, "RapidOCR：流水号：1037"),
            lookup,
        )

        self.assertEqual(result.text, "103")
        self.assertGreater(result.confidence, 0.62)
        self.assertLess(result.confidence, 0.70)

    def test_corrects_leading_noise_using_iso_list(self) -> None:
        lookup = build_record_lookup([IsoRecord(serial="44", line_no="A")])

        result = correct_result_with_iso_lookup(
            SerialVisionResult("144", 0.93, "RapidOCR：流水號：144"),
            lookup,
        )

        self.assertEqual(result.text, "44")

    def test_does_not_correct_ambiguous_iso_candidates(self) -> None:
        lookup = build_record_lookup(
            [
                IsoRecord(serial="12", line_no="A"),
                IsoRecord(serial="23", line_no="B"),
            ]
        )

        correction = serial_lookup_correction("123", lookup)

        self.assertIsNone(correction)

    def test_empty_iso_lookup_keeps_result_unchanged(self) -> None:
        result = SerialVisionResult("1037", 0.92, "RapidOCR：流水号：1037")

        corrected = correct_result_with_iso_lookup(result, {})

        self.assertEqual(corrected, result)


if __name__ == "__main__":
    unittest.main()
