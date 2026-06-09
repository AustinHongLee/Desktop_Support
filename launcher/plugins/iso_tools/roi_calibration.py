from __future__ import annotations

from typing import Any, Iterable, Mapping

from launcher.plugins.iso_tools.serial_vision import (
    SerialRegionCalibration,
    SerialVisionRegion,
    calibrate_serial_region_from_bgr,
    calibrate_serial_region_from_qimage,
)


def calibrate_serial_roi_from_bgr(image: Any) -> dict[str, Any]:
    return serial_calibration_payload(calibrate_serial_region_from_bgr(image))


def calibrate_serial_roi_from_qimage(image: Any) -> dict[str, Any]:
    return serial_calibration_payload(calibrate_serial_region_from_qimage(image))


def serial_calibration_payload(calibration: SerialRegionCalibration) -> dict[str, Any]:
    return {
        "region": region_payload(calibration.region) if calibration.region else None,
        "confidence": float(calibration.confidence),
        "message": calibration.message,
    }


def region_payload(region: SerialVisionRegion) -> dict[str, float]:
    return {
        "left": float(region.left),
        "top": float(region.top),
        "width": float(region.width),
        "height": float(region.height),
    }


def confidence_distribution(rows: Iterable[Mapping[str, Any]], *, threshold: float = 0.70) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    ready = 0
    low = 0
    missing = 0
    for index, row in enumerate(rows):
        confidence = _float_value(row.get("confidence"), 0.0)
        if confidence >= threshold:
            bucket = "ready"
            ready += 1
        elif confidence > 0:
            bucket = "low"
            low += 1
        else:
            bucket = "missing"
            missing += 1
        samples.append(
            {
                "index": index,
                "page": row.get("page"),
                "source_name": row.get("source_name") or row.get("source_path") or "",
                "confidence": confidence,
                "bucket": bucket,
            }
        )
    return {
        "threshold": float(threshold),
        "total": len(samples),
        "ready": ready,
        "low": low,
        "missing": missing,
        "samples": samples,
    }


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
