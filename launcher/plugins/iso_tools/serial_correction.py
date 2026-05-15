from __future__ import annotations

import re

from launcher.plugins.iso_tools.iso_naming import IsoRecord
from launcher.plugins.iso_tools.serial_vision import SerialVisionResult


ISO_CORRECTION_CONFIDENCE_BOOST = 0.06
ISO_CORRECTION_STRONG_FLOOR = 0.90
ISO_CORRECTION_STRONG_SOURCE = 0.78
ISO_CORRECTION_MAX_CONFIDENCE = 0.98


def correct_result_with_iso_lookup(
    result: SerialVisionResult,
    record_lookup: dict[str, IsoRecord],
) -> SerialVisionResult:
    if not record_lookup or not result.text or result.text in record_lookup:
        return result
    correction = serial_lookup_correction(result.text, record_lookup)
    if correction is None:
        return result
    corrected_serial, reason = correction
    confidence = min(ISO_CORRECTION_MAX_CONFIDENCE, result.confidence + ISO_CORRECTION_CONFIDENCE_BOOST)
    if result.confidence >= ISO_CORRECTION_STRONG_SOURCE:
        confidence = max(confidence, ISO_CORRECTION_STRONG_FLOOR)
    return SerialVisionResult(corrected_serial, confidence, f"ISO List 校正：{reason}；原始信心 {result.confidence:.2f}")


def serial_lookup_correction(text: str, record_lookup: dict[str, IsoRecord]) -> tuple[str, str] | None:
    digits = re.sub(r"\D+", "", text)
    if len(digits) < 2:
        return None
    matches: list[tuple[int, int, int, str, str]] = []
    max_trim = min(2, len(digits) - 1)
    for left_trim in range(0, max_trim + 1):
        for right_trim in range(0, max_trim + 1):
            if left_trim == 0 and right_trim == 0:
                continue
            if left_trim + right_trim >= len(digits):
                continue
            candidate = digits[left_trim : len(digits) - right_trim if right_trim else len(digits)]
            if len(candidate) < 2 or candidate not in record_lookup:
                continue
            record_serial = record_lookup[candidate].serial
            score = len(candidate) * 10 - (left_trim + right_trim)
            if right_trim == 1:
                score += 2
            if left_trim == 1:
                score += 1
            reason = f"{digits} -> {record_serial}"
            matches.append((score, len(candidate), left_trim + right_trim, record_serial, reason))
    if not matches:
        return None
    matches.sort(reverse=True)
    best = matches[0]
    for match in matches[1:]:
        if match[1] == best[1] and match[2] == best[2] and match[3] != best[3]:
            return None
    return best[3], best[4]
