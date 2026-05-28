from __future__ import annotations

from datetime import datetime
from pathlib import Path
import subprocess
import sys
import time
import traceback

from PyQt6.QtCore import QFileInfo, QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.core.context_model import LauncherContext
from launcher.core.state_store import AppStateStore
from launcher.core.safe_cleanup import (
    BLOCKED_LAYER,
    PROCESS_LAYER,
    REGISTRY_LAYER,
    REVIEW_LAYER,
    SAFE_LAYER,
    CleanupApplyResult,
    CleanupPlan,
    CleanupPlanItem,
    OfficialUninstaller,
    ScanCancelToken,
    ScanCancelled,
    apply_cleanup_plan,
    build_cleanup_plan,
    confidence_band,
    evidence_summary,
    run_official_uninstaller,
    scan_stage_count,
)
from launcher.ui.installed_app_picker_dialog import InstalledApplicationPickerDialog
from launcher.ui.quarantine_browser_dialog import QuarantineBrowserDialog
from launcher.ui.registry_source_dialog import RegistrySourceDialog
from launcher.ui.safe_cleanup.activity_log_tab import ActivityLogTab
from launcher.ui.safe_cleanup.header_card import TargetHeaderCard
from launcher.ui.safe_cleanup.one_click_dialogs import OneClickResultDialog, OneClickSummaryDialog, default_one_click_ids
from launcher.ui.safe_cleanup.overview_tab import OverviewTab
from launcher.ui.safe_cleanup.quarantine_tab import QuarantineTab
from launcher.ui.theme import safe_cleanup_stylesheet, theme_by_name


class SafeCleanupDialog(QDialog):
    def __init__(self, context: LauncherContext, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._context = context
        self._plan: CleanupPlan = _placeholder_plan(context)
        self._item_by_id: dict[str, CleanupPlanItem] = {}
        self._icon_provider = QFileIconProvider()
        self._scan_generation = 0
        self._scan_active = False
        self._scan_threads: list[QThread] = []
        self._scan_workers: list[_CleanupPlanWorker] = []
        self._scan_token: ScanCancelToken | None = None
        self._apply_active = False
        self._apply_threads: list[QThread] = []
        self._apply_workers: list[_CleanupApplyWorker] = []
        self._suggestion_columns_initialized = False
        self._pending_one_click_result = False

        self.setWindowTitle("安全清除工作台")
        self.setMinimumSize(1200, 760)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._header = TargetHeaderCard()
        self._header.analyze_requested.connect(self.analyze_typed_target)
        self._header.refresh_requested.connect(self.refresh_plan)
        self._header.cancel_requested.connect(self.cancel_scan)
        self._header.one_click_requested.connect(self._on_one_click_clean)
        self._header.pick_app_requested.connect(self.pick_installed_app)
        self._header.pick_file_requested.connect(self.pick_file)
        self._header.pick_folder_requested.connect(self.pick_folder)
        self._summary = QLabel()
        self._summary.setObjectName("Muted")
        self._summary.setWordWrap(True)
        self._target_path: QLineEdit = self._header.target_path_edit
        self._refresh_button = self._header.refresh_button
        self._cancel_scan_button = self._header.cancel_button

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, scan_stage_count())
        self._scan_progress.setTextVisible(True)
        self._scan_progress.setFixedHeight(18)
        self._scan_progress.hide()

        self._identity = QLabel()
        self._identity.setObjectName("H1")
        self._identity.setWordWrap(True)
        self._conclusion = QLabel()
        self._conclusion.setObjectName("Muted")
        self._conclusion.setWordWrap(True)

        self._info_tree = QTreeWidget()
        self._info_tree.setColumnCount(2)
        self._info_tree.setHeaderLabels(["資訊", "內容"])
        self._info_tree.setMinimumWidth(320)
        self._info_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["套用 / 狀態", "清除建議", "動作", "判斷註解", "位置 / 登錄檔", "信心"])
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._tree.itemSelectionChanged.connect(self._update_detail)
        self._tree.itemChanged.connect(self._on_item_changed)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(110)

        self._include_review = QCheckBox("允許執行需確認層")
        self._include_review.setToolTip("資料夾與疑似衍生檔需要人工確認才可加入隔離。")
        self._include_review.stateChanged.connect(lambda _state: self._refresh_item_flags())
        self._include_process = QCheckBox("允許嘗試關閉執行中程序")
        self._include_process.setToolTip("只會嘗試正常 taskkill，不使用強制 /F；失敗時請手動關閉。")
        self._include_process.stateChanged.connect(lambda _state: self._refresh_item_flags())
        self._include_registry = QCheckBox("允許登錄檔 HKCU 清理")
        self._include_registry.setToolTip("只允許刪除 HKCU 值；HKLM / 系統層只列出。")
        self._include_registry.stateChanged.connect(lambda _state: self._refresh_item_flags())
        self._system_note = QLabel("系統層：需管理員深度清理")
        self._system_note.setObjectName("Muted")
        self._system_note.setToolTip("HKLM / Windows Installer 項目不由一般清理按鈕執行；需後續管理員模式、.reg 備份與還原紀錄。")

        self._apply_button = QPushButton("隔離 / 清理勾選項目")
        self._apply_button.setObjectName("Primary")
        self._apply_button.setDefault(True)
        self._apply_button.clicked.connect(self.apply_selected)
        self._locate_button = QPushButton("檢視 / 定位來源")
        self._locate_button.setObjectName("Ghost")
        self._locate_button.setToolTip("開啟檔案所在位置；登錄檔項目會用內建檢視器列出 key 內所有值，必要時再外部開啟 Regedit。")
        self._locate_button.clicked.connect(self.locate_selected_item)
        self._locate_button.setEnabled(False)
        quarantine_button = QPushButton("管理隔離區")
        quarantine_button.setObjectName("Ghost")
        quarantine_button.clicked.connect(self.open_quarantine_browser)
        close_button = QPushButton("關閉")
        close_button.setObjectName("Ghost")
        close_button.clicked.connect(self.accept)

        toggles = QHBoxLayout()
        toggles.addWidget(self._include_review)
        toggles.addWidget(self._include_process)
        toggles.addWidget(self._include_registry)
        toggles.addWidget(self._system_note)
        toggles.addStretch(1)

        self._overview_tab = OverviewTab()
        self._overview_tab.layer_selected.connect(self._focus_suggestion_layer)
        self._overview_tab.one_click_requested.connect(self._on_one_click_clean)
        self._overview_tab.run_uninstaller_requested.connect(self.run_detected_uninstaller)
        self._uninstall_panel = self._overview_tab.uninstaller_banner
        self._uninstall_label = self._overview_tab.uninstaller_label
        self._uninstall_button = self._overview_tab.uninstaller_button

        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(8)
        info_title = QLabel("目標資訊")
        info_title.setObjectName("H2")
        info_layout.addWidget(info_title)
        info_layout.addWidget(self._identity)
        info_layout.addWidget(self._conclusion)
        info_layout.addWidget(self._info_tree, 1)

        suggestion_body = QWidget()
        suggestion_body_layout = QVBoxLayout(suggestion_body)
        suggestion_body_layout.setContentsMargins(0, 0, 0, 0)
        suggestion_body_layout.setSpacing(10)
        suggestion_panel = QWidget()
        suggestion_layout = QVBoxLayout(suggestion_panel)
        suggestion_layout.setContentsMargins(0, 0, 0, 0)
        suggestion_layout.setSpacing(0)
        suggestion_title = QLabel("清除建議")
        suggestion_title.setObjectName("H1")
        suggestion_body_layout.addWidget(suggestion_title)
        suggestion_body_layout.addWidget(self._summary)
        suggestion_body_layout.addWidget(self._tree, 1)
        suggestion_body_layout.addLayout(toggles)
        suggestion_body_layout.addWidget(self._detail)

        suggestion_splitter = QSplitter(Qt.Orientation.Horizontal)
        suggestion_splitter.addWidget(info_panel)
        suggestion_splitter.addWidget(suggestion_body)
        suggestion_splitter.setStretchFactor(0, 0)
        suggestion_splitter.setStretchFactor(1, 1)
        suggestion_splitter.setSizes([340, 820])
        suggestion_layout.addWidget(suggestion_splitter)

        self._quarantine_tab = QuarantineTab()
        self._quarantine_tab.open_browser_requested.connect(self.open_quarantine_browser)
        self._activity_tab = ActivityLogTab()

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._overview_tab, "概覽")
        self._tabs.addTab(suggestion_panel, "清除建議")
        self._tabs.addTab(self._quarantine_tab, "隔離區")
        self._tabs.addTab(self._activity_tab, "活動紀錄")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(10)
        buttons.addWidget(quarantine_button)
        buttons.addStretch(1)
        buttons.addWidget(self._locate_button)
        buttons.addWidget(self._apply_button)
        buttons.addWidget(close_button)

        footer_wrap = QFrame()
        footer_wrap.setObjectName("FooterWrap")
        footer_layout = QVBoxLayout(footer_wrap)
        footer_layout.setContentsMargins(20, 12, 20, 16)
        footer_layout.addLayout(buttons)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 0)
        layout.setSpacing(14)
        layout.addWidget(self._header)
        layout.addWidget(self._scan_progress)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(footer_wrap)

        self.setStyleSheet(safe_cleanup_stylesheet(theme_by_name(AppStateStore().theme_name)))
        self._show_scan_placeholder()
        self.refresh_plan()

    def open_quarantine_browser(self) -> None:
        dialog = QuarantineBrowserDialog(parent=self)
        dialog.exec()

    def _on_one_click_clean(self) -> None:
        if self._scan_active:
            QMessageBox.information(self, "安全清除工作台", "目前仍在分析，請稍候完成後再執行。")
            return
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，請稍候完成。")
            return
        selected_ids = default_one_click_ids(self._plan)
        if not selected_ids:
            QMessageBox.information(self, "安全清除工作台", "目前沒有符合一鍵安全清除規則的項目。")
            return
        dialog = OneClickSummaryDialog(self._plan, selected_ids=selected_ids, parent=self)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_one_click_result = True
        self._start_apply(selected_ids)

    def _focus_suggestion_layer(self, layer: str) -> None:
        self._tabs.setCurrentIndex(1)
        if layer == "uninstaller":
            self.run_detected_uninstaller()
            return
        for index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(index)
            group_item = self._item_by_id.get(str(group.data(0, Qt.ItemDataRole.UserRole)))
            if group_item is not None:
                continue
            if _layer_label(layer) in group.text(0) or layer in group.text(0):
                group.setExpanded(True)
                if group.childCount():
                    self._tree.setCurrentItem(group.child(0))
                return

    def run_detected_uninstaller(self) -> None:
        if self._scan_active:
            QMessageBox.information(self, "安全清除工作台", "目前仍在分析，請稍候完成後再執行。")
            return
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，完成後再執行。")
            return
        uninstaller = _primary_uninstaller(self._plan)
        if uninstaller is None:
            QMessageBox.information(self, "安全清除工作台", "目前沒有找到可執行的官方解除安裝指令。")
            return
        command = uninstaller.preferred_command
        answer = QMessageBox.question(
            self,
            "執行官方解除安裝",
            (
                f"將啟動官方解除安裝程式：\n{uninstaller.display_name}\n\n"
                f"來源：{uninstaller.root_name}\\{uninstaller.registry_key}\n\n"
                "啟動後請依解除安裝程式畫面操作；工作台會在數秒後重新分析殘留。確定？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            process = run_official_uninstaller(uninstaller)
        except Exception as exc:
            QMessageBox.warning(self, "安全清除工作台", f"啟動失敗：{exc}\n\n指令：{command}")
            return
        pid_text = f"PID {process.pid}" if getattr(process, "pid", None) else "已啟動"
        self._detail.setPlainText(
            "\n".join(
                [
                    f"已啟動官方解除安裝：{uninstaller.display_name}",
                    f"狀態：{pid_text}",
                    f"指令：{command}",
                    "工作台會稍後重新分析；如果解除安裝程式仍在執行，請完成後再按一次重新分析。",
                ]
            )
        )
        QTimer.singleShot(3500, self.refresh_plan)

    def pick_file(self) -> None:
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，完成後再切換目標。")
            return
        start = str(_initial_folder(self._context))
        file_path, _selected = QFileDialog.getOpenFileName(self, "選擇要分析的檔案", start, "所有檔案 (*.*)")
        if not file_path:
            return
        self._context = LauncherContext.from_paths([file_path], source="picker.safe_cleanup")
        self._target_path.setText(file_path)
        self.refresh_plan()

    def pick_folder(self) -> None:
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，完成後再切換目標。")
            return
        start = str(_initial_folder(self._context))
        folder = QFileDialog.getExistingDirectory(self, "選擇要分析的資料夾", start)
        if not folder:
            return
        self._context = LauncherContext(folder=Path(folder), source="picker.safe_cleanup")
        self._target_path.setText(folder)
        self.refresh_plan()

    def pick_installed_app(self) -> None:
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，完成後再切換目標。")
            return
        dialog = InstalledApplicationPickerDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        app = dialog.selected_application()
        if app is None:
            return
        target = app.analysis_target
        self._context = LauncherContext.from_paths([Path(target)], source="installed_app.safe_cleanup")
        self._target_path.setText(target)
        self.refresh_plan()

    def analyze_typed_target(self) -> None:
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，完成後再切換目標。")
            return
        if self._sync_context_from_target_input(show_empty_warning=True):
            self.refresh_plan()

    def refresh_plan(self) -> None:
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，完成後再重新分析。")
            return
        self._sync_context_from_target_input(show_empty_warning=False)
        self._start_plan_scan()

    def _sync_context_from_target_input(self, *, show_empty_warning: bool) -> bool:
        text = self._target_path.text().strip()
        if not text:
            if show_empty_warning:
                QMessageBox.information(self, "安全清除工作台", "請輸入舊路徑、資料夾路徑或產品名稱。")
            return False
        current_text = _target_path_text(tuple(_context_targets(self._context)))
        if text != current_text:
            self._context = LauncherContext.from_paths([Path(text)], source="typed.safe_cleanup")
        return True

    def cancel_scan(self) -> None:
        if not self._scan_active:
            return
        self._scan_generation += 1
        if self._scan_token is not None:
            self._scan_token.cancel()
        self._scan_active = False
        self._set_scan_controls(False)
        self._summary.setText("分析已取消；可重新分析或重新選擇目標。")
        self._detail.setPlainText("已送出取消訊號；目前掃描會在下一個安全檢查點停止。")

    def apply_selected(self) -> None:
        if self._scan_active:
            QMessageBox.information(self, "安全清除工作台", "目前仍在分析，請稍候完成後再執行。")
            return
        if self._apply_active:
            QMessageBox.information(self, "安全清除工作台", "目前正在套用清理，請稍候完成。")
            return
        selected_ids = self._selected_item_ids()
        if not selected_ids:
            QMessageBox.information(self, "安全清除工作台", "目前沒有勾選可執行項目。")
            return
        selected = [self._item_by_id[item_id] for item_id in selected_ids if item_id in self._item_by_id]
        process_count = sum(1 for item in selected if item.layer == PROCESS_LAYER)
        registry_count = sum(1 for item in selected if item.layer == REGISTRY_LAYER)
        review_count = sum(1 for item in selected if item.layer == REVIEW_LAYER)
        blocked_count = sum(1 for item in selected if item.layer == BLOCKED_LAYER)
        if blocked_count:
            QMessageBox.warning(self, "安全清除工作台", "系統層項目需管理員深度清理，不由一般清理按鈕執行。")
            return
        if review_count and not self._include_review.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "需確認層尚未允許執行。")
            return
        if process_count and not self._include_process.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "執行中程序關閉尚未允許。")
            return
        if registry_count and not self._include_registry.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "登錄檔 HKCU 清理尚未允許執行。")
            return
        answer = QMessageBox.question(
            self,
            "確認安全清除",
            f"將處理 {len(selected)} 個項目。\n檔案/資料夾會移到隔離區；HKCU 登錄值會被刪除並寫入 manifest。\n確定執行？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start_apply(selected_ids)

    def locate_selected_item(self) -> None:
        item = self._current_plan_item()
        if item is None:
            QMessageBox.information(self, "安全清除工作台", "請先選擇要定位的項目。")
            return
        try:
            _locate_plan_item(item, self)
        except Exception as exc:
            QMessageBox.warning(self, "安全清除工作台", f"無法定位此項目：\n{exc}")

    def _start_apply(self, selected_ids: set[str]) -> None:
        self._set_apply_controls(True)
        worker = _CleanupApplyWorker(
            self._plan,
            selected_ids,
            include_registry=self._include_registry.isChecked(),
            include_process_close=self._include_process.isChecked(),
        )
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(self._on_apply_progress)
        worker.finished.connect(self._on_apply_finished)
        worker.failed.connect(self._on_apply_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._remove_apply_thread(thread, worker))
        self._apply_threads.append(thread)
        self._apply_workers.append(worker)
        thread.start()

    def _on_apply_progress(self, current: int, total: int, label: str) -> None:
        total = max(total, 1)
        self._scan_progress.setRange(0, total)
        self._scan_progress.setValue(max(0, min(current, total)))
        self._scan_progress.setFormat(f"{current}/{total}")
        self._summary.setText(f"套用中：{current} / {total}｜{label}")
        self._detail.setPlainText(f"正在套用清理：{label}\n請不要關閉相關檔案或手動移動目標。")

    def _on_apply_finished(self, result: object) -> None:
        if not isinstance(result, CleanupApplyResult):
            self._set_apply_controls(False)
            self._pending_one_click_result = False
            self._detail.setPlainText("套用完成，但回傳結果格式不正確。")
            return
        self._set_apply_controls(False)
        lines = [
            f"隔離資料夾：{result.quarantine_dir}",
            f"Manifest：{result.manifest_path}",
            f"已隔離檔案/資料夾：{result.moved_count}",
            f"已嘗試關閉程序：{result.closed_process_count}",
            f"已刪 HKCU 登錄值：{result.registry_deleted_count}",
            f"登錄檔備份：{'已建立 Restore-Registry.ps1' if result.registry_deleted_count else '無'}",
            f"已清工具列近期紀錄：{'是' if result.state_cleaned else '否'}",
        ]
        if result.errors:
            lines.append("")
            lines.extend(f"錯誤：{error}" for error in result.errors)
        self._detail.setPlainText("\n".join(lines))
        self._activity_tab.set_text("\n".join(lines))
        if self._pending_one_click_result:
            self._pending_one_click_result = False
            dialog = OneClickResultDialog(result, parent=self)
            dialog.setStyleSheet(self.styleSheet())
            dialog.exec()
            if dialog.open_quarantine_requested:
                self._tabs.setCurrentIndex(2)
                self.open_quarantine_browser()
        else:
            QMessageBox.information(self, "安全清除工作台", "\n".join(lines[:5]))
        self.refresh_plan()

    def _on_apply_failed(self, message: str) -> None:
        self._set_apply_controls(False)
        self._pending_one_click_result = False
        self._detail.setPlainText(message)
        self._activity_tab.set_text(message)
        QMessageBox.warning(self, "安全清除工作台", f"套用清理失敗：\n{message.splitlines()[-1] if message.splitlines() else message}")

    def _remove_apply_thread(self, thread: QThread, worker: "_CleanupApplyWorker") -> None:
        if thread in self._apply_threads:
            self._apply_threads.remove(thread)
        if worker in self._apply_workers:
            self._apply_workers.remove(worker)

    def _start_plan_scan(self) -> None:
        self._scan_generation += 1
        generation = self._scan_generation
        if self._scan_token is not None:
            self._scan_token.cancel()
        token = ScanCancelToken()
        self._scan_token = token
        self._scan_active = True
        self._plan = _placeholder_plan(self._context)
        self._show_scan_placeholder()
        self._set_scan_controls(True)

        thread = QThread()
        worker = _CleanupPlanWorker(self._context, generation, token)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.stage_changed.connect(self._on_scan_stage_changed)
        worker.finished.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        worker.cancelled.connect(self._on_scan_cancelled)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.cancelled.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda thread=thread, worker=worker: self._remove_scan_thread(thread, worker))
        self._scan_threads.append(thread)
        self._scan_workers.append(worker)
        thread.start()

    def _on_scan_stage_changed(self, generation: int, name: str, index: int, total: int) -> None:
        if generation != self._scan_generation:
            return
        self._summary.setText(f"分析中：{name} ({index} / {total})")
        self._scan_progress.setRange(0, total)
        self._scan_progress.setValue(max(0, min(index, total)))
        self._scan_progress.setFormat(f"{name} ({index}/{total})")

    def _on_scan_finished(self, generation: int, plan: CleanupPlan) -> None:
        if generation != self._scan_generation:
            return
        self._scan_active = False
        self._scan_token = None
        self._plan = plan
        self._set_scan_controls(False)
        self._populate()
        self._detail.setPlainText(f"分析完成：{datetime.fromtimestamp(plan.created_at).strftime('%Y-%m-%d %H:%M:%S')}")

    def _on_scan_cancelled(self, generation: int) -> None:
        if generation != self._scan_generation:
            return
        self._scan_active = False
        self._scan_token = None
        self._set_scan_controls(False)
        self._summary.setText("分析已取消。")
        self._detail.setPlainText("掃描已停止，沒有套用舊結果。")

    def _on_scan_failed(self, generation: int, message: str) -> None:
        if generation != self._scan_generation:
            return
        self._scan_active = False
        self._scan_token = None
        self._plan = _failed_plan(self._context, message)
        self._set_scan_controls(False)
        self._populate()
        self._detail.setPlainText(message)

    def _remove_scan_thread(self, thread: QThread, worker: "_CleanupPlanWorker") -> None:
        if thread in self._scan_threads:
            self._scan_threads.remove(thread)
        if worker in self._scan_workers:
            self._scan_workers.remove(worker)

    def _set_scan_controls(self, active: bool) -> None:
        self._scan_progress.setVisible(active)
        if active:
            self._scan_progress.setRange(0, scan_stage_count())
            self._scan_progress.setValue(0)
            self._scan_progress.setFormat("分析中")
        self._cancel_scan_button.setEnabled(active)
        self._refresh_button.setEnabled(not active and not self._apply_active)
        self._apply_button.setEnabled(not active and not self._apply_active)
        self._locate_button.setEnabled(not active and not self._apply_active and _can_locate_item(self._current_plan_item()))
        self._header.set_scanning(active)
        self._overview_tab.set_scanning(active)
        if not active:
            self._update_one_click_state()

    def _set_apply_controls(self, active: bool) -> None:
        self._apply_active = active
        self._scan_progress.setVisible(active)
        if active:
            self._scan_progress.setRange(0, 1)
            self._scan_progress.setValue(0)
            self._scan_progress.setFormat("套用中")
            self._apply_button.setText("套用中...")
            self._summary.setText("套用中：準備處理勾選項目")
        else:
            self._apply_button.setText("隔離 / 清理勾選項目")
        self._cancel_scan_button.setEnabled(False)
        self._refresh_button.setEnabled(not active and not self._scan_active)
        self._apply_button.setEnabled(not active and not self._scan_active)
        self._locate_button.setEnabled(not active and _can_locate_item(self._current_plan_item()))
        self._uninstall_button.setEnabled(not active and not self._scan_active)
        self._header.set_applying(active)
        if not active:
            self._update_one_click_state()

    def _update_one_click_state(self) -> None:
        enabled = bool(default_one_click_ids(self._plan)) and not self._scan_active and not self._apply_active
        self._header.set_one_click_enabled(enabled)
        self._overview_tab.one_click_button.setEnabled(enabled)

    def _show_scan_placeholder(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        self._item_by_id = {}
        self._target_path.setText(_target_path_text(self._plan.targets))
        self._header.set_plan(self._plan)
        self._header.set_one_click_enabled(False)
        self._identity.setText("正在分析目標")
        self._conclusion.setText("正在掃描目標、關聯檔、捷徑、執行中程序與登錄檔候選。")
        self._summary.setText("分析中...")
        self._uninstall_panel.hide()
        self._overview_tab.set_scanning(True)
        item = QTreeWidgetItem(["分析中", "請稍候", "無動作", "背景分析進行中，完成後會自動更新清除建議。", "", ""])
        item.setFirstColumnSpanned(True)
        self._tree.addTopLevelItem(item)
        self._configure_suggestion_columns()
        self._tree.blockSignals(False)
        self._populate_info_tree()
        self._detail.setPlainText("分析中；大型資料夾或登錄檔候選較多時，視窗仍可移動與關閉。")
        self._activity_tab.set_text("分析中；大型資料夾或登錄檔候選較多時，視窗仍可移動與關閉。")

    def _populate(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        self._item_by_id = {item.id: item for item in self._plan.items}
        self._target_path.setText(_target_path_text(self._plan.targets))
        self._header.set_plan(self._plan)
        self._identity.setText(_identity_text(self._plan))
        self._conclusion.setText(_analysis_conclusion(self._plan))
        self._summary.setText(_summary_text(self._plan))
        self._overview_tab.set_plan(self._plan)
        self._update_uninstaller_panel()
        self._populate_info_tree()
        for layer in (SAFE_LAYER, PROCESS_LAYER, REVIEW_LAYER, REGISTRY_LAYER, BLOCKED_LAYER):
            layer_items = [item for item in self._plan.items if item.layer == layer]
            if not layer_items:
                continue
            group = QTreeWidgetItem([_layer_title(layer, len(layer_items)), "", "", "", "", ""])
            group.setIcon(0, self._layer_icon(layer))
            group.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(group)
            for item in layer_items:
                child = QTreeWidgetItem(["", item.label, item.action, item.note, _item_location(item), _confidence_text(item)])
                child.setData(0, Qt.ItemDataRole.UserRole, item.id)
                child.setIcon(1, self._item_icon(item))
                child.setCheckState(0, Qt.CheckState.Checked if item.checked_default and item.executable else Qt.CheckState.Unchecked)
                _apply_row_style(child, item)
                group.addChild(child)
            group.setExpanded(layer != BLOCKED_LAYER)
        self._configure_suggestion_columns()
        self._tree.blockSignals(False)
        self._refresh_item_flags()
        self._update_one_click_state()
        self._activity_tab.set_text(
            f"分析完成：{datetime.fromtimestamp(self._plan.created_at).strftime('%Y-%m-%d %H:%M:%S')}\n{_summary_text(self._plan)}"
        )
        if self._tree.topLevelItemCount() > 0 and self._tree.topLevelItem(0).childCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0).child(0))

    def _configure_suggestion_columns(self) -> None:
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(54)
        for column in range(self._tree.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        if self._suggestion_columns_initialized:
            return
        default_widths = (88, 360, 110, 680, 860, 90)
        for column, width in enumerate(default_widths):
            self._tree.setColumnWidth(column, width)
        self._suggestion_columns_initialized = True

    def _populate_info_tree(self) -> None:
        self._info_tree.clear()
        targets = self._plan.targets
        target_group = QTreeWidgetItem(["目標身分", ""])
        target_group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
        self._info_tree.addTopLevelItem(target_group)
        if targets:
            for target in targets:
                target_group.addChild(_info_item("名稱", target.name or str(target), self._path_icon(target)))
                target_group.addChild(_info_item("完整路徑", str(target)))
                target_group.addChild(_info_item("類型", _path_type_text(target)))
                target_group.addChild(_info_item("存在", "是" if target.exists() else "否"))
                target_group.addChild(_info_item("大小", _target_size_text(self._plan, target)))
                target_group.addChild(_info_item("修改時間", _mtime_text(target)))
        else:
            target_group.addChild(_info_item("狀態", "尚未選擇目標"))

        safety_group = QTreeWidgetItem(["安全判斷", ""])
        safety_group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))
        self._info_tree.addTopLevelItem(safety_group)
        safety_group.addChild(_info_item("預設策略", "檔案先移到隔離區；不直接永久刪除"))
        safety_group.addChild(_info_item("系統層待確認", f"{self._plan.count_by_layer(BLOCKED_LAYER)} 項需管理員模式，不在一般模式執行"))
        safety_group.addChild(_info_item("需人工確認", f"{self._plan.count_by_layer(REVIEW_LAYER)} 項"))
        high_count = sum(1 for item in self._plan.items if confidence_band(item.confidence) == "high")
        medium_count = sum(1 for item in self._plan.items if confidence_band(item.confidence) == "medium")
        weak_count = sum(1 for item in self._plan.items if confidence_band(item.confidence) == "weak")
        safety_group.addChild(_info_item("證據分層", f"高信心 {high_count}｜中信心 {medium_count}｜弱關聯 {weak_count}"))
        safety_group.addChild(_info_item("自動策略", "低信心項目不會被隱藏；只是不預設勾選，也不進一鍵安全清除。"))

        relation_group = QTreeWidgetItem(["關聯資訊", ""])
        relation_group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon))
        self._info_tree.addTopLevelItem(relation_group)
        uninstall_branch = QTreeWidgetItem(["官方解除安裝", f"{len(self._plan.official_uninstallers)} 項"])
        relation_group.addChild(uninstall_branch)
        if self._plan.official_uninstallers:
            for uninstaller in self._plan.official_uninstallers[:5]:
                child = _info_item(uninstaller.display_name, uninstaller.match_reason or uninstaller.registry_key)
                child.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
                uninstall_branch.addChild(child)
        else:
            uninstall_branch.addChild(_info_item("結果", "未找到"))
        for title, kinds in (
            ("疑似安裝資料夾", {"install_folder"}),
            ("安裝檔暫存", {"leftover_installer"}),
            ("應用程式足跡", {"app_footprint_file", "app_footprint_folder"}),
            ("執行中 / 可能佔用", {"running_process"}),
            ("捷徑", {"shortcut"}),
            ("同名 / 衍生檔", {"associated_file", "associated_folder"}),
            ("工具列近期紀錄", {"state_record"}),
            ("Windows Installer 殘留", {"installer_registry_value"}),
            ("登錄檔候選", {"registry_value"}),
        ):
            matches = [item for item in self._plan.items if item.kind in kinds]
            branch = QTreeWidgetItem([title, f"{len(matches)} 項"])
            relation_group.addChild(branch)
            if matches:
                for item in matches[:20]:
                    child = _info_item(item.label, item.note)
                    child.setIcon(0, self._item_icon(item))
                    branch.addChild(child)
            else:
                branch.addChild(_info_item("結果", "未找到"))
        self._info_tree.expandAll()
        self._info_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._info_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _refresh_item_flags(self) -> None:
        self._tree.blockSignals(True)
        for index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                item = self._item_by_id.get(str(child.data(0, Qt.ItemDataRole.UserRole)))
                if item is None:
                    continue
                enabled = item.executable
                if item.layer == PROCESS_LAYER:
                    enabled = enabled and self._include_process.isChecked()
                if item.layer == REVIEW_LAYER:
                    enabled = enabled and self._include_review.isChecked()
                if item.layer == REGISTRY_LAYER:
                    enabled = enabled and self._include_registry.isChecked()
                flags = child.flags() | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                if enabled:
                    child.setText(0, "")
                    child.setCheckState(0, Qt.CheckState.Checked if item.checked_default and item.executable else Qt.CheckState.Unchecked)
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsUserCheckable
                    child.setData(0, Qt.ItemDataRole.CheckStateRole, None)
                    child.setText(0, _non_apply_status(item))
                child.setFlags(flags)
        self._tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        plan_item = self._item_by_id.get(str(item.data(0, Qt.ItemDataRole.UserRole)))
        if plan_item is None or plan_item.executable:
            return
        self._tree.blockSignals(True)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        self._tree.blockSignals(False)

    def _selected_item_ids(self) -> set[str]:
        selected: set[str] = set()
        for index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                if child.checkState(0) == Qt.CheckState.Checked:
                    selected.add(str(child.data(0, Qt.ItemDataRole.UserRole)))
        return selected

    def _update_detail(self) -> None:
        item = self._current_plan_item()
        if item is None:
            self._locate_button.setEnabled(False)
            return
        self._locate_button.setEnabled(not self._apply_active and _can_locate_item(item))
        lines = [
            f"項目：{item.label}",
            f"層級：{_layer_label(item.layer)}",
            f"類型：{item.kind}",
            f"動作：{item.action}",
            f"信心：{_confidence_text(item)}",
            f"證據摘要：{evidence_summary(item)}",
            f"註解：{item.note}",
            f"可執行：{'是' if item.executable else '否'}",
        ]
        if item.evidence:
            lines.append("")
            lines.append("證據帳本：")
            for evidence in item.evidence:
                sign = "+" if evidence.weight > 0 else "-" if evidence.weight < 0 else " "
                lines.append(f"{sign} {evidence.label}：{evidence.detail}")
        if item.path:
            lines.append(f"路徑：{item.path}")
            lines.append(f"大小：{_format_size(item.size_bytes)}")
        if item.process_id:
            lines.append(f"PID：{item.process_id}")
            lines.append(f"程序：{item.process_name}")
            lines.append(f"程序路徑：{item.process_path or '未知'}")
            lines.append(f"可嘗試關閉：{'是' if item.can_close else '否'}")
        if item.registry_key:
            lines.append(f"登錄檔：{item.root_name}\\{item.registry_key}")
            lines.append(f"值：{item.registry_value_name or '(Default)'}")
            lines.append(f"內容：{item.registry_value_data}")
            if item.layer == BLOCKED_LAYER:
                lines.append("")
                lines.append("重裝影響：可能。HKLM / Windows Installer 殘留可能讓安裝程式誤判已安裝、修復/移除入口異常，或沿用舊路徑。")
                lines.append("為什麼不能打勾：主清理按鈕只處理目前能完整備份與還原的項目；此項屬系統層，需管理員深度清理流程。")
                lines.append("處理方式：先用來源檢視確認內容；深度清理需管理員權限，先匯出 .reg 備份，再刪除已確認屬於目標的值或 key。")
        self._detail.setPlainText("\n".join(lines))

    def _current_plan_item(self) -> CleanupPlanItem | None:
        current = self._tree.currentItem()
        if current is None:
            return None
        return self._item_by_id.get(str(current.data(0, Qt.ItemDataRole.UserRole)))

    def _layer_icon(self, layer: str) -> QIcon:
        pixmap = {
            SAFE_LAYER: QStyle.StandardPixmap.SP_DialogApplyButton,
            PROCESS_LAYER: QStyle.StandardPixmap.SP_ComputerIcon,
            REVIEW_LAYER: QStyle.StandardPixmap.SP_MessageBoxWarning,
            REGISTRY_LAYER: QStyle.StandardPixmap.SP_FileDialogDetailedView,
            BLOCKED_LAYER: QStyle.StandardPixmap.SP_MessageBoxWarning,
        }.get(layer, QStyle.StandardPixmap.SP_FileIcon)
        return self.style().standardIcon(pixmap)

    def _item_icon(self, item: CleanupPlanItem) -> QIcon:
        if item.layer == PROCESS_LAYER:
            return self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if item.layer == REGISTRY_LAYER or item.kind in {"registry_value", "installer_registry_value"}:
            return self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        if item.kind.endswith("folder"):
            return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        if item.kind == "shortcut":
            return self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon)
        if item.kind == "state_record":
            return self.style().standardIcon(QStyle.StandardPixmap.SP_DriveFDIcon)
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def _path_icon(self, path: Path) -> QIcon:
        icon = self._icon_provider.icon(QFileInfo(str(path)))
        if not icon.isNull():
            return icon
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon if path.is_dir() else QStyle.StandardPixmap.SP_FileIcon)

    def _update_uninstaller_panel(self) -> None:
        uninstaller = _primary_uninstaller(self._plan)
        if uninstaller is None:
            self._uninstall_panel.hide()
            return
        count = len(self._plan.official_uninstallers)
        confidence = int(uninstaller.confidence * 100)
        more_text = f"；另有 {count - 1} 個候選" if count > 1 else ""
        self._uninstall_label.setText(
            f"找到官方解除安裝：{uninstaller.display_name}｜信心 {confidence}%｜{uninstaller.match_reason or '登錄檔候選'}{more_text}"
        )
        self._uninstall_panel.show()


class _CleanupPlanWorker(QObject):
    stage_changed = pyqtSignal(int, str, int, int)
    finished = pyqtSignal(int, object)
    cancelled = pyqtSignal(int)
    failed = pyqtSignal(int, str)

    def __init__(self, context: LauncherContext, generation: int, cancel_token: ScanCancelToken) -> None:
        super().__init__()
        self._context = context
        self._generation = generation
        self._cancel_token = cancel_token

    def run(self) -> None:
        try:
            self.finished.emit(self._generation, build_cleanup_plan(self._context, cancel_token=self._cancel_token, progress=self._emit_stage))
        except ScanCancelled:
            self.cancelled.emit(self._generation)
        except Exception:
            self.failed.emit(self._generation, traceback.format_exc())

    def _emit_stage(self, name: str, index: int, total: int) -> None:
        self.stage_changed.emit(self._generation, name, index, total)


class _CleanupApplyWorker(QObject):
    progress_changed = pyqtSignal(int, int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        plan: CleanupPlan,
        selected_ids: set[str],
        *,
        include_registry: bool,
        include_process_close: bool,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._selected_ids = set(selected_ids)
        self._include_registry = include_registry
        self._include_process_close = include_process_close

    def run(self) -> None:
        try:
            result = apply_cleanup_plan(
                self._plan,
                self._selected_ids,
                include_registry=self._include_registry,
                include_process_close=self._include_process_close,
                progress=self._emit_progress,
            )
            self.finished.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc())

    def _emit_progress(self, current: int, total: int, label: str) -> None:
        self.progress_changed.emit(current, total, label)


def _placeholder_plan(context: LauncherContext) -> CleanupPlan:
    return CleanupPlan(targets=tuple(_context_targets(context)), items=(), created_at=time.time())


def _failed_plan(context: LauncherContext, message: str) -> CleanupPlan:
    return CleanupPlan(
        targets=tuple(_context_targets(context)),
        items=(
            CleanupPlanItem(
                id="scan:error",
                layer=BLOCKED_LAYER,
                kind="empty",
                label="分析失敗",
                action="無動作",
                note=message.splitlines()[-1] if message.splitlines() else message,
                checked_default=False,
            ),
        ),
        created_at=time.time(),
    )


def _context_targets(context: LauncherContext) -> list[Path]:
    if context.files:
        return [path for path in context.files if str(path).strip()]
    if context.folder is not None:
        return [context.folder]
    return []


def _primary_uninstaller(plan: CleanupPlan) -> OfficialUninstaller | None:
    for uninstaller in plan.official_uninstallers:
        if not uninstaller.is_fork_relative and uninstaller.confidence >= 0.6:
            return uninstaller
    return None


def _target_path_text(targets: tuple[Path, ...]) -> str:
    if not targets:
        return ""
    if len(targets) == 1:
        return str(targets[0])
    return f"{len(targets)} 個項目，第一個為 {targets[0]}"


def _identity_text(plan: CleanupPlan) -> str:
    if not plan.targets:
        return "尚未選擇分析目標"
    target = plan.targets[0]
    target_item = next((item for item in plan.items if item.id.startswith("target:")), None)
    layer = _layer_label(target_item.layer) if target_item else "未知"
    retired = "｜殘渣掃描" if len(plan.targets) == 1 and not target.exists() else ""
    if len(plan.targets) == 1:
        return f"{target.name or target}｜{_path_type_text(target)}｜{layer}{retired}"
    return f"{len(plan.targets)} 個目標｜第一個：{target.name or target}｜{layer}"


def _analysis_conclusion(plan: CleanupPlan) -> str:
    if not plan.targets:
        return "請先選擇一個檔案或資料夾。"
    target = plan.targets[0]
    install_count = _count_kinds(plan, {"install_folder"})
    shortcut_count = _count_kinds(plan, {"shortcut"})
    process_count = _count_kinds(plan, {"running_process"})
    registry_count = _count_kinds(plan, {"registry_value", "installer_registry_value"})
    footprint_count = _count_kinds(plan, {"app_footprint_file", "app_footprint_folder"})
    installer_cache_count = _count_kinds(plan, {"leftover_installer"})
    associated_count = _count_kinds(plan, {"associated_file", "associated_folder"})
    uninstall_count = len(plan.official_uninstallers)
    if not target.exists() and (footprint_count or installer_cache_count or registry_count or shortcut_count or uninstall_count):
        return (
            "判斷：目標本體不存在，已進入退役後殘渣掃描。"
            "這通常發生在主程式被其他解除安裝器硬刪後；"
            f"目前找到官方解除安裝 {uninstall_count}、安裝檔暫存 {installer_cache_count}、應用程式足跡 {footprint_count}、"
            f"捷徑 {shortcut_count}、登錄檔/Installer 殘留 {registry_count}。"
        )
    if target.suffix.casefold() == ".exe" and (uninstall_count or install_count or installer_cache_count or footprint_count or registry_count or shortcut_count):
        return (
            "判斷：這看起來像一個應用程式執行檔。建議先跑官方解除安裝，再清殘留；"
            f"目前找到官方解除安裝 {uninstall_count}、安裝資料夾 {install_count}、安裝檔暫存 {installer_cache_count}、應用程式足跡 {footprint_count}、"
            f"執行中/可能佔用 {process_count}、捷徑 {shortcut_count}、登錄檔候選 {registry_count}。"
        )
    if installer_cache_count:
        return f"判斷：找到 {installer_cache_count} 個疑似安裝檔暫存；可先隔離釋放空間，之後仍可從隔離區還原。"
    if footprint_count:
        return f"判斷：找到 {footprint_count} 個疑似應用程式足跡；大型軟體建議逐項確認來源後再隔離。"
    if process_count:
        return f"判斷：目前找到 {process_count} 個執行中或可能佔用目標的程序；清除前建議先關閉。"
    if associated_count:
        return f"判斷：找到 {associated_count} 個同名或衍生項目，適合先隔離檢查再清除。"
    return "判斷：目前只找到目標本體；清除前仍會先移到隔離區。"


def _summary_text(plan: CleanupPlan) -> str:
    return (
        f"安全 {plan.count_by_layer(SAFE_LAYER)}｜"
        f"執行中 {plan.count_by_layer(PROCESS_LAYER)}｜"
        f"需確認 {plan.count_by_layer(REVIEW_LAYER)}｜"
        f"安裝檔暫存 {_count_kinds(plan, {'leftover_installer'})}｜"
        f"足跡 {_count_kinds(plan, {'app_footprint_file', 'app_footprint_folder'})}｜"
        f"登錄檔 {_count_kinds(plan, {'registry_value', 'installer_registry_value'})}｜"
        f"官方解除安裝 {len(plan.official_uninstallers)}｜"
        f"系統待確認 {plan.count_by_layer(BLOCKED_LAYER)}｜"
        f"估計大小 {_format_size(plan.total_size_bytes)}"
    )


def _count_kinds(plan: CleanupPlan, kinds: set[str]) -> int:
    return sum(1 for item in plan.items if item.kind in kinds)


def _layer_title(layer: str, count: int) -> str:
    return f"{_layer_label(layer)} ({count})"


def _layer_label(layer: str) -> str:
    labels = {
        SAFE_LAYER: "安全可隔離",
        PROCESS_LAYER: "執行中 / 可能佔用",
        REVIEW_LAYER: "需要人工確認",
        REGISTRY_LAYER: "登錄檔 HKCU 高風險",
        BLOCKED_LAYER: "系統層待管理員確認",
    }
    return labels.get(layer, layer)


def _item_location(item: CleanupPlanItem) -> str:
    if item.path:
        return item.path
    if item.process_id:
        return item.process_path or f"PID {item.process_id}"
    if item.registry_key:
        return f"{item.root_name}\\{item.registry_key}\\{item.registry_value_name or '(Default)'}"
    return ""


def _confidence_text(item: CleanupPlanItem) -> str:
    confidence = max(0.0, min(1.0, item.confidence))
    band = confidence_band(confidence)
    if band == "high":
        label = "高"
    elif band == "medium":
        label = "中"
    else:
        label = "弱"
    return f"{label} {int(confidence * 100)}%"


def _non_apply_status(item: CleanupPlanItem) -> str:
    if item.layer == BLOCKED_LAYER and item.registry_key:
        return "管理員"
    if item.layer == BLOCKED_LAYER:
        return "不可執行"
    if item.layer in {PROCESS_LAYER, REVIEW_LAYER, REGISTRY_LAYER}:
        return "需允許"
    return "查看"


def _can_locate_item(item: CleanupPlanItem | None) -> bool:
    if item is None:
        return False
    return bool(item.registry_key or item.path or item.process_path)


def _locate_plan_item(item: CleanupPlanItem, parent: QWidget | None = None) -> None:
    if item.registry_key:
        RegistrySourceDialog(item, parent=parent).exec()
        return
    if item.path:
        _open_path_location(Path(item.path))
        return
    if item.process_path:
        _open_path_location(Path(item.process_path))
        return
    raise ValueError("此項目沒有可定位的位置。")


def _open_path_location(path: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("目前只支援 Windows 定位。")
    target = path.expanduser().resolve(strict=False)
    if target.exists() and target.is_file():
        subprocess.Popen(["explorer.exe", f"/select,{target}"])  # noqa: S603,S607 - local desktop action.
        return
    if target.exists() and target.is_dir():
        subprocess.Popen(["explorer.exe", str(target)])  # noqa: S603,S607 - local desktop action.
        return
    parent = target.parent
    if parent.exists():
        subprocess.Popen(["explorer.exe", str(parent)])  # noqa: S603,S607 - local desktop action.
        return
    raise FileNotFoundError(f"找不到可開啟的位置：{target}")


def _apply_row_style(row: QTreeWidgetItem, item: CleanupPlanItem) -> None:
    color = {
        SAFE_LAYER: "#155e36",
        PROCESS_LAYER: "#1d4ed8",
        REVIEW_LAYER: "#8a4b00",
        REGISTRY_LAYER: "#7c2d12",
        BLOCKED_LAYER: "#6b7280",
    }.get(item.layer, "#0c1320")
    for column in range(6):
        row.setForeground(column, QBrush(QColor(color)))


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def _initial_folder(context: LauncherContext) -> Path:
    if context.files:
        first = context.files[0]
        return first.parent if first.parent else Path.home()
    if context.folder:
        return context.folder
    return Path.home()


def _info_item(label: str, value: str, icon: QIcon | None = None) -> QTreeWidgetItem:
    item = QTreeWidgetItem([label, value])
    if icon is not None:
        item.setIcon(0, icon)
    return item


def _path_type_text(path: Path) -> str:
    if not path.exists():
        return "不存在"
    if path.is_dir():
        return "資料夾"
    suffix = path.suffix.upper().lstrip(".")
    return f"{suffix} 檔案" if suffix else "檔案"


def _target_size_text(plan: CleanupPlan, target: Path) -> str:
    item = next((entry for entry in plan.items if entry.path == str(target)), None)
    return _format_size(item.size_bytes) if item else "未知"


def _mtime_text(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "未知"
