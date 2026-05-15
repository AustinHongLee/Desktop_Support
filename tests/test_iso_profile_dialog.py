from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.state_store import AppStateStore  # noqa: E402
from launcher.plugins.iso_tools.profile import IsoNamingProfile, save_iso_naming_profile  # noqa: E402
from launcher.plugins.iso_tools.serial_vision import SerialVisionRegion  # noqa: E402
from launcher.ui.iso_pdf_naming_dialog import IsoPdfNamingDialog  # noqa: E402


class IsoProfileDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_restores_profile_for_current_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            (pages / "page1.pdf").write_bytes(b"%PDF-1.4\n")
            iso_list = root / "iso.csv"
            iso_list.write_text("流水號,圖號\n1,A-001\n", encoding="utf-8")
            store = AppStateStore(root / "state.json")
            save_iso_naming_profile(
                store,
                pages,
                IsoNamingProfile(
                    serial_region=SerialVisionRegion(left=0.2, top=0.1, width=0.3, height=0.2),
                    drawing_region=SerialVisionRegion(left=0.4, top=0.7, width=0.5, height=0.2),
                    pattern="{serial}-{line}.pdf",
                    iso_list_path=iso_list,
                    sheet_name="CSV",
                    serial_col=0,
                    line_col=1,
                ),
            )

            dialog = IsoPdfNamingDialog(
                LauncherContext(folder=pages, source="test"),
                state_store=store,
            )

            self.assertEqual(dialog._pattern.text(), "{serial}-{line}.pdf")
            self.assertEqual(dialog._serial_region().left, 0.2)
            self.assertEqual(dialog._drawing_region().top, 0.7)
            self.assertEqual(dialog._sheet_combo.currentText(), "CSV")
            self.assertEqual(dialog._serial_column_combo.currentData(), 0)
            self.assertEqual(dialog._line_column_combo.currentData(), 1)
            self.assertEqual(dialog._table.item(0, 5).text(), "1-A-001.pdf")


if __name__ == "__main__":
    unittest.main()
