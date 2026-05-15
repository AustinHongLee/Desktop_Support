from __future__ import annotations

import os
import re
import shutil
import tempfile
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSize, QTimer, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QImage, QPainter, QPixmap
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from launcher.core.context_model import LauncherContext
from launcher.core.state_store import AppStateStore, default_state_path
from launcher.plugins.iso_tools.iso_naming import (
    IsoRecord,
    IsoTable,
    build_record_lookup,
    format_iso_name,
    guess_iso_columns,
    list_iso_sheets,
    natural_pdf_key,
    parse_iso_filename,
    read_iso_table,
    records_from_table,
    split_pdf_to_pages,
)
from launcher.plugins.iso_tools.profile import DEFAULT_DRAWING_REGION, IsoNamingProfile, load_iso_naming_profile, save_iso_naming_profile
from launcher.plugins.iso_tools.rename_plan import build_rename_plan
from launcher.plugins.iso_tools.serial_correction import correct_result_with_iso_lookup
from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialVisionRegion, SerialVisionResult
from launcher.plugins.iso_tools.serial_vision import calibrate_serial_region_from_qimage, detect_serial_two_stage_from_qimage, serial_region_bounds
from launcher.plugins.rename_tools.rename_actions import RenameOperation, _apply_operations, _validate_operations
from launcher.ui.iso_pdf.batch_detect import BatchDetectThread, detect_serial_from_pdf
from launcher.ui.iso_pdf.region_selector import RegionSelector
from launcher.ui.iso_pdf.styles import workbench_stylesheet
from launcher.ui.preview_cache import PdfPreviewCache
from launcher.ui.rename_plan_dialog import RenamePlanDialog


SERIAL_AUTO_FILL_CONFIDENCE = 0.70
REVIEW_ROW_BACKGROUND = QColor("#fff2b8")
REVIEW_ROW_FOREGROUND = QColor("#2a2100")
REVIEW_KIND_STYLES = {
    "low_confidence": (QColor("#fff2b8"), QColor("#2a2100")),
    "not_in_iso": (QColor("#ffd6d6"), QColor("#4a1010")),
    "conflict": (QColor("#ffc8a6"), QColor("#4a2108")),
    "correction": (QColor("#e5f0ff"), QColor("#14345f")),
    "missing": (QColor("#e8e8e8"), QColor("#263238")),
    "review": (REVIEW_ROW_BACKGROUND, REVIEW_ROW_FOREGROUND),
}


class IsoPdfNamingDialog(QDialog):
    def __init__(
        self,
        context: LauncherContext,
        parent=None,  # noqa: ANN001
        *,
        state_store: AppStateStore | None = None,
    ) -> None:
        super().__init__(parent)
        self._context = context
        self._state_store = state_store or AppStateStore()
        self._combine_pdf: Path | None = None
        self._page_folder: Path | None = None
        self._pdfs: list[Path] = []
        self._records: list[IsoRecord] = []
        self._iso_list_path: Path | None = None
        self._iso_table: IsoTable | None = None
        self._preview_path: Path | None = None
        self._preview_document_path: Path | None = None
        self._loaded_preview_document_path: Path | None = None
        self._preview_image: QImage | None = None
        self._detected_serial: str = ""
        self._detected_serial_confidence: float = 0.0
        self._serial_region_value = DEFAULT_SERIAL_REGION
        self._drawing_region_value = DEFAULT_DRAWING_REGION
        self._vision_results: dict[Path, SerialVisionResult] = {}
        self._review_issues: dict[Path, str] = {}
        self._row_problem_kinds: dict[Path, str] = {}
        self._problem_row_count = 0
        self._batch_thread: BatchDetectThread | None = None
        self._batch_progress: QProgressDialog | None = None
        self._batch_record_lookup: dict[str, IsoRecord] = {}
        self._batch_stats: dict[str, object] = {}
        self._batch_completion_pending = False
        self._one_click_workflow_active = False
        self._closing = False
        self._preview_temp_dir = Path(tempfile.gettempdir()) / f"engineering_launcher_pdf_preview_{uuid.uuid4().hex}"
        self._preview_temp_dir.mkdir(parents=True, exist_ok=True)
        self._preview_cache = PdfPreviewCache(self._preview_temp_dir)

        self.setWindowTitle("ISO PDF 命名工作台")
        self.setMinimumSize(1280, 760)
        self.resize(1440, 900)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._combine_path = QLineEdit()
        self._combine_path.setReadOnly(True)
        self._combine_path.setPlaceholderText("尚未選擇 combine PDF")
        self._page_folder_path = QLineEdit()
        self._page_folder_path.setReadOnly(True)
        self._page_folder_path.setPlaceholderText("尚未選擇頁面 PDF 資料夾")
        self._iso_label = QLabel("ISO list：尚未載入")
        self._iso_label.setWordWrap(True)
        self._sheet_combo = QComboBox()
        self._sheet_combo.setMinimumWidth(220)
        self._serial_column_combo = QComboBox()
        self._serial_column_combo.setMinimumWidth(220)
        self._line_column_combo = QComboBox()
        self._line_column_combo.setMinimumWidth(220)
        self._page_label = QLabel("頁面 PDF：0 個")
        self._page_label.setObjectName("PillLabel")
        self._workflow_source_chip = _step_chip("1 來源：未選")
        self._workflow_iso_chip = _step_chip("2 ISO：未載入")
        self._workflow_vision_chip = _step_chip("3 判讀：未執行")
        self._workflow_review_chip = _step_chip("4 確認：待資料")
        self._workflow_rename_chip = _step_chip("5 更名：待確認")
        self._pattern = QLineEdit("{serial}--{line}.pdf")
        self._pattern.setToolTip("可用變數：{serial} 流水號、{line} 完整圖號/檔名")
        self._pattern.editingFinished.connect(self._save_current_profile)
        self._terminal = QPlainTextEdit()
        self._terminal.setReadOnly(True)
        self._terminal.setMinimumHeight(120)
        self._terminal.setPlaceholderText("終端機")
        self._preview_info = QLabel("預覽：尚未選擇 PDF")
        self._preview_info.setObjectName("PreviewInfo")
        self._preview_info.setWordWrap(True)
        self._serial_vision_label = QLabel("影像判讀流水號：尚未判讀")
        self._serial_vision_label.setObjectName("VisionInfo")
        self._serial_vision_label.setWordWrap(True)
        self._preview_doc = QPdfDocument(self)
        self._preview_view = QPdfView(None)
        self._preview_view.setDocument(self._preview_doc)
        self._preview_view.setPageMode(QPdfView.PageMode.SinglePage)
        self._preview_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self._preview_view.setMinimumHeight(260)
        self._top_right_preview = _preview_image_label("右上角\nsort / 流水號")
        self._bottom_right_preview = _preview_image_label("右下角\n圖號 / 標題欄")
        self._bottom_right_preview.setMinimumHeight(150)
        self._corner_preview = QLabel("流水號判讀區")
        self._corner_preview.setObjectName("CornerPreview")
        self._corner_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._corner_preview.setMinimumHeight(120)
        self._region_selector = RegionSelector()
        self._region_selector.dragStarted.connect(self._begin_region_edit)
        self._region_selector.regionChanged.connect(self._update_region_from_selector)
        self._region_selector.regionCommitted.connect(self._commit_region_from_selector)

        self._problem_only_check = QCheckBox("只看問題列")
        self._problem_only_check.toggled.connect(self._apply_table_filter)
        self._problem_summary_label = QLabel("問題列：0 / 0")
        self._problem_summary_label.setObjectName("TableSummary")
        self._table_search = QLineEdit()
        self._table_search.setPlaceholderText("搜尋 old/new/流水號/圖號/狀態")
        self._table_search.setClearButtonEnabled(True)
        self._table_search.textChanged.connect(self._apply_table_filter)
        self._next_problem_button = QPushButton("下一個問題")
        self._next_problem_button.clicked.connect(self._select_next_problem_row)

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(["套用", "old name", "page", "sort/流水號", "圖號/檔名", "new name", "狀態", "判讀信心"])
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemSelectionChanged.connect(self._update_preview_from_selection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_workspace(), 1)

        self._apply_style()
        self._update_workflow_status()
        self._log("ISO PDF 命名工作台已啟動。")
        self._load_context(context)
        self._auto_prepare_from_context()

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("ISO PDF 命名工作台")
        title.setObjectName("DialogTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self._page_label)

        step_row = QHBoxLayout()
        step_row.setSpacing(6)
        for chip in (
            self._workflow_source_chip,
            self._workflow_iso_chip,
            self._workflow_vision_chip,
            self._workflow_review_chip,
            self._workflow_rename_chip,
        ):
            step_row.addWidget(chip)
        step_row.addStretch(1)

        layout.addLayout(title_row)
        layout.addLayout(step_row)
        return header

    def _build_workspace(self) -> QSplitter:
        workspace = QSplitter(Qt.Orientation.Vertical)
        workspace.setChildrenCollapsible(False)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        control_panel = self._build_control_panel()
        table_panel = self._build_table_panel()
        preview_panel = self._build_preview_panel()
        body.addWidget(control_panel)
        body.addWidget(table_panel)
        body.addWidget(preview_panel)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([390, 680, 330])

        workspace.addWidget(body)
        workspace.addWidget(self._build_terminal_group())
        workspace.setStretchFactor(0, 1)
        workspace.setStretchFactor(1, 0)
        workspace.setSizes([680, 150])
        return workspace

    def _build_control_panel(self) -> QScrollArea:
        scroller = QScrollArea()
        scroller.setObjectName("ControlScroller")
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setMinimumWidth(380)
        scroller.setMaximumWidth(450)

        panel = QWidget()
        panel.setObjectName("ControlPanel")
        panel.setMinimumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._build_source_group())
        layout.addWidget(self._build_naming_group())
        layout.addStretch(1)
        scroller.setWidget(panel)
        return scroller

    def _build_table_panel(self) -> QGroupBox:
        group = QGroupBox("更名表")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self._problem_only_check)
        toolbar.addWidget(self._problem_summary_label)
        toolbar.addStretch(1)
        toolbar.addWidget(self._table_search, 1)
        toolbar.addWidget(self._next_problem_button)
        layout.addLayout(toolbar)
        layout.addWidget(self._table, 1)
        return group

    def _build_terminal_group(self) -> QGroupBox:
        group = QGroupBox("終端機")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.addWidget(self._terminal)
        return group

    def _build_preview_panel(self) -> QGroupBox:
        group = QGroupBox("PDF 預覽")
        group.setMinimumWidth(340)
        group.setMaximumWidth(480)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        open_button = QPushButton("開啟目前 PDF")
        open_button.clicked.connect(self._open_preview_pdf)
        refresh_button = QPushButton("刷新預覽")
        refresh_button.clicked.connect(self._refresh_current_preview)
        detect_button = QPushButton("判讀目前頁")
        detect_button.clicked.connect(self._detect_current_preview_image)
        calibrate_button = QPushButton("自動校準框")
        calibrate_button.clicked.connect(self._auto_calibrate_serial_region)
        reset_region_button = QPushButton("重設框")
        reset_region_button.clicked.connect(self._reset_serial_region)
        apply_serial_button = QPushButton("填入判讀流水號")
        apply_serial_button.clicked.connect(self._apply_detected_serial_to_row)
        self._batch_serial_button = QPushButton("批次判讀流水號")
        self._batch_serial_button.setObjectName("BatchDetectButton")
        self._batch_serial_button.clicked.connect(lambda: self._batch_detect_serials())
        confirm_review_button = QPushButton("確認此列")
        confirm_review_button.clicked.connect(self._confirm_current_review_issue)

        self._preview_tabs = QTabWidget()
        self._preview_tabs.setObjectName("PreviewTabs")
        self._preview_tabs.addTab(self._build_pdf_preview_tab(open_button, refresh_button), "預覽")
        self._preview_tabs.addTab(self._build_detection_tab(detect_button, apply_serial_button), "判讀")
        self._preview_tabs.addTab(self._build_calibration_tab(calibrate_button, reset_region_button), "校準")
        self._preview_tabs.addTab(self._build_review_tab(confirm_review_button), "確認")
        layout.addWidget(self._preview_tabs, 1)
        return group

    def _build_pdf_preview_tab(self, open_button: QPushButton, refresh_button: QPushButton) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        button_row = QHBoxLayout()
        button_row.addWidget(open_button)
        button_row.addWidget(refresh_button)
        calibrate_full_button = QPushButton("調整全圖定位")
        calibrate_full_button.clicked.connect(self._open_full_page_calibration)
        button_row.addWidget(calibrate_full_button)
        layout.addWidget(self._preview_info)
        layout.addWidget(_field_label("右上角：sort / 流水號"))
        layout.addWidget(self._top_right_preview)
        layout.addWidget(_field_label("右下角：圖號 / 標題欄"))
        layout.addWidget(self._bottom_right_preview)
        layout.addLayout(button_row)
        return tab

    def _build_detection_tab(self, detect_button: QPushButton, apply_serial_button: QPushButton) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self._serial_vision_label)
        layout.addWidget(detect_button)
        layout.addWidget(apply_serial_button)
        layout.addWidget(self._batch_serial_button)
        layout.addStretch(1)
        return tab

    def _build_calibration_tab(self, calibrate_button: QPushButton, reset_region_button: QPushButton) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        button_row = QHBoxLayout()
        button_row.addWidget(calibrate_button)
        button_row.addWidget(reset_region_button)
        layout.addLayout(button_row)
        layout.addWidget(_field_label("頁面定位"))
        layout.addWidget(self._region_selector, 1)
        layout.addWidget(_field_label("裁切預覽"))
        layout.addWidget(self._corner_preview)
        return tab

    def _build_review_tab(self, confirm_review_button: QPushButton) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        next_problem_button = QPushButton("下一個問題")
        next_problem_button.clicked.connect(self._select_next_problem_row)
        layout.addWidget(next_problem_button)
        layout.addWidget(confirm_review_button)
        layout.addStretch(1)
        return tab

    def _reset_serial_region(self) -> None:
        self._serial_region_value = DEFAULT_SERIAL_REGION
        self._sync_region_selectors(DEFAULT_SERIAL_REGION)
        self._save_current_profile()
        self._update_region_preview(detect=True)
        self._log(f"[影像判讀] 判讀區已重設：{self._serial_region_text()}")

    def _auto_calibrate_serial_region(self) -> None:
        if self._preview_image is None or self._preview_image.isNull():
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可校準的預覽影像。")
            return
        self._set_serial_vision_result("", 0.0, "影像判讀流水號：自動校準中")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            calibration = calibrate_serial_region_from_qimage(self._preview_image)
        finally:
            QApplication.restoreOverrideCursor()
        if calibration.region is None:
            self._set_serial_vision_result("", 0.0, f"影像判讀流水號：{calibration.message}")
            QMessageBox.warning(self, "ISO PDF 命名工作台", calibration.message)
            self._log(f"[影像判讀] 自動校準失敗：{calibration.message}")
            return
        self._serial_region_value = calibration.region
        self._sync_region_selectors(calibration.region)
        self._save_current_profile()
        self._update_region_preview(detect=True)
        self._log(
            f"[影像判讀] 自動校準完成：{calibration.message}，"
            f"信心 {calibration.confidence:.2f}，判讀區 {self._serial_region_text()}"
        )

    def _begin_region_edit(self) -> None:
        self._set_serial_vision_result("", 0.0, "影像判讀流水號：調整判讀區中，暫停判讀")

    def _update_region_from_selector(self, region: SerialVisionRegion) -> None:
        self._serial_region_value = region
        self._sync_region_selectors(region)
        self._update_region_preview(detect=False)

    def _commit_region_from_selector(self, region: SerialVisionRegion) -> None:
        self._serial_region_value = region
        self._sync_region_selectors(region)
        self._save_current_profile()
        self._update_region_preview(detect=True)

    def _serial_region(self) -> SerialVisionRegion:
        return self._serial_region_value

    def _sync_region_selectors(self, region: SerialVisionRegion) -> None:
        self._region_selector.set_region(region)

    def _begin_drawing_region_edit(self) -> None:
        self._log("[預覽] 調整右下角圖號/標題欄框。")

    def _update_drawing_region_from_selector(self, region: SerialVisionRegion) -> None:
        self._drawing_region_value = region
        self._sync_drawing_region_selector(region)
        self._render_pdf_preview_regions()

    def _commit_drawing_region_from_selector(self, region: SerialVisionRegion) -> None:
        self._drawing_region_value = region
        self._sync_drawing_region_selector(region)
        self._save_current_profile()
        self._render_pdf_preview_regions()
        self._log(f"[預覽] 右下角圖號/標題欄框已更新：{self._drawing_region_text()}")

    def _drawing_region(self) -> SerialVisionRegion:
        return self._drawing_region_value

    def _sync_drawing_region_selector(self, region: SerialVisionRegion) -> None:
        self._drawing_region_value = region

    def _serial_region_text(self) -> str:
        region = self._serial_region()
        return (
            f"左 {region.left:.2f}、上 {region.top:.2f}、"
            f"寬 {region.width:.2f}、高 {region.height:.2f}"
        )

    def _drawing_region_text(self) -> str:
        region = self._drawing_region()
        return (
            f"左 {region.left:.2f}、上 {region.top:.2f}、"
            f"寬 {region.width:.2f}、高 {region.height:.2f}"
        )

    def _build_source_group(self) -> QGroupBox:
        group = QGroupBox("PDF 來源與拆頁")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(8)
        choose_and_split_button = QPushButton("選擇合併 PDF 並拆成單頁")
        choose_and_split_button.setProperty("primary", True)
        choose_and_split_button.clicked.connect(self._choose_combine_pdf_and_split)
        more_button = QPushButton("更多功能")
        more_button.setMenu(self._build_source_more_menu())
        primary_row.addWidget(choose_and_split_button, 1)
        primary_row.addWidget(more_button)

        layout.addLayout(primary_row)
        layout.addWidget(_field_label("合併 PDF"))
        layout.addWidget(self._combine_path)
        layout.addWidget(_field_label("單頁 PDF 資料夾"))
        layout.addWidget(self._page_folder_path)
        return group

    def _build_source_more_menu(self) -> QMenu:
        menu = QMenu(self)
        use_context = QAction("載入工具列目前來源", menu)
        use_context.triggered.connect(self._load_current_context_and_auto_prepare)
        choose_combine = QAction("只選擇合併 PDF", menu)
        choose_combine.triggered.connect(self._choose_combine_pdf)
        split = QAction("拆目前合併 PDF", menu)
        split.triggered.connect(lambda: self._split_combine_pdf())
        choose_folder = QAction("選擇單頁 PDF 資料夾", menu)
        choose_folder.triggered.connect(self._choose_page_folder)
        scan = QAction("重新讀取單頁 PDF", menu)
        scan.triggered.connect(self._scan_page_folder)
        menu.addAction(use_context)
        menu.addSeparator()
        menu.addAction(choose_combine)
        menu.addAction(split)
        menu.addSeparator()
        menu.addAction(choose_folder)
        menu.addAction(scan)
        return menu

    def _build_naming_group(self) -> QGroupBox:
        group = QGroupBox("ISO List 與命名")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 18, 12, 12)
        layout.setSpacing(8)

        load_iso_button = QPushButton("選 ISO List")
        load_iso_button.clicked.connect(self._load_iso_list)
        refresh_iso_button = QPushButton("重新整理")
        refresh_iso_button.clicked.connect(self._refresh_iso_naming)
        more_button = QPushButton("更多功能")
        more_button.setMenu(self._build_naming_more_menu())
        self._one_click_button = QPushButton("一鍵產生命名草稿")
        self._one_click_button.setObjectName("OneClickDraftButton")
        self._one_click_button.setProperty("primary", True)
        self._one_click_button.clicked.connect(lambda: self._start_one_click_workflow())

        iso_buttons = QHBoxLayout()
        iso_buttons.setSpacing(8)
        iso_buttons.addWidget(load_iso_button, 1)
        iso_buttons.addWidget(refresh_iso_button, 1)
        iso_buttons.addWidget(more_button)

        action_buttons = QGridLayout()
        action_buttons.setHorizontalSpacing(8)
        action_buttons.setVerticalSpacing(8)
        action_buttons.addWidget(self._one_click_button, 0, 0, 1, 2)

        layout.addWidget(self._iso_label)
        layout.addLayout(iso_buttons)
        layout.addWidget(_field_label("Sheet"))
        layout.addWidget(self._sheet_combo)
        layout.addWidget(_field_label("流水號欄"))
        layout.addWidget(self._serial_column_combo)
        layout.addWidget(_field_label("圖號/檔名欄"))
        layout.addWidget(self._line_column_combo)
        layout.addWidget(_field_label("命名格式"))
        layout.addWidget(self._pattern)
        layout.addSpacing(4)
        layout.addLayout(action_buttons)
        return group

    def _build_naming_more_menu(self) -> QMenu:
        menu = QMenu(self)
        find_iso = QAction("找附近 ISO List", menu)
        find_iso.triggered.connect(self._find_nearby_iso_list)
        read_sheet = QAction("讀取 Sheet", menu)
        read_sheet.triggered.connect(lambda: self._read_selected_sheet())
        auto_columns = QAction("自動判讀欄位", menu)
        auto_columns.triggered.connect(self._auto_select_columns)
        apply_columns = QAction("套用欄位", menu)
        apply_columns.triggered.connect(lambda: self._apply_selected_columns())
        regenerate = QAction("依 ISO List 更新命名", menu)
        regenerate.triggered.connect(self._regenerate_names)
        check = QAction("勾選可更名", menu)
        check.triggered.connect(self._check_renames)
        execute = QAction("套用更名", menu)
        execute.triggered.connect(self._execute)
        menu.addAction(find_iso)
        menu.addSeparator()
        menu.addAction(read_sheet)
        menu.addAction(auto_columns)
        menu.addAction(apply_columns)
        menu.addSeparator()
        menu.addAction(regenerate)
        menu.addAction(check)
        menu.addAction(execute)
        return menu

    def _log(self, message: str) -> None:
        self._terminal.appendPlainText(message)
        scrollbar = self._terminal.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        _append_iso_workbench_log(message)

    def _load_context(self, context: LauncherContext) -> None:
        pdfs = self._resolve_pdfs(context)
        if len(pdfs) == 1:
            self._combine_pdf = pdfs[0]
            self._page_folder = pdfs[0].with_name(f"{pdfs[0].stem}_pages")
            self._pdfs = [pdfs[0]]
        elif len(pdfs) > 1:
            self._combine_pdf = None
            self._page_folder = pdfs[0].parent
            self._pdfs = pdfs
        elif context.folder and context.folder.exists():
            self._combine_pdf = None
            self._page_folder = context.folder
            self._pdfs = self._pdfs_from_folder(context.folder)
        else:
            self._combine_pdf = None
            self._page_folder = None
            self._pdfs = []
        self._update_source_labels()
        self._load_rows()
        self._load_profile_for_current_folder()

    def _load_current_context_and_auto_prepare(self) -> None:
        self._load_context(self._context)
        self._auto_prepare_from_context()

    def _auto_prepare_from_context(self) -> None:
        if self._should_auto_split_current_pdf():
            assert self._combine_pdf is not None
            self._log(f"[啟動] 偵測到合併 PDF，準備拆成單頁：{self._combine_pdf}")
            if self._split_combine_pdf(show_message=False):
                self._log(f"[啟動] 已自動拆頁並載入：{self._page_folder}")
            else:
                self._log("[啟動] 自動拆頁失敗，保留目前 PDF 來源。")

        if not self._records and self._iso_list_path is None:
            candidate = self._auto_xlsx_candidate()
            if candidate is not None:
                self._log(f"[啟動] 偵測到 ISO List，準備載入：{candidate}")
                if not self._load_iso_list_path(candidate, show_errors=False):
                    self._log("[啟動] ISO List 自動載入失敗，請手動選擇。")

    def _should_auto_split_current_pdf(self) -> bool:
        if self._combine_pdf is None or not self._combine_pdf.exists():
            return False
        if self._pdfs != [self._combine_pdf]:
            return False
        if self._combine_pdf.parent.name.lower().endswith("_pages"):
            return False
        return not _looks_like_page_pdf(self._combine_pdf)

    def _auto_xlsx_candidate(self) -> Path | None:
        for path in self._nearby_iso_list_candidates():
            if path.suffix.lower() == ".xlsx":
                return path
        return None

    def _profile_folder(self) -> Path | None:
        if self._page_folder is not None:
            return self._page_folder if self._page_folder.is_dir() else self._page_folder.parent
        if self._combine_pdf is not None:
            return self._combine_pdf.parent
        if self._context.folder is not None:
            return self._context.folder
        return None

    def _load_profile_for_current_folder(self) -> None:
        folder = self._profile_folder()
        if folder is None:
            return
        profile = load_iso_naming_profile(self._state_store, folder)
        if profile is None:
            return
        self._serial_region_value = profile.serial_region
        self._drawing_region_value = profile.drawing_region
        self._sync_region_selectors(profile.serial_region)
        self._sync_drawing_region_selector(profile.drawing_region)
        self._pattern.setText(profile.pattern)
        restored_iso = False
        if profile.iso_list_path is not None:
            if profile.iso_list_path.exists():
                restored_iso = self._load_iso_list_path(
                    profile.iso_list_path,
                    preferred_sheet=profile.sheet_name,
                    preferred_serial_col=profile.serial_col,
                    preferred_line_col=profile.line_col,
                    show_errors=False,
                )
            else:
                self._log(f"[Profile] ISO List 不存在，略過還原：{profile.iso_list_path}")
        if not restored_iso:
            self._regenerate_names()
        self._log(f"[Profile] 已還原資料夾設定：{folder}")

    def _current_profile(self) -> IsoNamingProfile:
        return IsoNamingProfile(
            serial_region=self._serial_region(),
            drawing_region=self._drawing_region(),
            confidence_threshold=SERIAL_AUTO_FILL_CONFIDENCE,
            pattern=self._pattern.text().strip() or "{serial}--{line}.pdf",
            iso_list_path=self._iso_list_path,
            sheet_name=self._sheet_combo.currentText().strip() or None,
            serial_col=self._serial_column_combo.currentData(),
            line_col=self._line_column_combo.currentData(),
        )

    def _save_current_profile(self) -> None:
        folder = self._profile_folder()
        if folder is None:
            return
        save_iso_naming_profile(self._state_store, folder, self._current_profile())

    def _resolve_pdfs(self, context: LauncherContext) -> list[Path]:
        if context.files:
            return sorted((path for path in context.files if path.suffix.lower() == ".pdf" and path.exists()), key=natural_pdf_key)
        if context.folder and context.folder.exists():
            return self._pdfs_from_folder(context.folder)
        return []

    def _pdfs_from_folder(self, folder: Path) -> list[Path]:
        return sorted((path for path in folder.iterdir() if path.suffix.lower() == ".pdf"), key=natural_pdf_key)

    def _choose_combine_pdf(self) -> None:
        file_name, _selected = QFileDialog.getOpenFileName(
            self,
            "選擇 combine PDF",
            str(self._context.folder or Path.home()),
            "PDF (*.pdf)",
        )
        if not file_name:
            return
        self._combine_pdf = Path(file_name)
        self._page_folder = self._combine_pdf.with_name(f"{self._combine_pdf.stem}_pages")
        self._pdfs = [self._combine_pdf]
        self._update_source_labels()
        self._load_rows()
        self._load_profile_for_current_folder()

    def _choose_combine_pdf_and_split(self) -> None:
        self._choose_combine_pdf()
        if self._combine_pdf is None:
            return
        if self._split_combine_pdf(show_message=False):
            QMessageBox.information(self, "ISO PDF 命名工作台", f"已拆成 {len(self._pdfs)} 個單頁 PDF。")

    def _choose_page_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇頁面 PDF 資料夾", str(self._context.folder or Path.home()))
        if not folder:
            return
        self._page_folder = Path(folder)
        self._combine_pdf = None
        self._scan_page_folder()

    def _scan_page_folder(self) -> None:
        if self._page_folder is None:
            QMessageBox.information(self, "ISO PDF 命名工作台", "請先選擇頁面 PDF 資料夾。")
            return
        self._pdfs = self._pdfs_from_folder(self._page_folder)
        self._update_source_labels()
        self._load_rows()
        self._load_profile_for_current_folder()

    def _split_combine_pdf(self, *, show_message: bool = True) -> bool:
        if self._combine_pdf is None:
            if show_message:
                QMessageBox.information(self, "ISO PDF 命名工作台", "請先選擇 combine PDF。")
            return False
        self._pause_preview_for_pdf_write("正在拆分 PDF，已暫時關閉預覽以避免檔案鎖定。")
        try:
            outputs = split_pdf_to_pages(self._combine_pdf)
        except Exception as exc:
            self._log(f"[失敗] PDF 拆頁失敗：{exc}")
            if show_message:
                QMessageBox.critical(self, "ISO PDF 命名工作台", str(exc))
            return False
        self._page_folder = outputs[0].parent if outputs else self._combine_pdf.with_name(f"{self._combine_pdf.stem}_pages")
        self._pdfs = outputs
        self._update_source_labels()
        self._load_rows()
        self._load_profile_for_current_folder()
        self._regenerate_names()
        if show_message:
            QMessageBox.information(self, "ISO PDF 命名工作台", f"已分割 {len(outputs)} 頁，並重新產生命名。")
        return True

    def _load_rows(self) -> None:
        current_paths = set(self._pdfs)
        self._review_issues = {path: reason for path, reason in self._review_issues.items() if path in current_paths}
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._pdfs))
        lookup = build_record_lookup(self._records)
        for row, path in enumerate(self._pdfs):
            parsed = parse_iso_filename(path.name)
            serial = parsed.serial if parsed else str(row + 1)
            record = lookup.get(serial)
            line_no = record.line_no if record else (parsed.line_no if parsed else "")
            new_name = format_iso_name(self._pattern.text(), serial=serial, line=line_no)

            apply_item = QTableWidgetItem()
            apply_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            apply_item.setCheckState(Qt.CheckState.Checked if new_name and new_name != path.name else Qt.CheckState.Unchecked)

            self._table.setItem(row, 0, apply_item)
            self._table.setItem(row, 1, _readonly_item(path.name))
            self._table.setItem(row, 2, _readonly_item(str(row + 1)))
            self._table.setItem(row, 3, QTableWidgetItem(serial))
            self._table.setItem(row, 4, QTableWidgetItem(line_no))
            self._table.setItem(row, 5, QTableWidgetItem(new_name))
            self._table.setItem(row, 6, _readonly_item(""))
            self._table.setItem(row, 7, _readonly_item(_vision_cell_text(self._vision_results.get(path))))
        self._table.blockSignals(False)
        self._refresh_statuses()
        self._update_source_labels()
        if self._pdfs:
            self._table.setCurrentCell(0, 1)
            self._show_pdf_preview(self._pdfs[0])
        else:
            self._clear_preview()

    def _update_preview_from_selection(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._pdfs):
            self._clear_preview()
            return
        self._show_pdf_preview(self._pdfs[row])

    def _refresh_current_preview(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._pdfs):
            self._clear_preview()
            return
        self._show_pdf_preview(self._pdfs[row], force_reload=True)

    def _show_pdf_preview(self, path: Path, *, force_reload: bool = False, detect: bool = True) -> None:
        self._preview_path = path
        if not path.exists():
            self._clear_preview(f"預覽：找不到檔案\n{path}")
            return
        try:
            preview_path = self._copy_pdf_for_preview(path)
        except Exception as exc:
            self._clear_preview(f"預覽：無法建立暫存複本\n{exc}")
            return
        if (
            not force_reload
            and self._loaded_preview_document_path == preview_path
            and self._preview_doc.status() == QPdfDocument.Status.Ready
        ):
            self._preview_info.setText(f"預覽：{path.name}")
            return
        self._preview_doc.close()
        self._loaded_preview_document_path = None
        error = self._preview_doc.load(str(preview_path))
        if error != QPdfDocument.Error.None_:
            self._clear_preview(f"預覽：PDF 無法載入 ({error.name})\n{path.name}")
            return
        self._loaded_preview_document_path = preview_path
        self._preview_info.setText(f"預覽：{path.name}")
        self._render_corner_preview(detect=detect)

    def _copy_pdf_for_preview(self, path: Path) -> Path:
        preview_path = self._preview_cache.preview_path_for(path)
        self._preview_document_path = preview_path
        return preview_path

    def _render_corner_preview(self, *, detect: bool = True) -> None:
        if self._preview_doc.status() != QPdfDocument.Status.Ready or self._preview_doc.pageCount() <= 0:
            self._preview_image = None
            self._region_selector.clear_image()
            self._clear_pdf_preview_regions()
            self._corner_preview.setText("流水號判讀區")
            self._corner_preview.setPixmap(QPixmap())
            self._set_serial_vision_result("", 0.0, "影像判讀流水號：無可判讀頁面")
            return
        page_size = self._preview_doc.pagePointSize(0)
        render_size = QSize(max(800, int(page_size.width() * 2.0)), max(1100, int(page_size.height() * 2.0)))
        image = self._preview_doc.render(0, render_size)
        if image.isNull():
            self._preview_image = None
            self._region_selector.clear_image()
            self._clear_pdf_preview_regions()
            self._corner_preview.setText("無法產生判讀區預覽")
            self._corner_preview.setPixmap(QPixmap())
            self._set_serial_vision_result("", 0.0, "影像判讀流水號：無法產生影像")
            return
        self._preview_image = _image_on_white(image)
        self._render_pdf_preview_regions()
        self._region_selector.set_image(self._preview_image)
        self._sync_region_selectors(self._serial_region())
        self._sync_drawing_region_selector(self._drawing_region())
        self._update_region_preview(detect=detect)

    def _render_pdf_preview_regions(self) -> None:
        image = self._preview_image
        if image is None or image.isNull():
            self._clear_pdf_preview_regions()
            return
        self._set_preview_region(
            self._top_right_preview,
            image,
            self._serial_region(),
            QSize(360, 130),
        )
        self._set_preview_region(
            self._bottom_right_preview,
            image,
            self._drawing_region(),
            QSize(360, 150),
        )

    def _set_preview_region(self, label: QLabel, image: QImage, region: SerialVisionRegion, size: QSize) -> None:
        left, top, crop_width, crop_height = serial_region_bounds(image.width(), image.height(), region)
        crop = image.copy(left, top, crop_width, crop_height)
        label.setPixmap(
            QPixmap.fromImage(crop).scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        label.setText("")

    def _clear_pdf_preview_regions(self) -> None:
        for label, text in (
            (self._top_right_preview, "右上角\nsort / 流水號"),
            (self._bottom_right_preview, "右下角\n圖號 / 標題欄"),
        ):
            label.setPixmap(QPixmap())
            label.setText(text)

    def _open_full_page_calibration(self) -> None:
        if self._preview_image is None or self._preview_image.isNull():
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可調整的預覽影像。")
            return
        dialog = FullPageCalibrationDialog(
            self._preview_image,
            serial_region=self._serial_region(),
            drawing_region=self._drawing_region(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._serial_region_value = dialog.serial_region()
        self._drawing_region_value = dialog.drawing_region()
        self._sync_region_selectors(self._serial_region())
        self._sync_drawing_region_selector(self._drawing_region())
        self._save_current_profile()
        self._render_pdf_preview_regions()
        self._update_region_preview(detect=True)
        self._log(
            "[預覽] 全圖定位已更新："
            f"流水號框 {self._serial_region_text()}；圖號框 {self._drawing_region_text()}"
        )

    def _update_region_preview(self, *, detect: bool) -> None:
        image = self._preview_image
        if image is None or image.isNull():
            return
        left, top, crop_width, crop_height = serial_region_bounds(image.width(), image.height(), self._serial_region())
        crop = image.copy(left, top, crop_width, crop_height)
        pixmap = QPixmap.fromImage(crop).scaled(
            QSize(360, 150),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._corner_preview.setPixmap(pixmap)
        self._corner_preview.setToolTip(self._serial_region_text())
        if detect:
            self._detect_serial_from_preview_image(image)

    def _detect_current_preview_image(self) -> None:
        if self._preview_image is None or self._preview_image.isNull():
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可判讀的預覽影像。")
            return
        self._detect_serial_from_preview_image(self._preview_image)

    def _detect_serial_from_preview_image(self, image) -> None:  # noqa: ANN001
        try:
            result = detect_serial_two_stage_from_qimage(image, fallback_region=self._serial_region())
        except Exception as exc:
            self._set_serial_vision_result("", 0.0, f"影像判讀流水號：失敗（{exc}）")
            return
        result = correct_result_with_iso_lookup(result, build_record_lookup(self._records) if self._records else {})
        if self._preview_path is not None:
            self._record_vision_result(self._preview_path, result)
        if not result.text:
            self._set_serial_vision_result("", result.confidence, f"影像判讀流水號：{result.message}")
            return
        self._set_serial_vision_result(
            result.text,
            result.confidence,
            f"影像判讀流水號：{result.text}  信心 {result.confidence:.2f}（{result.message}）",
        )

    def _set_serial_vision_result(self, serial: str, confidence: float, message: str) -> None:
        self._detected_serial = serial
        self._detected_serial_confidence = confidence
        self._serial_vision_label.setText(message)

    def _record_vision_result(self, path: Path, result: SerialVisionResult) -> None:
        self._vision_results[path] = result
        try:
            row = self._pdfs.index(path)
        except ValueError:
            return
        self._set_vision_cell(row, result)

    def _set_vision_cell(self, row: int, result: SerialVisionResult | None) -> None:
        item = self._table.item(row, 7)
        if item is None:
            item = _readonly_item("")
            self._table.setItem(row, 7, item)
        item.setText(_vision_cell_text(result))
        item.setToolTip(result.message if result else "")

    def _clear_preview(self, message: str = "預覽：尚未選擇 PDF") -> None:
        self._preview_path = None
        self._preview_document_path = None
        self._loaded_preview_document_path = None
        self._preview_image = None
        self._preview_doc.close()
        self._preview_info.setText(message)
        self._set_serial_vision_result("", 0.0, "影像判讀流水號：尚未判讀")
        self._region_selector.clear_image()
        self._clear_pdf_preview_regions()
        self._corner_preview.setPixmap(QPixmap())
        self._corner_preview.setText("流水號判讀區")

    def _pause_preview_for_pdf_write(self, message: str) -> None:
        self._clear_preview(message)
        self._log(f"[PDF] {message}")

    def _open_preview_pdf(self) -> None:
        if self._preview_path is None or not self._preview_path.exists():
            QMessageBox.information(self, "ISO PDF 命名工作台", "請先在更名表選擇一個 PDF。")
            return
        os.startfile(self._preview_path)  # noqa: S606

    def _start_one_click_workflow(self) -> None:
        try:
            self._run_one_click_workflow()
        except Exception as exc:
            self._one_click_workflow_active = False
            self._one_click_button.setEnabled(True)
            self._batch_serial_button.setEnabled(True)
            self._log(f"[流程失敗] 一鍵產生命名草稿發生例外：{exc}")
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "一鍵產生命名草稿", f"流程失敗：{exc}")

    def _run_one_click_workflow(self) -> None:
        if self._batch_thread is not None and self._batch_thread.isRunning():
            QMessageBox.information(self, "ISO PDF 命名工作台", "批次判讀正在執行中。")
            return
        self._log("[流程] 一鍵產生命名草稿：開始。")
        if not self._ensure_workflow_pdf_pages():
            return
        if not self._ensure_workflow_iso_records():
            return
        self._problem_only_check.setChecked(False)
        self._one_click_workflow_active = True
        self._batch_detect_serials(workflow=True)

    def _ensure_workflow_pdf_pages(self) -> bool:
        if self._combine_pdf is not None and self._combine_pdf.exists() and self._pdfs == [self._combine_pdf]:
            page_folder = self._combine_pdf.with_name(f"{self._combine_pdf.stem}_pages")
            existing_pages = self._pdfs_from_folder(page_folder) if page_folder.exists() else []
            if existing_pages:
                self._log(f"[流程] 使用既有單頁 PDF 資料夾：{page_folder}")
                self._page_folder = page_folder
                self._pdfs = existing_pages
                self._update_source_labels()
                self._load_rows()
                self._load_profile_for_current_folder()
            else:
                self._log("[流程] 偵測到合併 PDF，開始拆成單頁 PDF。")
                if not self._split_combine_pdf(show_message=False):
                    self._log("[流程] 拆頁失敗，已停止一鍵流程。")
                    return False
        if not self._pdfs:
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可處理的 PDF。")
            self._log("[流程] 沒有可處理的 PDF，已停止。")
            return False
        return True

    def _ensure_workflow_iso_records(self) -> bool:
        if self._records:
            return True
        if self._iso_table is not None:
            self._apply_selected_columns(show_message=False)
            if self._records:
                return True
        candidates = self._nearby_iso_list_candidates()
        for candidate in candidates[:5]:
            self._log(f"[流程] 嘗試自動載入 ISO List：{candidate}")
            if self._load_iso_list_path(candidate, show_errors=False) and self._records:
                return True
        QMessageBox.information(self, "ISO PDF 命名工作台", "一鍵流程需要先載入可用的 ISO List。")
        self._log("[流程] 找不到可用 ISO List，已停止。")
        return False

    def _apply_detected_serial_to_row(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._pdfs):
            QMessageBox.information(self, "ISO PDF 命名工作台", "請先在更名表選擇一列。")
            return
        if not self._detected_serial:
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可填入的影像判讀流水號。")
            return
        if self._detected_serial_confidence < SERIAL_AUTO_FILL_CONFIDENCE:
            QMessageBox.warning(
                self,
                "ISO PDF 命名工作台",
                f"目前判讀信心 {self._detected_serial_confidence:.2f} 低於 {SERIAL_AUTO_FILL_CONFIDENCE:.2f}，未自動填入。",
            )
            return
        if self._records and self._detected_serial not in build_record_lookup(self._records):
            QMessageBox.warning(
                self,
                "ISO PDF 命名工作台",
                f"ISO List 找不到流水號 {self._detected_serial}，未自動填入。這通常代表影像判讀抓錯位置，請手動確認。",
            )
            self._log(f"[影像判讀] ISO List 找不到流水號，未填入：{self._detected_serial}")
            return
        self._table.item(row, 3).setText(self._detected_serial)
        self._clear_review_issue(row, "填入目前頁判讀流水號")
        self._regenerate_names()
        self._log(f"[影像判讀] 第 {row + 1} 列填入流水號：{self._detected_serial}")

    def _confirm_current_review_issue(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._pdfs):
            QMessageBox.information(self, "ISO PDF 命名工作台", "請先選擇一列。")
            return
        if self._pdfs[row] not in self._review_issues:
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前列沒有待確認的判讀問題。")
            return
        self._clear_review_issue(row, "使用者確認")
        self._refresh_statuses()
        self._log(f"[影像判讀] 第 {row + 1} 列已由使用者確認。")

    def _batch_detect_serials(self, _checked: bool = False, *, workflow: bool = False) -> None:
        if self._batch_thread is not None and self._batch_thread.isRunning():
            QMessageBox.information(self, "ISO PDF 命名工作台", "批次判讀正在執行中。")
            return
        if not self._pdfs:
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可判讀的 PDF。")
            return
        self._log(
            f"[影像判讀] 開始批次判讀 {len(self._pdfs)} 個 PDF；"
            f"判讀區 {self._serial_region_text()}；信心低於 {SERIAL_AUTO_FILL_CONFIDENCE:.2f} 不自動填入。"
        )
        total = len(self._pdfs)
        self._batch_record_lookup = build_record_lookup(self._records) if self._records else {}
        self._batch_stats = {
            "total": total,
            "processed": 0,
            "filled": 0,
            "low_confidence": [],
            "not_in_iso": [],
            "review_required": [],
            "failed": [],
            "cancel_logged": False,
        }
        self._batch_completion_pending = False
        self._one_click_workflow_active = workflow
        self._batch_serial_button.setEnabled(False)
        self._one_click_button.setEnabled(False)
        self._preview_tabs.setCurrentIndex(0)
        self._set_serial_vision_result("", 0.0, f"影像判讀流水號：批次判讀中 0 / {total}")

        progress = QProgressDialog(f"批次判讀流水號：0 / {total}", "取消", 0, total, self)
        progress.setWindowTitle("批次判讀流水號")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(self._cancel_batch_detect)
        progress.show()
        self._batch_progress = progress

        thread = BatchDetectThread(self._pdfs, self._serial_region(), self._preview_temp_dir)
        thread.progress.connect(self._on_batch_detect_progress)
        thread.completed.connect(self._on_batch_detect_completed)
        thread.finished.connect(thread.deleteLater)
        self._batch_thread = thread
        thread.start()
        self._update_workflow_status()

    def _cancel_batch_detect(self) -> None:
        thread = self._batch_thread
        if thread is None or not thread.isRunning():
            return
        thread.cancel()
        if not self._batch_stats.get("cancel_logged"):
            self._batch_stats["cancel_logged"] = True
            self._log("[影像判讀] 已要求取消批次判讀，會在目前這張處理完後停止。")
        if self._batch_progress is not None:
            self._batch_progress.setLabelText("正在取消批次判讀...")

    def _on_batch_detect_progress(self, done: int, total: int, path_obj: object, result_obj: object) -> None:
        if self._batch_thread is None and not self._batch_completion_pending and not self._batch_stats:
            return
        try:
            self._handle_batch_detect_progress(done, total, path_obj, result_obj)
        except Exception as exc:
            self._log(f"[影像判讀失敗] 更新第 {done} / {total} 筆結果時發生例外：{exc}")
            self._log(traceback.format_exc())
            self._cancel_batch_detect()

    def _handle_batch_detect_progress(self, done: int, total: int, path_obj: object, result_obj: object) -> None:
        path = path_obj if isinstance(path_obj, Path) else Path(str(path_obj))
        result = result_obj if isinstance(result_obj, SerialVisionResult) else SerialVisionResult("", 0.0, "判讀結果格式錯誤")
        result = correct_result_with_iso_lookup(result, self._batch_record_lookup)
        self._batch_stats["processed"] = done
        progress = self._batch_progress
        if progress is not None:
            progress.setLabelText(f"批次判讀流水號：{done} / {total}\n{path.name}")
            progress.setValue(done)
        self._set_serial_vision_result(
            result.text,
            result.confidence,
            f"影像判讀流水號：批次判讀中 {done} / {total}  {path.name}",
        )
        try:
            row = self._pdfs.index(path)
        except ValueError:
            self._log(f"[影像判讀] 略過已不在表格中的結果：{path.name}")
            return

        self._show_batch_progress_preview(row, path, done, total, result)
        self._record_vision_result(path, result)
        issue = self._review_issue_for_result(result, self._batch_record_lookup)
        if not result.text:
            reason = issue or result.message
            self._set_review_issue(row, reason)
            self._append_batch_stat("failed", f"第 {row + 1} 列 {path.name}: {result.message}")
            self._log(f"[影像判讀] 未判讀：第 {row + 1} 列 {path.name} ({result.message})")
        elif result.confidence < SERIAL_AUTO_FILL_CONFIDENCE:
            reason = issue or f"信心太低 {result.confidence:.2f}"
            self._set_review_issue(row, reason)
            self._append_batch_stat("low_confidence", f"第 {row + 1} 列 {path.name}: {result.text} ({result.confidence:.2f})")
            self._log(f"[影像判讀] 信心太低，未填入：第 {row + 1} 列 {result.text} ({result.confidence:.2f}) {result.message}")
        elif self._batch_record_lookup and result.text not in self._batch_record_lookup:
            reason = issue or f"ISO List 無此流水號：{result.text}"
            self._set_review_issue(row, reason)
            self._append_batch_stat("not_in_iso", f"第 {row + 1} 列 {path.name}: {result.text} ({result.confidence:.2f})")
            self._log(f"[影像判讀] ISO List 無此流水號，未填入：第 {row + 1} 列 {result.text} ({result.confidence:.2f})")
        else:
            self._fill_serial_row(row, result.text, self._batch_record_lookup)
            self._batch_stats["filled"] = int(self._batch_stats.get("filled", 0)) + 1
            if issue:
                self._set_review_issue(row, issue)
                self._append_batch_stat("review_required", f"第 {row + 1} 列 {path.name}: {result.text} ({result.confidence:.2f}) {issue}")
                self._log(f"[影像判讀] 第 {row + 1} 列 {path.name} -> {result.text} ({result.confidence:.2f})，需確認：{issue}")
            else:
                self._clear_review_issue(row)
                self._log(f"[影像判讀] 第 {row + 1} 列 {path.name} -> {result.text} ({result.confidence:.2f}) {result.message}")
        self._refresh_statuses()

    def _show_batch_progress_preview(
        self,
        row: int,
        path: Path,
        done: int,
        total: int,
        result: SerialVisionResult,
    ) -> None:
        was_blocked = self._table.blockSignals(True)
        try:
            self._table.setCurrentCell(row, 1)
        finally:
            self._table.blockSignals(was_blocked)
        self._preview_tabs.setCurrentIndex(0)
        self._show_pdf_preview(path, force_reload=True, detect=False)
        detected = result.text or "未判讀"
        self._preview_info.setText(
            f"批次預覽：{done} / {total}\n"
            f"{path.name}\n"
            f"結果：{detected}  信心 {result.confidence:.2f}"
        )

    def _on_batch_detect_completed(self, canceled: bool) -> None:
        if self._batch_completion_pending:
            return
        self._batch_completion_pending = True
        QTimer.singleShot(100, lambda canceled=canceled: self._complete_batch_detect(canceled))

    def _complete_batch_detect(self, canceled: bool) -> None:
        try:
            self._handle_batch_detect_completed(canceled)
        except Exception as exc:
            self._batch_completion_pending = False
            self._batch_thread = None
            self._one_click_workflow_active = False
            self._batch_serial_button.setEnabled(True)
            self._one_click_button.setEnabled(True)
            if self._batch_progress is not None:
                self._batch_progress.close()
                self._batch_progress = None
            self._update_workflow_status()
            self._log(f"[影像判讀失敗] 批次完成收尾時發生例外：{exc}")
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "ISO PDF 命名工作台", f"批次判讀收尾失敗：{exc}")

    def _handle_batch_detect_completed(self, canceled: bool) -> None:
        if self._batch_progress is not None:
            try:
                self._batch_progress.canceled.disconnect(self._cancel_batch_detect)
            except TypeError:
                pass
            self._batch_progress.close()
            self._batch_progress = None
        self._batch_thread = None
        self._batch_serial_button.setEnabled(True)
        self._one_click_button.setEnabled(True)
        self._regenerate_names()
        self._update_workflow_status()

        message, detail, has_issues = self._batch_summary(canceled)
        self._log(f"[影像判讀] {message.replace(chr(10), ' ')}")
        self._set_serial_vision_result("", 0.0, message.splitlines()[0])
        workflow = self._one_click_workflow_active
        self._one_click_workflow_active = False
        self._batch_record_lookup = {}
        self._batch_stats = {}
        self._batch_completion_pending = False
        if self._closing:
            return
        if workflow:
            self._finish_one_click_workflow(canceled, message, detail, has_issues)
            return
        if canceled:
            QMessageBox.information(self, "ISO PDF 命名工作台", f"{message}\n\n{detail}".strip())
        elif has_issues:
            QMessageBox.warning(self, "ISO PDF 命名工作台", f"{message}\n\n{detail}".strip())
        else:
            QMessageBox.information(self, "ISO PDF 命名工作台", message)

    def _finish_one_click_workflow(self, canceled: bool, message: str, detail: str, has_issues: bool) -> None:
        if canceled:
            QMessageBox.information(self, "ISO PDF 命名工作台", f"{message}\n\n{detail}".strip())
            self._log("[流程] 一鍵產生命名草稿已取消。")
            return
        self._check_renames()
        unresolved = self._unresolved_review_rows()
        if unresolved or has_issues:
            self._problem_only_check.setChecked(True)
            self._select_next_problem_row()
            detail_text = detail or "\n".join(f"第 {row + 1} 列 {path.name}: {reason}" for row, path, reason in unresolved[:8])
            QMessageBox.warning(
                self,
                "一鍵產生命名草稿",
                f"{message}\n\n仍有需要人工確認的列，已切到問題列。\n\n{detail_text}".strip(),
            )
            self._log("[流程] 一鍵草稿完成，但仍有問題列需要確認。")
            return
        try:
            operations = self._operations()
            if not operations:
                QMessageBox.information(self, "一鍵產生命名草稿", "草稿已完成，但沒有需要更名的 PDF。")
                self._log("[流程] 草稿完成，沒有需要更名的 PDF。")
                return
            _validate_operations(operations)
        except Exception as exc:
            QMessageBox.warning(self, "一鍵產生命名草稿", str(exc))
            self._refresh_statuses()
            self._log(f"[流程] 草稿完成，但更名前檢查失敗：{exc}")
            return
        self._log("[流程] 草稿完成，準備開啟更名確認表。")
        QTimer.singleShot(200, self._open_one_click_rename_plan)

    def _open_one_click_rename_plan(self) -> None:
        if self._closing:
            return
        try:
            self._log("[流程] 開啟更名確認表。")
            self._execute()
        except Exception as exc:
            self._log(f"[流程失敗] 開啟更名確認表時發生例外：{exc}")
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "一鍵產生命名草稿", f"開啟更名確認表失敗：{exc}")

    def _fill_serial_row(self, row: int, serial: str, record_lookup: dict[str, IsoRecord]) -> None:
        record = record_lookup.get(serial)
        line_no = record.line_no if record else self._table.item(row, 4).text().strip()
        new_name = format_iso_name(self._pattern.text(), serial=serial, line=line_no)
        source = self._pdfs[row]
        self._table.blockSignals(True)
        self._table.item(row, 3).setText(serial)
        self._table.item(row, 4).setText(line_no)
        self._table.item(row, 5).setText(new_name)
        self._table.item(row, 0).setCheckState(Qt.CheckState.Checked if new_name and new_name != source.name else Qt.CheckState.Unchecked)
        self._table.blockSignals(False)

    def _append_batch_stat(self, key: str, value: str) -> None:
        bucket = self._batch_stats.get(key)
        if isinstance(bucket, list):
            bucket.append(value)

    def _batch_summary(self, canceled: bool) -> tuple[str, str, bool]:
        total = int(self._batch_stats.get("total", len(self._pdfs)))
        processed = int(self._batch_stats.get("processed", 0))
        filled = int(self._batch_stats.get("filled", 0))
        low_confidence = self._batch_stat_list("low_confidence")
        not_in_iso = self._batch_stat_list("not_in_iso")
        review_required = self._batch_stat_list("review_required")
        failed = self._batch_stat_list("failed")
        prefix = "批次判讀已取消" if canceled else "批次判讀完成"
        message = f"{prefix}：已處理 {processed} / {total} 筆，自動填入 {filled} 筆。"
        if low_confidence:
            message += f"\n{len(low_confidence)} 筆命中率太低，未自動填入。"
        if not_in_iso:
            message += f"\n{len(not_in_iso)} 筆不在 ISO List，視為疑似誤判。"
        if review_required:
            message += f"\n{len(review_required)} 筆已填入但需要人工確認。"
        if failed:
            message += f"\n{len(failed)} 筆未判讀到流水號。"
        detail = "\n".join([*low_confidence[:8], *not_in_iso[:8], *review_required[:8], *failed[:8]])
        return message, detail, bool(low_confidence or not_in_iso or review_required or failed)

    def _batch_stat_list(self, key: str) -> list[str]:
        value = self._batch_stats.get(key)
        return value if isinstance(value, list) else []

    def _detect_serial_from_pdf(self, path: Path) -> SerialVisionResult:
        return detect_serial_from_pdf(path, self._serial_region(), self._preview_cache)

    def _review_issue_for_result(self, result: SerialVisionResult, record_lookup: dict[str, IsoRecord]) -> str:
        if not result.text:
            return result.message or "未判讀到流水號"
        if result.confidence < SERIAL_AUTO_FILL_CONFIDENCE:
            return f"信心太低 {result.confidence:.2f}"
        if record_lookup and result.text not in record_lookup:
            return f"ISO List 無此流水號：{result.text}"
        if "OCR 不一致" in result.message:
            return result.message
        if "OCR 尾段校正" in result.message or "OCR 前段校正" in result.message:
            return result.message
        return ""

    def _set_review_issue(self, row: int, reason: str) -> None:
        if 0 <= row < len(self._pdfs):
            self._review_issues[self._pdfs[row]] = reason or "需要人工確認"

    def _clear_review_issue(self, row: int, note: str = "") -> None:
        if 0 <= row < len(self._pdfs):
            path = self._pdfs[row]
            if path in self._review_issues:
                del self._review_issues[path]
                if note:
                    self._log(f"[影像判讀] 第 {row + 1} 列解除待確認：{note}。")

    def _unresolved_review_rows(self) -> list[tuple[int, Path, str]]:
        rows: list[tuple[int, Path, str]] = []
        for row, path in enumerate(self._pdfs):
            reason = self._review_issues.get(path)
            if reason:
                rows.append((row, path, reason))
        return rows

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._closing = True
        if self._batch_thread is not None and self._batch_thread.isRunning():
            self._batch_thread.cancel()
            self._batch_thread.wait(3000)
        if self._batch_progress is not None:
            self._batch_progress.close()
            self._batch_progress = None
        self._save_current_profile()
        self._clear_preview()
        shutil.rmtree(self._preview_temp_dir, ignore_errors=True)
        super().closeEvent(event)

    def _refresh_iso_naming(self) -> None:
        if self._iso_list_path is None:
            candidate = self._auto_xlsx_candidate()
            if candidate is None:
                QMessageBox.information(self, "ISO PDF 命名工作台", "目前來源附近沒有找到 .xlsx ISO List。")
                self._log("[ISO] 重新整理：附近沒有找到 .xlsx ISO List。")
                return
            self._log(f"[ISO] 重新整理：自動載入 {candidate}")
            self._load_iso_list_path(candidate)
            return
        if not self._read_selected_sheet():
            return
        self._regenerate_names()
        self._check_renames()
        self._log("[ISO] 已重新整理 Sheet、欄位判讀與命名表。")

    def _load_iso_list(self) -> None:
        start = self._page_folder or (self._combine_pdf.parent if self._combine_pdf else self._context.folder) or Path.home()
        file_name, _selected = QFileDialog.getOpenFileName(
            self,
            "選擇 ISO list",
            str(start),
            "ISO List (*.xlsx *.xlsm *.csv)",
        )
        if not file_name:
            return
        self._load_iso_list_path(Path(file_name))

    def _load_iso_list_path(
        self,
        path: Path,
        *,
        preferred_sheet: str | None = None,
        preferred_serial_col: int | None = None,
        preferred_line_col: int | None = None,
        show_errors: bool = True,
    ) -> bool:
        self._iso_list_path = path
        self._iso_table = None
        self._records = []
        self._serial_column_combo.clear()
        self._line_column_combo.clear()
        try:
            sheets = list_iso_sheets(self._iso_list_path)
        except Exception as exc:
            self._log(f"[失敗] ISO list 讀取 sheet 清單失敗：{exc}")
            self._update_workflow_status()
            if show_errors:
                QMessageBox.warning(self, "ISO PDF 命名工作台", str(exc))
            return False

        self._sheet_combo.blockSignals(True)
        self._sheet_combo.clear()
        for sheet in sheets:
            self._sheet_combo.addItem(sheet)
        preferred_index = self._sheet_combo.findText(preferred_sheet) if preferred_sheet else -1
        if preferred_index < 0:
            preferred_index = self._preferred_sheet_index(sheets)
        if preferred_index is not None:
            self._sheet_combo.setCurrentIndex(preferred_index)
        self._sheet_combo.blockSignals(False)
        self._iso_label.setText(f"ISO list：{path}，尚未套用欄位")
        self._update_workflow_status()
        self._log(f"[ISO] 已選擇：{path}")
        self._log(f"[ISO] 可用 Sheet：{', '.join(sheets) if sheets else '無'}")
        if preferred_index is not None and sheets:
            self._log(f"[ISO] 優先讀取 Sheet：{sheets[preferred_index]}")
        return self._read_selected_sheet(
            preferred_serial_col=preferred_serial_col,
            preferred_line_col=preferred_line_col,
            show_errors=show_errors,
        )

    def _preferred_sheet_index(self, sheets: list[str]) -> int | None:
        if self._iso_list_path is None:
            return 0 if sheets else None
        scored = [(self._score_iso_sheet(sheet), index) for index, sheet in enumerate(sheets)]
        scored.sort(reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][1]
        preferred_keywords = ("dwg", "iso", "isometric", "list", "管線", "清單", "圖號")
        for index, sheet in enumerate(sheets):
            normalized = sheet.lower().replace(" ", "")
            if any(keyword in normalized for keyword in preferred_keywords):
                return index
        return 0 if sheets else None

    def _score_iso_sheet(self, sheet_name: str) -> int:
        if self._iso_list_path is None:
            return 0
        score = 0
        normalized_sheet = sheet_name.lower().replace(" ", "")
        if any(keyword in normalized_sheet for keyword in ("dwg", "iso", "圖號", "清單", "list")):
            score += 10
        try:
            table = read_iso_table(self._iso_list_path, sheet_name=sheet_name)
        except Exception:
            return score
        serial_col, line_col = guess_iso_columns(table.headers)
        if serial_col is not None:
            score += 30
        if line_col is not None:
            score += 30
            header = table.headers[line_col].lower()
            if any(keyword in header for keyword in ("file_basename", "dst_pdf_name", "source_pdf_name", "pdf", "檔名", "圖號")):
                score += 50
        score += min(20, len(table.rows) // 10)
        return score

    def _find_nearby_iso_list(self) -> None:
        candidates = self._nearby_iso_list_candidates()
        if not candidates:
            QMessageBox.information(self, "ISO PDF 命名工作台", "附近沒有找到可能的 ISO List。")
            self._log("[ISO] 附近沒有找到可能的 ISO List。")
            return
        selected = candidates[0]
        self._log("[ISO] 找到附近 ISO List 候選：")
        for path in candidates[:8]:
            self._log(f"  - {path}")
        self._load_iso_list_path(selected)

    def _nearby_iso_list_candidates(self) -> list[Path]:
        roots: list[Path] = []
        for path in (self._page_folder, self._combine_pdf.parent if self._combine_pdf else None, self._context.folder):
            if path and path.exists():
                root = path if path.is_dir() else path.parent
                if root not in roots:
                    roots.append(root)

        candidates: list[Path] = []
        for root in roots:
            for pattern in ("*.xlsx", "*.xlsm", "*.csv"):
                candidates.extend(path for path in root.glob(pattern) if not path.name.startswith("~$"))

        def score(path: Path) -> tuple[int, float]:
            name = path.stem.lower()
            value = 0
            for keyword, points in (
                ("iso", 40),
                ("圖號", 35),
                ("清單", 25),
                ("list", 20),
                ("dwg", 20),
                ("pdf_page_to_new_name", -80),
                ("rename_plan", -100),
            ):
                if keyword in name:
                    value += points
            return value, path.stat().st_mtime

        unique = sorted(set(candidates), key=score, reverse=True)
        return [path for path in unique if score(path)[0] > -50]

    def _read_selected_sheet(
        self,
        *,
        preferred_serial_col: int | None = None,
        preferred_line_col: int | None = None,
        show_errors: bool = True,
    ) -> bool:
        if self._iso_list_path is None:
            if show_errors:
                QMessageBox.information(self, "ISO PDF 命名工作台", "請先選擇 ISO List。")
            self._log("[提醒] 尚未選擇 ISO List。")
            return False
        sheet_name = self._sheet_combo.currentText().strip() or None
        try:
            self._iso_table = read_iso_table(self._iso_list_path, sheet_name=sheet_name)
        except Exception as exc:
            self._iso_table = None
            self._records = []
            self._serial_column_combo.clear()
            self._line_column_combo.clear()
            self._log(f"[失敗] Sheet 讀取失敗：{exc}")
            self._update_workflow_status()
            if show_errors:
                QMessageBox.warning(self, "ISO PDF 命名工作台", str(exc))
            return False

        self._populate_column_combos(self._iso_table)
        self._iso_label.setText(
            f"ISO list：{self._iso_list_path}，Sheet={self._iso_table.sheet_name}，尚未套用欄位"
        )
        self._update_workflow_status()
        self._log(
            f"[Sheet] 已讀取 {self._iso_table.sheet_name}；"
            f"標題列={self._iso_table.header_row_index + 1}，欄位={len(self._iso_table.headers)}，資料列={len(self._iso_table.rows)}"
        )
        if preferred_serial_col is not None or preferred_line_col is not None:
            serial_ok = self._set_combo_by_data(self._serial_column_combo, preferred_serial_col)
            line_ok = self._set_combo_by_data(self._line_column_combo, preferred_line_col)
            if serial_ok and line_ok:
                self._log("[Profile] 已還原 ISO List 欄位對應。")
                self._apply_selected_columns(show_message=False)
                return True
        self._auto_select_columns()
        return True

    def _populate_column_combos(self, table: IsoTable) -> None:
        for combo in (self._serial_column_combo, self._line_column_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("請選擇欄位", None)
            for index, header in enumerate(table.headers):
                combo.addItem(f"{index + 1}. {header}", index)
            combo.blockSignals(False)

    def _auto_select_columns(self) -> None:
        if self._iso_table is None:
            QMessageBox.information(self, "ISO PDF 命名工作台", "請先讀取 ISO List 的 Sheet。")
            self._log("[提醒] 尚未讀取 Sheet，無法自動判讀欄位。")
            return
        serial_col, line_col = guess_iso_columns(self._iso_table.headers)
        self._set_combo_by_data(self._serial_column_combo, serial_col)
        self._set_combo_by_data(self._line_column_combo, line_col)

        serial_text = self._iso_table.headers[serial_col] if serial_col is not None else "未找到"
        line_text = self._iso_table.headers[line_col] if line_col is not None else "未找到"
        if serial_col is None or line_col is None:
            self._log(f"[欄位] 自動判讀不完整：流水號={serial_text}，圖號/檔名={line_text}。請手動選欄位後按「套用欄位」。")
            return
        self._log(f"[欄位] 自動判讀：流水號={serial_text}，圖號/檔名={line_text}")
        self._apply_selected_columns(show_message=False)

    def _set_combo_by_data(self, combo: QComboBox, value: int | None) -> bool:
        if value is None:
            combo.setCurrentIndex(0)
            return False
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
        return index >= 0

    def _apply_selected_columns(self, *, show_message: bool = True) -> None:
        if self._iso_table is None:
            QMessageBox.information(self, "ISO PDF 命名工作台", "請先讀取 ISO List 的 Sheet。")
            self._log("[提醒] 尚未讀取 Sheet，無法套用欄位。")
            return
        serial_col = self._serial_column_combo.currentData()
        line_col = self._line_column_combo.currentData()
        if serial_col is None or line_col is None:
            message = "請指定「流水號欄」與「圖號/檔名欄」。"
            self._log(f"[提醒] {message}")
            if show_message:
                QMessageBox.information(self, "ISO PDF 命名工作台", message)
            return
        if serial_col == line_col:
            message = "流水號欄與圖號/檔名欄不能是同一欄。"
            self._log(f"[提醒] {message}")
            if show_message:
                QMessageBox.warning(self, "ISO PDF 命名工作台", message)
            return

        self._records = records_from_table(self._iso_table, serial_col=int(serial_col), line_col=int(line_col))
        serial_header = self._iso_table.headers[int(serial_col)]
        line_header = self._iso_table.headers[int(line_col)]
        self._iso_label.setText(
            f"ISO list：{self._iso_list_path}，Sheet={self._iso_table.sheet_name}，{len(self._records)} 筆"
        )
        self._update_workflow_status()
        self._log(
            f"[成功] 已套用欄位：流水號={serial_header}，圖號/檔名={line_header}；有效資料={len(self._records)} 筆"
        )
        if self._records:
            sample = self._records[0]
            self._log(f"[範例] {sample.serial} -> {sample.line_no}")
        self._save_current_profile()
        self._regenerate_names()

    def _regenerate_names(self) -> None:
        if not self._records:
            self._log("[命名] 尚未載入 ISO 對照資料；會保留表格內手動輸入的圖號/檔名。")
        lookup = build_record_lookup(self._records)
        pattern = self._pattern.text().strip() or "{serial}--{line}.pdf"
        self._table.blockSignals(True)
        for row, path in enumerate(self._pdfs):
            serial = self._table.item(row, 3).text().strip() or str(row + 1)
            record = lookup.get(serial)
            line_no = record.line_no if record else self._table.item(row, 4).text().strip()
            new_name = format_iso_name(pattern, serial=serial, line=line_no)
            self._table.item(row, 4).setText(line_no)
            self._table.item(row, 5).setText(new_name)
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked if new_name and new_name != path.name else Qt.CheckState.Unchecked)
        self._table.blockSignals(False)
        self._refresh_statuses()

    def _check_renames(self) -> None:
        for row, path in enumerate(self._pdfs):
            new_name = self._table.item(row, 5).text().strip()
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked if new_name and new_name != path.name else Qt.CheckState.Unchecked)
        self._refresh_statuses()

    def _execute(self) -> None:
        unresolved = self._unresolved_review_rows()
        if unresolved:
            first_row, _first_path, _first_reason = unresolved[0]
            self._table.setCurrentCell(first_row, 6)
            detail = "\n".join(
                f"第 {row + 1} 列 {path.name}: {reason}" for row, path, reason in unresolved[:10]
            )
            QMessageBox.warning(
                self,
                "尚有判讀問題未確認",
                "更名表仍有高亮的判讀問題列。請手動修正流水號/圖號/檔名，或選取確認無誤後按「確認此列」。\n\n"
                f"{detail}",
            )
            self._log(f"[阻擋] 尚有 {len(unresolved)} 列判讀問題未確認，已停止更名。")
            return
        try:
            operations = self._operations()
            if not operations:
                QMessageBox.information(self, "ISO PDF 命名工作台", "沒有勾選需要更名的 PDF。")
                return
            _validate_operations(operations)
        except Exception as exc:
            QMessageBox.warning(self, "ISO PDF 命名工作台", str(exc))
            self._refresh_statuses()
            return

        plan = build_rename_plan(operations, review_issues=self._review_issues)
        dialog = RenamePlanDialog(plan, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pause_preview_for_pdf_write("正在套用更名，已暫時關閉預覽以避免檔案鎖定。")
        try:
            _apply_operations(operations)
        except Exception as exc:
            QMessageBox.critical(self, "ISO PDF 命名工作台", str(exc))
            return

        renamed = {operation.source: operation.target for operation in operations}
        self._pdfs = [renamed.get(path, path) for path in self._pdfs]
        self._load_rows()
        QMessageBox.information(self, "ISO PDF 命名工作台", f"已更名 {len(operations)} 個 PDF。")

    def _operations(self) -> list[RenameOperation]:
        operations: list[RenameOperation] = []
        for row, source in enumerate(self._pdfs):
            if self._table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            new_name = self._table.item(row, 5).text().strip()
            if not new_name or new_name == source.name:
                continue
            operations.append(RenameOperation(source=source, target=source.with_name(new_name)))
        return operations

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() in {3, 4}:
            row = item.row()
            serial = self._table.item(row, 3).text().strip()
            line_no = self._table.item(row, 4).text().strip()
            if item.column() == 3:
                record = build_record_lookup(self._records).get(serial) if self._records else None
                if record is not None:
                    line_no = record.line_no
            self._table.blockSignals(True)
            if item.column() == 3:
                self._table.item(row, 4).setText(line_no)
            self._table.item(row, 5).setText(format_iso_name(self._pattern.text(), serial=serial, line=line_no))
            self._table.blockSignals(False)
        if item.column() == 5:
            row = item.row()
            source = self._pdfs[row]
            self._table.item(row, 0).setCheckState(
                Qt.CheckState.Checked if item.text().strip() and item.text().strip() != source.name else Qt.CheckState.Unchecked
            )
        if item.column() in {3, 4, 5}:
            self._revalidate_manual_row(item.row(), "使用者手動修正")
        self._refresh_statuses()

    def _revalidate_manual_row(self, row: int, note: str = "") -> None:
        issue = self._manual_review_issue_for_row(row)
        if issue:
            self._set_review_issue(row, issue)
            return
        self._clear_review_issue(row, note)

    def _manual_review_issue_for_row(self, row: int) -> str:
        if row < 0 or row >= len(self._pdfs):
            return ""
        serial = self._table.item(row, 3).text().strip()
        line_no = self._table.item(row, 4).text().strip()
        new_name = self._table.item(row, 5).text().strip()
        if not serial:
            return "缺少流水號"
        record_lookup = build_record_lookup(self._records) if self._records else {}
        record = record_lookup.get(serial)
        if record_lookup and record is None:
            return f"ISO List 無此流水號：{serial}"
        if not line_no:
            return "缺少圖號/檔名"
        if record is not None and _line_compare_key(line_no) != _line_compare_key(record.line_no):
            return f"圖號/檔名與 ISO List 不一致：{serial} 應為 {record.line_no}"
        parsed = parse_iso_filename(new_name)
        if parsed is not None:
            if parsed.serial != serial:
                return f"檔名流水號與欄位不一致：{parsed.serial} / {serial}"
            if _line_compare_key(parsed.line_no) != _line_compare_key(line_no):
                return f"檔名圖號與欄位不一致：{parsed.line_no} / {line_no}"
        return ""

    def _refresh_statuses(self) -> None:
        self._table.blockSignals(True)
        seen: set[str] = set()
        problem_count = 0
        self._row_problem_kinds = {}
        for row, source in enumerate(self._pdfs):
            new_name = self._table.item(row, 5).text().strip()
            review_issue = self._review_issues.get(source, "")
            status = ""
            if not source.exists():
                status = "來源不存在"
            elif not new_name:
                status = "缺少命名"
            elif new_name in seen:
                status = "命名重複"
            elif new_name == source.name:
                status = "未變更"
            elif source.with_name(new_name).exists():
                status = "目標已存在"
            else:
                status = "可更名"
            if review_issue:
                status = f"需確認：{review_issue}" if status in {"可更名", "未變更"} else f"{status} / 需確認"
            seen.add(new_name)
            status_item = self._table.item(row, 6)
            status_item.setText(status)
            status_item.setToolTip(review_issue)
            problem_kind = _status_issue_kind(status, review_issue)
            if problem_kind:
                self._row_problem_kinds[source] = problem_kind
                problem_count += 1
            self._apply_row_review_style(row, problem_kind)
        self._table.blockSignals(False)
        self._problem_row_count = problem_count
        self._apply_table_filter()

    def _apply_row_review_style(self, row: int, problem_kind: str) -> None:
        background_color, foreground_color = REVIEW_KIND_STYLES.get(problem_kind, (None, None))
        background = QBrush(background_color) if background_color is not None else QBrush()
        foreground = QBrush(foreground_color) if foreground_color is not None else QBrush()
        for column in range(self._table.columnCount()):
            item = self._table.item(row, column)
            if item is None:
                continue
            item.setBackground(background)
            item.setForeground(foreground)

    def _apply_table_filter(self) -> None:
        show_only_problems = self._problem_only_check.isChecked()
        search_terms = _search_terms(self._table_search.text())
        first_visible = -1
        current_row = self._table.currentRow()
        current_hidden = False
        visible_count = 0
        visible_problem_count = 0
        for row, path in enumerate(self._pdfs):
            is_problem = bool(self._row_problem_kinds.get(path))
            hidden = (show_only_problems and not is_problem) or not self._row_matches_search(row, search_terms)
            self._table.setRowHidden(row, hidden)
            if hidden and row == current_row:
                current_hidden = True
            if not hidden and first_visible < 0:
                first_visible = row
            if not hidden:
                visible_count += 1
                if is_problem:
                    visible_problem_count += 1
        if current_hidden and first_visible >= 0:
            self._table.setCurrentCell(first_visible, 1)
        self._problem_summary_label.setText(f"問題列：{self._problem_row_count} / {len(self._pdfs)}｜顯示 {visible_count}")
        self._next_problem_button.setEnabled(visible_problem_count > 0)
        self._update_workflow_status()

    def _row_matches_search(self, row: int, search_terms: list[str]) -> bool:
        if not search_terms:
            return True
        values = [self._pdfs[row].name if 0 <= row < len(self._pdfs) else ""]
        for column in (1, 3, 4, 5, 6, 7):
            item = self._table.item(row, column)
            if item is not None:
                values.append(item.text())
        haystack = " ".join(values).casefold()
        return all(term in haystack for term in search_terms)

    def _select_next_problem_row(self) -> None:
        visible_problem_rows = [
            row
            for row, path in enumerate(self._pdfs)
            if self._row_problem_kinds.get(path) and not self._table.isRowHidden(row)
        ]
        if not visible_problem_rows:
            QMessageBox.information(self, "ISO PDF 命名工作台", "目前沒有可見問題列。")
            return
        current_row = self._table.currentRow()
        for row in visible_problem_rows:
            if row > current_row:
                self._table.setCurrentCell(row, 6)
                return
        self._table.setCurrentCell(visible_problem_rows[0], 6)

    def _update_source_labels(self) -> None:
        self._combine_path.setText(str(self._combine_pdf or ""))
        self._combine_path.setToolTip(str(self._combine_pdf or ""))
        self._page_folder_path.setText(str(self._page_folder or ""))
        self._page_folder_path.setToolTip(str(self._page_folder or ""))
        self._page_label.setText(f"頁面 PDF：{len(self._pdfs)} 個")
        self._update_workflow_status()

    def _update_workflow_status(self) -> None:
        if self._combine_pdf is not None and self._pdfs == [self._combine_pdf]:
            self._set_step_chip(self._workflow_source_chip, "1 來源：合併 PDF 待拆頁", "warn")
        elif self._pdfs:
            self._set_step_chip(self._workflow_source_chip, f"1 來源：{len(self._pdfs)} 頁", "ready")
        else:
            self._set_step_chip(self._workflow_source_chip, "1 來源：未選", "empty")

        if self._records:
            self._set_step_chip(self._workflow_iso_chip, f"2 ISO：{len(self._records)} 筆", "ready")
        elif self._iso_table is not None:
            self._set_step_chip(self._workflow_iso_chip, "2 ISO：欄位待套用", "warn")
        elif self._iso_list_path is not None:
            self._set_step_chip(self._workflow_iso_chip, "2 ISO：Sheet 待讀取", "warn")
        else:
            self._set_step_chip(self._workflow_iso_chip, "2 ISO：未載入", "empty")

        if self._batch_thread is not None and self._batch_thread.isRunning():
            self._set_step_chip(self._workflow_vision_chip, "3 判讀：執行中", "running")
        elif self._vision_results:
            detected = sum(1 for result in self._vision_results.values() if result.text)
            self._set_step_chip(self._workflow_vision_chip, f"3 判讀：{detected}/{len(self._pdfs)}", "ready" if detected else "warn")
        elif self._pdfs:
            self._set_step_chip(self._workflow_vision_chip, "3 判讀：未執行", "empty")
        else:
            self._set_step_chip(self._workflow_vision_chip, "3 判讀：待資料", "empty")

        if not self._pdfs:
            self._set_step_chip(self._workflow_review_chip, "4 確認：待資料", "empty")
        elif self._problem_row_count:
            self._set_step_chip(self._workflow_review_chip, f"4 確認：{self._problem_row_count} 列", "warn")
        else:
            self._set_step_chip(self._workflow_review_chip, "4 確認：OK", "ready")

        checked_count = self._checked_rename_count()
        if self._problem_row_count:
            self._set_step_chip(self._workflow_rename_chip, "5 更名：先處理問題", "warn")
        elif checked_count:
            self._set_step_chip(self._workflow_rename_chip, f"5 更名：{checked_count} 筆", "ready")
        else:
            self._set_step_chip(self._workflow_rename_chip, "5 更名：無勾選", "empty")

    def _set_step_chip(self, label: QLabel, text: str, state: str) -> None:
        label.setText(text)
        label.setProperty("state", state)
        label.style().unpolish(label)
        label.style().polish(label)

    def _checked_rename_count(self) -> int:
        checked = 0
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                checked += 1
        return checked

    def _apply_style(self) -> None:
        self.setStyleSheet(workbench_stylesheet())


class FullPageCalibrationDialog(QDialog):
    def __init__(
        self,
        image: QImage,
        *,
        serial_region: SerialVisionRegion,
        drawing_region: SerialVisionRegion,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("全圖定位調整")
        self.setMinimumSize(900, 680)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._serial_region = serial_region
        self._drawing_region = drawing_region
        self._mode = "serial"

        self._selector = RegionSelector()
        self._selector.setMinimumHeight(520)
        self._selector.set_image(image)
        self._selector.set_region(serial_region)
        self._selector.regionChanged.connect(self._update_active_region)
        self._selector.regionCommitted.connect(self._update_active_region)

        self._serial_button = QPushButton("右上角 sort / 流水號")
        self._serial_button.setCheckable(True)
        self._serial_button.setChecked(True)
        self._serial_button.clicked.connect(lambda: self._set_mode("serial"))
        self._drawing_button = QPushButton("右下角圖號 / 標題欄")
        self._drawing_button.setCheckable(True)
        self._drawing_button.clicked.connect(lambda: self._set_mode("drawing"))

        reset_button = QPushButton("重設目前框")
        reset_button.clicked.connect(self._reset_active_region)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        apply_button = QPushButton("套用")
        apply_button.setProperty("primary", True)
        apply_button.clicked.connect(self.accept)

        mode_row = QHBoxLayout()
        mode_row.addWidget(self._serial_button)
        mode_row.addWidget(self._drawing_button)
        mode_row.addStretch(1)
        mode_row.addWidget(reset_button)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(cancel_button)
        button_row.addWidget(apply_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(QLabel("選擇要調整的框，直接在全圖上拖拉。"))
        layout.addLayout(mode_row)
        layout.addWidget(self._selector, 1)
        layout.addLayout(button_row)
        self.setStyleSheet(workbench_stylesheet())

    def serial_region(self) -> SerialVisionRegion:
        return self._serial_region

    def drawing_region(self) -> SerialVisionRegion:
        return self._drawing_region

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        self._serial_button.setChecked(mode == "serial")
        self._drawing_button.setChecked(mode == "drawing")
        self._selector.set_region(self._serial_region if mode == "serial" else self._drawing_region)

    def _update_active_region(self, region: SerialVisionRegion) -> None:
        if self._mode == "serial":
            self._serial_region = region
        else:
            self._drawing_region = region

    def _reset_active_region(self) -> None:
        if self._mode == "serial":
            self._serial_region = DEFAULT_SERIAL_REGION
            self._selector.set_region(self._serial_region)
        else:
            self._drawing_region = DEFAULT_DRAWING_REGION
            self._selector.set_region(self._drawing_region)


def _readonly_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    return item


def _step_chip(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("WorkflowStepChip")
    label.setProperty("state", "empty")
    return label


def _preview_image_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PdfPreviewImage")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setMinimumHeight(120)
    label.setWordWrap(True)
    return label


def _vision_cell_text(result: SerialVisionResult | None) -> str:
    if result is None:
        return ""
    if not result.text:
        return "未判讀"
    suffix = "" if result.confidence >= SERIAL_AUTO_FILL_CONFIDENCE else " 低"
    return f"{result.text} / {result.confidence:.2f}{suffix}"


def _status_issue_kind(status: str, review_issue: str) -> str:
    if review_issue:
        return _review_issue_kind(review_issue)
    if "命名重複" in status or "目標已存在" in status:
        return "conflict"
    if "來源不存在" in status or "缺少命名" in status:
        return "missing"
    return ""


def _review_issue_kind(reason: str) -> str:
    if not reason:
        return ""
    if "信心" in reason:
        return "low_confidence"
    if "ISO List 無此流水號" in reason or "無此流水號" in reason:
        return "not_in_iso"
    if "命名重複" in reason or "目標已存在" in reason:
        return "conflict"
    if "校正" in reason or "不一致" in reason:
        return "correction"
    if "未判讀" in reason or "找不到" in reason or "缺少" in reason:
        return "missing"
    return "review"


def _image_on_white(image: QImage) -> QImage:
    if not image.hasAlphaChannel():
        return image
    output = QImage(image.size(), QImage.Format.Format_RGB32)
    output.fill(Qt.GlobalColor.white)
    painter = QPainter(output)
    painter.drawImage(0, 0, image)
    painter.end()
    return output


def _field_label(value: str) -> QLabel:
    label = QLabel(value)
    label.setObjectName("FieldLabel")
    return label


def _looks_like_page_pdf(path: Path) -> bool:
    stem = path.stem.casefold()
    return bool(
        re.search(r"(^|[_\-\s])(p|page|頁)\s*0*\d{1,4}$", stem)
        or re.search(r"(^|[_\-\s])0*\d{1,4}$", stem)
    )


def _line_compare_key(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    path = Path(text)
    return path.stem.strip().lower() if path.suffix else text.lower()


def _search_terms(value: str) -> list[str]:
    return [term.casefold() for term in str(value).split() if term.strip()]


def _append_iso_workbench_log(message: str) -> None:
    try:
        log_dir = default_state_path().parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
        with (log_dir / "iso_pdf_workbench.log").open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass
