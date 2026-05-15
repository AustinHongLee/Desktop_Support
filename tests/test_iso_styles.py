from __future__ import annotations

import unittest

from launcher.ui.iso_pdf.styles import workbench_stylesheet


class IsoStylesTests(unittest.TestCase):
    def test_workbench_stylesheet_contains_core_selectors(self) -> None:
        stylesheet = workbench_stylesheet()

        self.assertIn("QDialog", stylesheet)
        self.assertIn("QPdfView", stylesheet)
        self.assertIn("QTabWidget::pane", stylesheet)
        self.assertIn('QPushButton[primary="true"]', stylesheet)
        self.assertIn("QLabel#WorkflowStepChip", stylesheet)
        self.assertIn("QLabel#PdfPreviewImage", stylesheet)


if __name__ == "__main__":
    unittest.main()
