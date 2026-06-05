from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtWidgets import QApplication

from launcher.plugins.iso_tools.profile import DEFAULT_DRAWING_REGION
from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialVisionRegion, detect_serial_from_qimage, serial_region_bounds


@dataclass(frozen=True)
class IsoPreviewRequest:
    source_path: Path
    detect_serial: bool = True
    serial_region: SerialVisionRegion = DEFAULT_SERIAL_REGION
    drawing_region: SerialVisionRegion = DEFAULT_DRAWING_REGION


def main() -> int:
    _configure_stdio()
    try:
        request = IsoPreviewRequest(**_normalize_request(json.loads(_read_stdin_json() or "{}")))
        payload = build_iso_preview(request)
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1


def build_iso_preview(request: IsoPreviewRequest) -> dict[str, Any]:
    source = request.source_path
    if not source.exists():
        raise FileNotFoundError(f"PDF 不存在：{source}")

    _ensure_app()
    document = QPdfDocument(None)
    try:
        error = document.load(str(source))
        if error != QPdfDocument.Error.None_:
            raise ValueError(f"PDF 無法載入 ({error.name})：{source.name}")
        if document.pageCount() <= 0:
            raise ValueError(f"PDF 沒有頁面：{source.name}")

        page_size = document.pagePointSize(0)
        render_size = QSize(max(900, int(page_size.width() * 2.2)), max(1200, int(page_size.height() * 2.2)))
        rendered = document.render(0, render_size)
        if rendered.isNull():
            raise ValueError(f"無法產生 PDF 預覽：{source.name}")
    finally:
        document.close()

    image = _image_on_white(rendered)
    serial_crop = _crop_region(image, request.serial_region)
    drawing_crop = _crop_region(image, request.drawing_region)
    vision = detect_serial_from_qimage(image, request.serial_region) if request.detect_serial else None
    return {
        "schema_version": 1,
        "source_path": str(source),
        "source_name": source.name,
        "page": {
            "width": image.width(),
            "height": image.height(),
            "image": _image_data_url(_scaled(image, QSize(900, 1200))),
        },
        "serial_crop": {
            "region": _region_payload(request.serial_region),
            "image": _image_data_url(_scaled(serial_crop, QSize(420, 180))),
        },
        "drawing_crop": {
            "region": _region_payload(request.drawing_region),
            "image": _image_data_url(_scaled(drawing_crop, QSize(420, 220))),
        },
        "vision": None
        if vision is None
        else {
            "text": vision.text,
            "confidence": round(float(vision.confidence), 3),
            "message": vision.message,
        },
    }


def _normalize_request(payload: dict[str, Any]) -> dict[str, Any]:
    source_path = str(payload.get("source_path") or "").strip()
    if not source_path:
        raise ValueError("缺少 source_path。")
    return {
        "source_path": Path(source_path),
        "detect_serial": bool(payload.get("detect_serial", True)),
        "serial_region": _region_from_payload(payload.get("serial_region"), DEFAULT_SERIAL_REGION),
        "drawing_region": _region_from_payload(payload.get("drawing_region"), DEFAULT_DRAWING_REGION),
    }


def _region_from_payload(payload: Any, default: SerialVisionRegion) -> SerialVisionRegion:
    if not isinstance(payload, dict):
        return default
    return SerialVisionRegion(
        left=_float_value(payload.get("left"), default.left),
        top=_float_value(payload.get("top"), default.top),
        width=_float_value(payload.get("width"), default.width),
        height=_float_value(payload.get("height"), default.height),
    )


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _crop_region(image: QImage, region: SerialVisionRegion) -> QImage:
    left, top, width, height = serial_region_bounds(image.width(), image.height(), region)
    return image.copy(left, top, width, height)


def _scaled(image: QImage, size: QSize) -> QImage:
    return image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _image_data_url(image: QImage) -> str:
    payload = QByteArray()
    buffer = QBuffer(payload)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    data = bytes(payload.data())
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _image_on_white(image: QImage) -> QImage:
    if not image.hasAlphaChannel():
        return image
    output = QImage(image.size(), QImage.Format.Format_RGB32)
    output.fill(0xFFFFFFFF)
    painter = QPainter(output)
    painter.drawImage(0, 0, image)
    painter.end()
    return output


def _region_payload(region: SerialVisionRegion) -> dict[str, float]:
    return {
        "left": region.left,
        "top": region.top,
        "width": region.width,
        "height": region.height,
    }


def _ensure_app() -> None:
    QApplication.instance() or QApplication([])


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_stdin_json() -> str:
    return sys.stdin.buffer.read().decode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
