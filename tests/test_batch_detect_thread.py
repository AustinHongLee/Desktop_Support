from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialRegionCalibration, SerialVisionRegion, SerialVisionResult  # noqa: E402
from launcher.ui.iso_pdf.batch_detect import BatchDetectThread, SerialBatchPdfDetector, detect_serial_from_pdf  # noqa: E402


class BatchDetectThreadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_missing_pdf_returns_failure_result(self) -> None:
        result = detect_serial_from_pdf(Path("missing.pdf"), DEFAULT_SERIAL_REGION)

        self.assertEqual(result.text, "")
        self.assertEqual(result.message, "檔案不存在")

    def test_batch_detector_uses_fast_roi_before_full_page_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "page.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            image = QImage(120, 120, QImage.Format.Format_RGB32)
            detector = SerialBatchPdfDetector(DEFAULT_SERIAL_REGION)

            with unittest.mock.patch("launcher.ui.iso_pdf.batch_detect._render_first_pdf_page", return_value=image):
                with unittest.mock.patch(
                    "launcher.ui.iso_pdf.batch_detect.detect_serial_from_qimage",
                    return_value=SerialVisionResult("101", 0.95, "OK"),
                ) as fast_detect:
                    with unittest.mock.patch("launcher.ui.iso_pdf.batch_detect.calibrate_serial_region_from_qimage") as calibrate:
                        result = detector.detect(pdf)

            self.assertEqual(result.text, "101")
            self.assertIn("快速 ROI", result.message)
            fast_detect.assert_called_once()
            calibrate.assert_not_called()

    def test_batch_detector_falls_back_to_calibration_when_fast_roi_is_weak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "page.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            image = QImage(120, 120, QImage.Format.Format_RGB32)
            detector = SerialBatchPdfDetector(DEFAULT_SERIAL_REGION)
            calibrated = SerialVisionRegion(left=0.8, top=0.0, width=0.2, height=0.1)

            with unittest.mock.patch("launcher.ui.iso_pdf.batch_detect._render_first_pdf_page", return_value=image):
                with unittest.mock.patch(
                    "launcher.ui.iso_pdf.batch_detect.detect_serial_from_qimage",
                    side_effect=[
                        SerialVisionResult("10", 0.60, "weak"),
                        SerialVisionResult("101", 0.94, "OK"),
                    ],
                ):
                    with unittest.mock.patch(
                        "launcher.ui.iso_pdf.batch_detect.calibrate_serial_region_from_qimage",
                        return_value=SerialRegionCalibration(calibrated, 0.96, "自動校準：流水號"),
                    ):
                        result = detector.detect(pdf)

            self.assertEqual(result.text, "101")
            self.assertIn("自動 ROI", result.message)

    def test_cancel_stops_batch_before_all_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / f"page_{index}.pdf" for index in range(6)]
            processed: list[Path] = []
            completed: list[bool] = []

            def detector(path: Path, _region, _cache) -> SerialVisionResult:  # noqa: ANN001
                time.sleep(0.05)
                return SerialVisionResult(path.stem, 0.95, "OK")

            thread = BatchDetectThread(paths, DEFAULT_SERIAL_REGION, Path(tmp), detector=detector)
            loop = QEventLoop()

            def on_progress(_done: int, _total: int, path: object, _result: object) -> None:
                processed.append(path if isinstance(path, Path) else Path(str(path)))
                if len(processed) == 1:
                    thread.cancel()

            def on_completed(canceled: bool) -> None:
                completed.append(canceled)
                loop.quit()

            thread.progress.connect(on_progress)
            thread.completed.connect(on_completed)
            thread.start()
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            thread.wait(1000)

            self.assertTrue(completed)
            self.assertTrue(completed[0])
            self.assertGreaterEqual(len(processed), 1)
            self.assertLess(len(processed), len(paths))


if __name__ == "__main__":
    unittest.main()
