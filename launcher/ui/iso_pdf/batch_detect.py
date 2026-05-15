from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeAlias

from PyQt6.QtCore import QSize, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtPdf import QPdfDocument

from launcher.plugins.iso_tools.serial_vision import (
    TWO_STAGE_MIN_CONFIDENCE,
    SerialVisionRegion,
    SerialVisionResult,
    calibrate_serial_region_from_qimage,
    detect_serial_from_qimage,
)
from launcher.ui.preview_cache import PdfPreviewCache


BatchDetector: TypeAlias = Callable[[Path, SerialVisionRegion, PdfPreviewCache | None], SerialVisionResult]
FAST_ROI_MIN_CONFIDENCE = 0.90


def detect_serial_from_pdf(
    path: Path,
    region: SerialVisionRegion,
    cache: PdfPreviewCache | None = None,
) -> SerialVisionResult:
    if not path.exists():
        return SerialVisionResult("", 0.0, "檔案不存在")
    return SerialBatchPdfDetector(region).detect(path, cache)


class SerialBatchPdfDetector:
    def __init__(
        self,
        fallback_region: SerialVisionRegion,
        *,
        fast_min_confidence: float = FAST_ROI_MIN_CONFIDENCE,
    ) -> None:
        self._fallback_region = fallback_region
        self._last_good_region: SerialVisionRegion | None = fallback_region
        self._fast_min_confidence = fast_min_confidence

    def __call__(
        self,
        path: Path,
        region: SerialVisionRegion,
        cache: PdfPreviewCache | None = None,
    ) -> SerialVisionResult:
        self._fallback_region = region
        return self.detect(path, cache)

    def detect(self, path: Path, cache: PdfPreviewCache | None = None) -> SerialVisionResult:
        if not path.exists():
            return SerialVisionResult("", 0.0, "檔案不存在")
        image_or_result = _render_first_pdf_page(path, cache)
        if isinstance(image_or_result, SerialVisionResult):
            return image_or_result

        image = _image_on_white(image_or_result)
        for label, candidate_region in self._fast_regions():
            result = detect_serial_from_qimage(image, candidate_region)
            if result.text and result.confidence >= self._fast_min_confidence:
                self._last_good_region = candidate_region
                return _with_message(result, f"{label}快速 ROI")

        calibration = calibrate_serial_region_from_qimage(image)
        if calibration.region is None:
            fallback_result = detect_serial_from_qimage(image, self._fallback_region)
            return _with_message(fallback_result, f"fallback ROI：{calibration.message}")

        self._last_good_region = calibration.region
        auto_result = detect_serial_from_qimage(image, calibration.region)
        if auto_result.text and auto_result.confidence >= TWO_STAGE_MIN_CONFIDENCE:
            return _with_message(auto_result, f"自動 ROI：{calibration.message}")

        fallback_result = detect_serial_from_qimage(image, self._fallback_region)
        if fallback_result.text:
            reason = "無結果" if not auto_result.text else f"低信心 {auto_result.confidence:.2f}"
            return _with_message(fallback_result, f"fallback ROI：自動 ROI {reason}（{calibration.message}）")
        if auto_result.text:
            return _with_message(auto_result, f"自動 ROI 低信心，fallback 無結果：{calibration.message}")
        return _with_message(fallback_result, f"fallback ROI：自動 ROI 無結果（{calibration.message}）")

    def _fast_regions(self) -> tuple[tuple[str, SerialVisionRegion], ...]:
        regions: list[tuple[str, SerialVisionRegion]] = []
        if self._last_good_region is not None:
            regions.append(("上一頁", self._last_good_region))
        if self._fallback_region not in [region for _label, region in regions]:
            regions.append(("設定", self._fallback_region))
        return tuple(regions)


def _render_first_pdf_page(path: Path, cache: PdfPreviewCache | None = None) -> QImage | SerialVisionResult:
    try:
        preview_path = cache.preview_path_for(path) if cache is not None else path
        document = QPdfDocument(None)
        try:
            error = document.load(str(preview_path))
            if error != QPdfDocument.Error.None_:
                return SerialVisionResult("", 0.0, f"PDF 無法載入 ({error.name})")
            if document.pageCount() <= 0:
                return SerialVisionResult("", 0.0, "PDF 沒有頁面")
            page_size = document.pagePointSize(0)
            image = document.render(
                0,
                QSize(max(1600, int(page_size.width() * 4.0)), max(2200, int(page_size.height() * 4.0))),
            )
            if image.isNull():
                return SerialVisionResult("", 0.0, "無法產生影像")
            return image
        finally:
            document.close()
    except Exception as exc:
        return SerialVisionResult("", 0.0, str(exc))


def _image_on_white(image: QImage) -> QImage:
    if not image.hasAlphaChannel():
        return image
    output = QImage(image.size(), QImage.Format.Format_RGB32)
    output.fill(0xFFFFFFFF)
    painter = QPainter(output)
    painter.drawImage(0, 0, image)
    painter.end()
    return output


def _with_message(result: SerialVisionResult, prefix: str) -> SerialVisionResult:
    message = f"{prefix}；{result.message}" if result.message else prefix
    return SerialVisionResult(result.text, result.confidence, message)


class BatchDetectThread(QThread):
    progress = pyqtSignal(int, int, object, object)
    completed = pyqtSignal(bool)

    def __init__(
        self,
        paths: Sequence[Path],
        region: SerialVisionRegion,
        temp_dir: Path,
        *,
        detector: BatchDetector | None = None,
    ) -> None:
        super().__init__()
        self._paths = tuple(paths)
        self._region = region
        self._temp_dir = temp_dir
        self._detector = detector
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        cache = PdfPreviewCache(self._temp_dir)
        detector = self._detector or SerialBatchPdfDetector(self._region)
        total = len(self._paths)
        canceled = False
        for index, path in enumerate(self._paths, start=1):
            if self._cancel_requested:
                canceled = True
                break
            result = detector(path, self._region, cache)
            self.progress.emit(index, total, path, result)
        if self._cancel_requested:
            canceled = True
        self.completed.emit(canceled)
