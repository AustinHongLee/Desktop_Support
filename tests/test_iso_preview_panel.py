from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QTabWidget  # noqa: E402

from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.plugins.iso_tools.serial_vision import SerialVisionRegion  # noqa: E402
from launcher.ui.iso_pdf_naming_dialog import FullPageCalibrationDialog, IsoPdfNamingDialog  # noqa: E402


class IsoPreviewPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_preview_panel_is_split_into_workflow_tabs(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        tabs = dialog.findChild(QTabWidget, "PreviewTabs")

        self.assertIsNotNone(tabs)
        assert tabs is not None
        self.assertEqual([tabs.tabText(index) for index in range(tabs.count())], ["預覽", "判讀", "校準", "確認"])

    def test_preview_tab_keeps_crop_panes_and_moves_full_page_to_dialog_button(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        panes = dialog.findChildren(QLabel, "PdfPreviewImage")
        button_texts = [button.text() for button in dialog.findChildren(QPushButton)]

        self.assertEqual(len(panes), 2)
        self.assertIn(dialog._top_right_preview, panes)
        self.assertIn(dialog._bottom_right_preview, panes)
        self.assertIn("調整全圖定位", button_texts)

    def test_pdf_preview_regions_render_from_page_image(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())
        image = QImage(1000, 1000, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFFFF)
        dialog._preview_image = image

        dialog._render_pdf_preview_regions()

        self.assertFalse(dialog._top_right_preview.pixmap().isNull())
        self.assertFalse(dialog._bottom_right_preview.pixmap().isNull())

    def test_calibration_page_selector_syncs_serial_region(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())
        region = SerialVisionRegion(left=0.5, top=0.1, width=0.2, height=0.1)

        dialog._update_region_from_selector(region)

        self.assertEqual(dialog._serial_region_value, region)
        self.assertEqual(dialog._region_selector._region, region)

    def test_bottom_right_selector_has_independent_drawing_region(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())
        serial_region = SerialVisionRegion(left=0.5, top=0.1, width=0.2, height=0.1)
        drawing_region = SerialVisionRegion(left=0.4, top=0.7, width=0.5, height=0.2)
        image = QImage(1000, 1000, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFFFF)
        dialog._preview_image = image

        dialog._update_region_from_selector(serial_region)
        dialog._update_drawing_region_from_selector(drawing_region)

        self.assertEqual(dialog._serial_region_value, serial_region)
        self.assertEqual(dialog._drawing_region_value, drawing_region)
        self.assertFalse(dialog._bottom_right_preview.pixmap().isNull())

    def test_full_page_calibration_dialog_switches_between_serial_and_drawing_regions(self) -> None:
        image = QImage(1000, 1000, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFFFF)
        serial_region = SerialVisionRegion(left=0.5, top=0.1, width=0.2, height=0.1)
        drawing_region = SerialVisionRegion(left=0.4, top=0.7, width=0.5, height=0.2)
        dialog = FullPageCalibrationDialog(image, serial_region=serial_region, drawing_region=drawing_region)

        dialog._set_mode("drawing")
        updated = SerialVisionRegion(left=0.3, top=0.6, width=0.4, height=0.2)
        dialog._update_active_region(updated)

        self.assertEqual(dialog.serial_region(), serial_region)
        self.assertEqual(dialog.drawing_region(), updated)

    def test_batch_button_click_is_signal_safe(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())
        button = dialog.findChild(QPushButton, "BatchDetectButton")
        assert button is not None

        with patch.object(dialog, "_batch_detect_serials") as batch_detect:
            button.click()

        batch_detect.assert_called_once_with()

    def test_left_control_buttons_keep_primary_actions_visible(self) -> None:
        dialog = IsoPdfNamingDialog(LauncherContext.empty())

        button_texts = [button.text() for button in dialog.findChildren(QPushButton)]

        self.assertIn("選擇合併 PDF 並拆成單頁", button_texts)
        self.assertIn("選 ISO List", button_texts)
        self.assertIn("重新整理", button_texts)
        self.assertIn("一鍵產生命名草稿", button_texts)
        self.assertNotIn("拆成單頁 PDF", button_texts)
        self.assertNotIn("依 ISO List 更新命名", button_texts)


if __name__ == "__main__":
    unittest.main()
