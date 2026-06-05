from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from launcher.app.tauri_iso_preview import IsoPreviewRequest, build_iso_preview  # noqa: E402


class TauriIsoPreviewTests(unittest.TestCase):
    def test_build_iso_preview_returns_page_and_crop_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "preview.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=420)
            with pdf.open("wb") as handle:
                writer.write(handle)

            payload = build_iso_preview(IsoPreviewRequest(source_path=pdf, detect_serial=False))

        self.assertEqual(payload["source_name"], "preview.pdf")
        self.assertGreater(payload["page"]["width"], 0)
        self.assertTrue(payload["page"]["image"].startswith("data:image/png;base64,"))
        self.assertTrue(payload["serial_crop"]["image"].startswith("data:image/png;base64,"))
        self.assertTrue(payload["drawing_crop"]["image"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
