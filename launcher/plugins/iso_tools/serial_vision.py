from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class SerialVisionResult:
    text: str
    confidence: float
    message: str


@dataclass(frozen=True)
class SerialVisionRegion:
    left: float = 0.62
    top: float = 0.0
    width: float = 0.38
    height: float = 0.24


@dataclass(frozen=True)
class SerialRegionCalibration:
    region: SerialVisionRegion | None
    confidence: float
    message: str


DEFAULT_SERIAL_REGION = SerialVisionRegion()
TWO_STAGE_MIN_CONFIDENCE = 0.70
_BLUE_DIGIT_FULL_X_RATIO = 0.966
_GRAY_DIGIT_FULL_X_RATIO = 0.943


def detect_serial_from_qimage(image: Any, region: SerialVisionRegion | None = None) -> SerialVisionResult:
    return detect_serial_from_bgr(_qimage_to_bgr(image), region=region)


def detect_serial_two_stage_from_qimage(
    image: Any,
    fallback_region: SerialVisionRegion | None = None,
    *,
    min_confidence: float = TWO_STAGE_MIN_CONFIDENCE,
) -> SerialVisionResult:
    return detect_serial_two_stage_from_bgr(_qimage_to_bgr(image), fallback_region, min_confidence=min_confidence)


def calibrate_serial_region_from_qimage(image: Any) -> SerialRegionCalibration:
    return calibrate_serial_region_from_bgr(_qimage_to_bgr(image))


def calibrate_serial_region_from_bgr(image: Any) -> SerialRegionCalibration:
    height, width = image.shape[:2]
    if height < 100 or width < 100:
        return SerialRegionCalibration(None, 0.0, "影像太小，無法自動校準")
    try:
        ocr = _rapidocr()
    except ImportError:
        return SerialRegionCalibration(None, 0.0, "RapidOCR 未安裝")
    try:
        raw_result = ocr(image)
    except Exception as exc:
        return SerialRegionCalibration(None, 0.0, f"RapidOCR 自動校準失敗：{exc}")
    return _calibrate_region_from_rapidocr_result(raw_result, width, height)


def detect_serial_from_bgr(image: Any, region: SerialVisionRegion | None = None) -> SerialVisionResult:
    cv2, _np = _cv2_np()
    height, width = image.shape[:2]
    if height < 100 or width < 100:
        return SerialVisionResult("", 0.0, "影像太小，無法判讀")

    normalized_region = _normalize_region(region)
    roi = _crop_serial_region(image, normalized_region)
    cv_result = _detect_serial_with_opencv(image, roi, normalized_region)
    ocr_result = _detect_serial_with_rapidocr(roi)
    return _merge_vision_results(cv_result, ocr_result)


def detect_serial_two_stage_from_bgr(
    image: Any,
    fallback_region: SerialVisionRegion | None = None,
    *,
    min_confidence: float = TWO_STAGE_MIN_CONFIDENCE,
) -> SerialVisionResult:
    calibration = calibrate_serial_region_from_bgr(image)
    fallback = _normalize_region(fallback_region)
    if calibration.region is None:
        fallback_result = detect_serial_from_bgr(image, region=fallback)
        return _with_message(fallback_result, f"fallback ROI：{calibration.message}")

    auto_result = detect_serial_from_bgr(image, region=calibration.region)
    if auto_result.text and auto_result.confidence >= min_confidence:
        return _with_message(auto_result, f"自動 ROI：{calibration.message}")

    fallback_result = detect_serial_from_bgr(image, region=fallback)
    if fallback_result.text:
        reason = "無結果" if not auto_result.text else f"低信心 {auto_result.confidence:.2f}"
        return _with_message(fallback_result, f"fallback ROI：自動 ROI {reason}（{calibration.message}）")
    if auto_result.text:
        return _with_message(auto_result, f"自動 ROI 低信心，fallback 無結果：{calibration.message}")
    return _with_message(fallback_result, f"fallback ROI：自動 ROI 無結果（{calibration.message}）")


def detect_serial_from_gray(gray: Any, region: SerialVisionRegion | None = None) -> SerialVisionResult:
    cv2, np = _cv2_np()
    height, width = gray.shape[:2]
    if height < 100 or width < 100:
        return SerialVisionResult("", 0.0, "影像太小，無法判讀")

    normalized_region = _normalize_region(region)
    roi = _crop_serial_region(gray, normalized_region)
    threshold = cv2.threshold(
        roi,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )[1]
    return _detect_serial_from_threshold(
        threshold,
        x_min_ratio=_candidate_x_min_ratio(normalized_region, _GRAY_DIGIT_FULL_X_RATIO),
    )


def serial_region_bounds(image_width: int, image_height: int, region: SerialVisionRegion | None = None) -> tuple[int, int, int, int]:
    normalized = _normalize_region(region)
    left = int(image_width * normalized.left)
    top = int(image_height * normalized.top)
    right = min(image_width, max(left + 1, int(image_width * (normalized.left + normalized.width))))
    bottom = min(image_height, max(top + 1, int(image_height * (normalized.top + normalized.height))))
    return left, top, right - left, bottom - top


def _detect_serial_with_opencv(image: Any, roi: Any, normalized_region: SerialVisionRegion) -> SerialVisionResult:
    cv2, _np = _cv2_np()
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(hsv, (90, 50, 30), (140, 255, 255))
    if cv2.countNonZero(blue_mask) > 100:
        result = _detect_serial_from_threshold(
            blue_mask,
            x_min_ratio=_candidate_x_min_ratio(normalized_region, _BLUE_DIGIT_FULL_X_RATIO),
        )
        if result.text:
            return result

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return detect_serial_from_gray(gray, region=normalized_region)


def _detect_serial_with_rapidocr(roi: Any) -> SerialVisionResult:
    try:
        ocr = _rapidocr()
    except ImportError:
        return SerialVisionResult("", 0.0, "RapidOCR 未安裝")
    try:
        raw_result = ocr(roi)
    except Exception as exc:
        return SerialVisionResult("", 0.0, f"RapidOCR 失敗：{exc}")
    return _pick_rapidocr_serial_candidate(raw_result, roi.shape[1], roi.shape[0])


def _merge_vision_results(cv_result: SerialVisionResult, ocr_result: SerialVisionResult) -> SerialVisionResult:
    if not ocr_result.text:
        return cv_result
    if not cv_result.text:
        return ocr_result
    if ocr_result.text == cv_result.text:
        return SerialVisionResult(
            cv_result.text,
            max(cv_result.confidence, ocr_result.confidence),
            f"OCR+OpenCV：{ocr_result.message}",
        )
    if ocr_result.text.endswith(cv_result.text) and len(ocr_result.text) > len(cv_result.text):
        confidence = max(cv_result.confidence, min(0.92, ocr_result.confidence - 0.05))
        return SerialVisionResult(cv_result.text, confidence, f"OCR 尾段校正：{ocr_result.text} -> {cv_result.text}")
    if ocr_result.text.startswith(cv_result.text) and len(ocr_result.text) > len(cv_result.text):
        confidence = max(cv_result.confidence, min(0.92, ocr_result.confidence - 0.05))
        return SerialVisionResult(cv_result.text, confidence, f"OCR 前段校正：{ocr_result.text} -> {cv_result.text}")
    if cv_result.text.endswith(ocr_result.text) and len(cv_result.text) > len(ocr_result.text):
        confidence = max(0.0, ocr_result.confidence - 0.03)
        return SerialVisionResult(ocr_result.text, confidence, f"OCR 尾段校正：{cv_result.text} -> {ocr_result.text}")
    if ocr_result.confidence >= 0.92 and cv_result.confidence < 0.76:
        return ocr_result
    return SerialVisionResult(cv_result.text, max(0.0, cv_result.confidence - 0.05), f"OCR 不一致：{ocr_result.text}")


def _pick_rapidocr_serial_candidate(raw_result: Any, roi_width: int, roi_height: int) -> SerialVisionResult:
    entries = _rapidocr_entries(raw_result)
    candidates: list[tuple[tuple[float, ...], str, float, str]] = []
    for entry in entries:
        if len(entry) < 3:
            continue
        box, text, score = entry[0], str(entry[1]), _safe_float(entry[2])
        digits = re.findall(r"\d+", text)
        if not digits:
            continue
        serial = digits[-1]
        normalized_text = text.replace("号", "號")
        keyword = 1.0 if ("流水" in normalized_text or "號" in normalized_text) else 0.0
        left, top, right, bottom = _box_bounds(box)
        center_x = (left + right) / 2 / max(1, roi_width)
        center_y = (top + bottom) / 2 / max(1, roi_height)
        if not keyword and center_y > 0.45:
            continue
        if len(serial) > 5:
            continue
        digit_density = len("".join(digits)) / max(1, len(re.sub(r"\s+", "", text)))
        confidence = score if keyword else max(0.0, score - 0.08)
        rank = (keyword, -center_y, center_x, digit_density, confidence)
        candidates.append((rank, serial, confidence, text))
    if not candidates:
        return SerialVisionResult("", 0.0, "RapidOCR 未找到流水號")
    _rank, serial, confidence, text = max(candidates, key=lambda item: item[0])
    return SerialVisionResult(serial, confidence, f"RapidOCR：{text}")


def _calibrate_region_from_rapidocr_result(raw_result: Any, image_width: int, image_height: int) -> SerialRegionCalibration:
    entries = _rapidocr_entries(raw_result)
    candidates: list[tuple[tuple[float, ...], SerialVisionRegion, float, str]] = []
    for entry in entries:
        if len(entry) < 3:
            continue
        box, text, score = entry[0], str(entry[1]), _safe_float(entry[2])
        normalized_text = text.replace("号", "號")
        if "流水" not in normalized_text and "流水號" not in normalized_text:
            continue
        left, top, right, bottom = _box_bounds(box)
        if right <= left or bottom <= top:
            continue
        region = _expanded_label_region(left, top, right, bottom, image_width, image_height)
        exact_keyword = 1.0 if "流水號" in normalized_text else 0.0
        center_x = (left + right) / 2 / max(1, image_width)
        center_y = (top + bottom) / 2 / max(1, image_height)
        rank = (exact_keyword, score, -center_y, center_x)
        candidates.append((rank, region, score, text))
    if not candidates:
        return SerialRegionCalibration(None, 0.0, "找不到「流水號」文字，無法自動校準")
    _rank, region, score, text = max(candidates, key=lambda item: item[0])
    return SerialRegionCalibration(region, score, f"自動校準：{text}")


def _expanded_label_region(
    left: float,
    top: float,
    right: float,
    bottom: float,
    image_width: int,
    image_height: int,
) -> SerialVisionRegion:
    box_width = right - left
    box_height = bottom - top
    expanded_left = left - max(box_width * 0.15, image_width * 0.008)
    expanded_top = top - max(box_height * 0.45, image_height * 0.006)
    expanded_right = right + max(box_width * 0.35, image_width * 0.025)
    expanded_bottom = bottom + max(box_height * 0.80, image_height * 0.012)

    return _normalize_region(
        SerialVisionRegion(
            left=expanded_left / max(1, image_width),
            top=expanded_top / max(1, image_height),
            width=(expanded_right - expanded_left) / max(1, image_width),
            height=(expanded_bottom - expanded_top) / max(1, image_height),
        )
    )


def _rapidocr_entries(raw_result: Any) -> list[Any]:
    if not raw_result:
        return []
    if isinstance(raw_result, tuple):
        first = raw_result[0] if raw_result else []
        return first or []
    return raw_result or []


def _box_bounds(box: Any) -> tuple[float, float, float, float]:
    points = list(box or [])
    xs = [_safe_float(point[0]) for point in points if len(point) >= 2]
    ys = [_safe_float(point[1]) for point in points if len(point) >= 2]
    if not xs or not ys:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _with_message(result: SerialVisionResult, prefix: str) -> SerialVisionResult:
    message = f"{prefix}；{result.message}" if result.message else prefix
    return SerialVisionResult(result.text, result.confidence, message)


def _qimage_to_bgr(image: Any) -> Any:
    _cv2, np = _cv2_np()
    ptr = image.bits()
    ptr.setsize(image.sizeInBytes())
    array = np.frombuffer(ptr, dtype=np.uint8).reshape(image.height(), image.width(), 4)
    if array.shape[2] == 4:
        alpha = array[:, :, 3:4].astype(np.float32) / 255.0
        color = array[:, :, :3].astype(np.float32)
        white = np.full_like(color, 255.0)
        array = (color * alpha + white * (1.0 - alpha)).astype(np.uint8)
    return array


def _detect_serial_from_threshold(threshold: Any, *, x_min_ratio: float) -> SerialVisionResult:
    cv2, _np = _cv2_np()
    contours, _hierarchy = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    digits: list[tuple[int, int, str, float, int]] = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        fill_ratio = area / max(1, box_width * box_height)
        if not _is_digit_candidate(
            threshold.shape[1],
            threshold.shape[0],
            x,
            y,
            box_width,
            box_height,
            fill_ratio,
            x_min_ratio=x_min_ratio,
        ):
            continue
        digit_image = threshold[
            max(0, y - 3) : min(threshold.shape[0], y + box_height + 3),
            max(0, x - 3) : min(threshold.shape[1], x + box_width + 3),
        ]
        digit, score = _classify_digit(digit_image)
        if score >= 0.55:
            digits.append((x, x + box_width, digit, score, box_width))

    digits.sort(key=lambda item: item[0])
    if not digits:
        return SerialVisionResult("", 0.0, "未判讀到流水號")

    run = _select_digit_run(digits)
    text = "".join(digit for _x, _right, digit, _score, _width in run)
    confidence = sum(score for _x, _right, _digit, score, _width in run) / len(run)
    return SerialVisionResult(text, confidence, "OK")


def _select_digit_run(digits: list[tuple[int, int, str, float, int]]) -> list[tuple[int, int, str, float, int]]:
    runs: list[list[tuple[int, int, str, float, int]]] = []
    current: list[tuple[int, int, str, float, int]] = []
    previous_right = 0
    previous_width = 0
    for item in digits:
        x, right, _digit, _score, width = item
        gap = x - previous_right if current else 0
        gap_limit = max(18, min(24, max(previous_width, width) * 0.60))
        if current and gap > gap_limit:
            runs.append(current)
            current = []
        current.append(item)
        previous_right = right
        previous_width = width
    if current:
        runs.append(current)

    preferred = [run for run in runs if 2 <= len(run) <= 5]
    if not preferred:
        preferred = [run for run in runs if len(run) <= 5] or runs
    return max(preferred, key=lambda run: (run[-1][1], len(run), sum(item[3] for item in run) / len(run)))


def _is_digit_candidate(
    roi_width: int,
    roi_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
    fill_ratio: float,
    *,
    x_min_ratio: float,
) -> bool:
    aspect_ratio = width / max(1, height)
    return (
        x > roi_width * x_min_ratio
        and y < min(roi_height * 0.20, 150)
        and 8 < width < 75
        and 25 < height < 90
        and fill_ratio > 0.15
        and fill_ratio < 0.85
        and 0.20 < aspect_ratio < 1.20
    )


def _classify_digit(binary_digit: Any) -> tuple[str, float]:
    cv2, _np = _cv2_np()
    normalized = _normalize_digit(binary_digit)
    if normalized is None:
        return "", 0.0
    best_digit = ""
    best_score = -1.0
    for digit, template in _digit_templates():
        score = float(cv2.matchTemplate(normalized, template, cv2.TM_CCOEFF_NORMED)[0, 0])
        if score > best_score:
            best_digit = digit
            best_score = score
    return best_digit, max(0.0, best_score)


def _normalize_digit(binary_digit: Any) -> Any | None:
    cv2, np = _cv2_np()
    target_width, target_height = 32, 48
    ys, xs = np.where(binary_digit > 0)
    if len(xs) == 0:
        return None
    crop = binary_digit[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    height, width = crop.shape[:2]
    scale = min((target_width - 6) / max(1, width), (target_height - 6) / max(1, height))
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    resized = cv2.resize(crop, (new_width, new_height), interpolation=cv2.INTER_AREA)
    output = np.zeros((target_height, target_width), dtype=np.uint8)
    x = (target_width - new_width) // 2
    y = (target_height - new_height) // 2
    output[y : y + new_height, x : x + new_width] = resized
    return cv2.threshold(output, 127, 255, cv2.THRESH_BINARY)[1]


def _crop_serial_region(image: Any, region: SerialVisionRegion | None) -> Any:
    height, width = image.shape[:2]
    left, top, crop_width, crop_height = serial_region_bounds(width, height, region)
    return image[top : top + crop_height, left : left + crop_width]


def _normalize_region(region: SerialVisionRegion | None) -> SerialVisionRegion:
    value = region or DEFAULT_SERIAL_REGION
    left = _clamp(value.left, 0.0, 0.95)
    top = _clamp(value.top, 0.0, 0.95)
    width = _clamp(value.width, 0.01, 1.0 - left)
    height = _clamp(value.height, 0.01, 1.0 - top)
    return SerialVisionRegion(left=left, top=top, width=width, height=height)


def _candidate_x_min_ratio(region: SerialVisionRegion, target_full_x_ratio: float) -> float:
    right = region.left + region.width
    if target_full_x_ratio <= region.left or target_full_x_ratio >= right:
        return 0.0
    return _clamp((target_full_x_ratio - region.left) / region.width, 0.0, 0.95)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@lru_cache(maxsize=1)
def _digit_templates() -> tuple[tuple[str, Any], ...]:
    cv2, np = _cv2_np()
    fonts = (
        cv2.FONT_HERSHEY_SIMPLEX,
        cv2.FONT_HERSHEY_DUPLEX,
        cv2.FONT_HERSHEY_COMPLEX,
        cv2.FONT_HERSHEY_TRIPLEX,
    )
    templates: list[tuple[str, Any]] = []
    for digit in "0123456789":
        for font in fonts:
            for scale in (1.8, 2.0, 2.2, 2.4):
                for thickness in (3, 4, 5, 6, 7, 8):
                    image = np.zeros((100, 80), dtype=np.uint8)
                    (text_width, text_height), _baseline = cv2.getTextSize(digit, font, scale, thickness)
                    cv2.putText(
                        image,
                        digit,
                        ((80 - text_width) // 2, (100 + text_height) // 2),
                        font,
                        scale,
                        255,
                        thickness,
                        cv2.LINE_AA,
                    )
                    normalized = _normalize_digit(image)
                    if normalized is not None:
                        templates.append((digit, normalized))
    return tuple(templates)


@lru_cache(maxsize=1)
def _cv2_np() -> tuple[Any, Any]:
    import cv2
    import numpy as np

    return cv2, np


@lru_cache(maxsize=1)
def _rapidocr() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()
