from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from launcher.plugins.pdf_tools.pdf_actions import split_pdf_pages


class PdfActionTests(unittest.TestCase):
    def test_split_pdf_pages_outputs_single_page_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pdf = folder / "sample.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_blank_page(width=72, height=72)
            with pdf.open("wb") as handle:
                writer.write(handle)

            result = split_pdf_pages({"context": {"files": [str(pdf)]}})

            output_dir = folder / "sample_pages"
            outputs = sorted(output_dir.glob("*.pdf"))
            self.assertEqual(len(outputs), 2)
            self.assertEqual(len(PdfReader(str(outputs[0])).pages), 1)
            self.assertEqual(result[1]["count"], 2)


if __name__ == "__main__":
    unittest.main()

