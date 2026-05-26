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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.core.context_model import LauncherContext
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
    run_official_uninstaller,
    scan_stage_count,
)
from launcher.ui.installed_app_picker_dialog import InstalledApplicationPickerDialog
from launcher.ui.quarantine_browser_dialog import QuarantineBrowserDialog
from launcher.ui.registry_source_dialog import RegistrySourceDialog
from launcher.ui.theme import preferences_stylesheet


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

        self.setWindowTitle("安全清除工作台")
        self.setMinimumSize(1120, 700)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("安全清除工作台")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("先選一個檔案/資料夾，或直接輸入已被刪除的舊路徑/產品名稱；工作台會顯示目標身分、殘留足跡、工具紀錄與登錄檔候選。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._summary = QLabel()
        self._summary.setObjectName("PreferenceHint")
        self._target_path = QLineEdit()
        self._target_path.setPlaceholderText("可輸入舊 exe 路徑、資料夾路徑或產品名稱，例如 Tekla Structures 2026")
        self._target_path.returnPressed.connect(self.analyze_typed_target)

        app_button = QPushButton("選擇應用")
        app_button.clicked.connect(self.pick_installed_app)
        file_button = QPushButton("選擇檔案")
        file_button.clicked.connect(self.pick_file)
        folder_button = QPushButton("選擇資料夾")
        folder_button.clicked.connect(self.pick_folder)
        typed_button = QPushButton("分析輸入")
        typed_button.clicked.connect(self.analyze_typed_target)
        self._refresh_button = QPushButton("重新分析")
        self._refresh_button.clicked.connect(self.refresh_plan)
        self._cancel_scan_button = QPushButton("取消分析")
        self._cancel_scan_button.clicked.connect(self.cancel_scan)
        self._cancel_scan_button.setEnabled(False)

        target_controls = QHBoxLayout()
        target_controls.addWidget(QLabel("分析目標"))
        target_controls.addWidget(self._target_path, 1)
        target_controls.addWidget(app_button)
        target_controls.addWidget(file_button)
        target_controls.addWidget(folder_button)
        target_controls.addWidget(typed_button)
        target_controls.addWidget(self._refresh_button)
        target_controls.addWidget(self._cancel_scan_button)

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, scan_stage_count())
        self._scan_progress.setTextVisible(False)
        self._scan_progress.setFixedHeight(8)
        self._scan_progress.hide()

        self._uninstall_panel = QWidget()
        uninstall_layout = QHBoxLayout(self._uninstall_panel)
        uninstall_layout.setContentsMargins(10, 8, 10, 8)
        uninstall_layout.setSpacing(10)
        uninstall_icon = QLabel()
        uninstall_icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton).pixmap(18, 18))
        self._uninstall_label = QLabel()
        self._uninstall_label.setObjectName("PreferenceHint")
        self._uninstall_label.setWordWrap(True)
        self._uninstall_button = QPushButton("執行官方解除安裝")
        self._uninstall_button.clicked.connect(self.run_detected_uninstaller)
        uninstall_layout.addWidget(uninstall_icon)
        uninstall_layout.addWidget(self._uninstall_label, 1)
        uninstall_layout.addWidget(self._uninstall_button)
        self._uninstall_panel.hide()

        self._identity = QLabel()
        self._identity.setObjectName("PreferenceTitle")
        self._identity.setWordWrap(True)
        self._conclusion = QLabel()
        self._conclusion.setObjectName("PreferenceHint")
        self._conclusion.setWordWrap(True)

        self._info_tree = QTreeWidget()
        self._info_tree.setColumnCount(2)
        self._info_tree.setHeaderLabels(["資訊", "內容"])
        self._info_tree.setMinimumWidth(390)
        self._info_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(["套用", "清除建議", "動作", "判斷註解", "位置 / 登錄檔"])
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
        self._system_guard = QCheckBox("我確認沒有勾選系統保護路徑")
        self._system_guard.setToolTip("系統保護路徑仍不會執行；這個確認用來避免使用者忽略 blocked 層警告。")

        self._apply_button = QPushButton("隔離 / 清理勾選項目")
        self._apply_button.setDefault(True)
        self._apply_button.clicked.connect(self.apply_selected)
        self._locate_button = QPushButton("檢視 / 定位來源")
        self._locate_button.setToolTip("開啟檔案所在位置；登錄檔項目會用內建檢視器列出 key 內所有值，必要時再外部開啟 Regedit。")
        self._locate_button.clicked.connect(self.locate_selected_item)
        self._locate_button.setEnabled(False)
        quarantine_button = QPushButton("管理隔離區")
        quarantine_button.clicked.connect(self.open_quarantine_browser)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        toggles = QHBoxLayout()
        toggles.addWidget(self._include_review)
        toggles.addWidget(self._include_process)
        toggles.addWidget(self._include_registry)
        toggles.addWidget(self._system_guard)
        toggles.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addWidget(quarantine_button)
        buttons.addStretch(1)
        buttons.addWidget(self._locate_button)
        buttons.addWidget(self._apply_button)
        buttons.addWidget(close_button)

        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(8)
        info_layout.addWidget(self._identity)
        info_layout.addWidget(self._conclusion)
        info_layout.addWidget(self._info_tree, 1)

        suggestion_panel = QWidget()
        suggestion_layout = QVBoxLayout(suggestion_panel)
        suggestion_layout.setContentsMargins(0, 0, 0, 0)
        suggestion_layout.setSpacing(8)
        suggestion_title = QLabel("清除建議")
        suggestion_title.setObjectName("PreferenceTitle")
        suggestion_layout.addWidget(suggestion_title)
        suggestion_layout.addWidget(self._summary)
        suggestion_layout.addWidget(self._tree, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(info_panel)
        splitter.addWidget(suggestion_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(target_controls)
        layout.addWidget(self._scan_progress)
        layout.addWidget(self._uninstall_panel)
        layout.addWidget(splitter, 1)
        layout.addLayout(toggles)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())
        self._show_scan_placeholder()
        self.refresh_plan()

    def open_quarantine_browser(self) -> None:
        dialog = QuarantineBrowserDialog(parent=self)
        dialog.exec()

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
            QMessageBox.warning(self, "安全清除工作台", "Blocked / 系統保護項目不可執行，請取消勾選。")
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
        if registry_count and not self._system_guard.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "請先確認沒有勾選系統保護路徑。")
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
        self._summary.setText(f"套用中：{current} / {total}｜{label}")
        self._detail.setPlainText(f"正在套用清理：{label}\n請不要關閉相關檔案或手動移動目標。")

    def _on_apply_finished(self, result: object) -> None:
        if not isinstance(result, CleanupApplyResult):
            self._set_apply_controls(False)
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
        QMessageBox.information(self, "安全清除工作台", "\n".join(lines[:5]))
        self.refresh_plan()

    def _on_apply_failed(self, message: str) -> None:
        self._set_apply_controls(False)
        self._detail.setPlainText(message)
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
        self._cancel_scan_button.setEnabled(active)
        self._refresh_button.setEnabled(not active and not self._apply_active)
        self._apply_button.setEnabled(not active and not self._apply_active)
        self._locate_button.setEnabled(not active and not self._apply_active and _can_locate_item(self._current_plan_item()))

    def _set_apply_controls(self, active: bool) -> None:
        self._apply_active = active
        self._scan_progress.setVisible(active)
        if active:
            self._scan_progress.setRange(0, 1)
            self._scan_progress.setValue(0)
            self._apply_button.setText("套用中...")
            self._summary.setText("套用中：準備處理勾選項目")
        else:
            self._apply_button.setText("隔離 / 清理勾選項目")
        self._cancel_scan_button.setEnabled(False)
        self._refresh_button.setEnabled(not active and not self._scan_active)
        self._apply_button.setEnabled(not active and not self._scan_active)
        self._locate_button.setEnabled(not active and _can_locate_item(self._current_plan_item()))
        self._uninstall_button.setEnabled(not active and not self._scan_active)

    def _show_scan_placeholder(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        self._item_by_id = {}
        self._target_path.setText(_target_path_text(self._plan.targets))
        self._identity.setText("正在分析目標")
        self._conclusion.setText("正在掃描目標、關聯檔、捷徑、執行中程序與登錄檔候選。")
        self._summary.setText("分析中...")
        self._uninstall_panel.hide()
        item = QTreeWidgetItem(["分析中", "請稍候", "無動作", "背景分析進行中，完成後會自動更新清除建議。", ""])
        item.setFirstColumnSpanned(True)
        self._tree.addTopLevelItem(item)
        self._configure_suggestion_columns()
        self._tree.blockSignals(False)
        self._populate_info_tree()
        self._detail.setPlainText("分析中；大型資料夾或登錄檔候選較多時，視窗仍可移動與關閉。")

    def _populate(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        self._item_by_id = {item.id: item for item in self._plan.items}
        self._target_path.setText(_target_path_text(self._plan.targets))
        self._identity.setText(_identity_text(self._plan))
        self._conclusion.setText(_analysis_conclusion(self._plan))
        self._summary.setText(_summary_text(self._plan))
        self._update_uninstaller_panel()
        self._populate_info_tree()
        for layer in (SAFE_LAYER, PROCESS_LAYER, REVIEW_LAYER, REGISTRY_LAYER, BLOCKED_LAYER):
            layer_items = [item for item in self._plan.items if item.layer == layer]
            if not layer_items:
                continue
            group = QTreeWidgetItem([_layer_title(layer, len(layer_items)), "", "", "", ""])
            group.setIcon(0, self._layer_icon(layer))
            group.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(group)
            for item in layer_items:
                child = QTreeWidgetItem(["", item.label, item.action, item.note, _item_location(item)])
                child.setData(0, Qt.ItemDataRole.UserRole, item.id)
                child.setIcon(1, self._item_icon(item))
                child.setCheckState(0, Qt.CheckState.Checked if item.checked_default and item.executable else Qt.CheckState.Unchecked)
                _apply_row_style(child, item)
                group.addChild(child)
            group.setExpanded(layer != BLOCKED_LAYER)
        self._configure_suggestion_columns()
        self._tree.blockSignals(False)
        self._refresh_item_flags()
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
        default_widths = (88, 360, 110, 680, 860)
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
                    flags |= Qt.ItemFlag.ItemIsUserCheckable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsUserCheckable
                    child.setCheckState(0, Qt.CheckState.Unchecked)
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
            f"註解：{item.note}",
            f"可執行：{'是' if item.executable else '否'}",
        ]
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
                lines.append("處理方式：一般模式不直接刪；深度清理需管理員權限，先匯出 .reg 備份，再刪除已確認屬於目標的值或 key。")
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
    if not plan.official_uninstallers:
        return None
    return plan.official_uninstallers[0]


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
    associated_count = _count_kinds(plan, {"associated_file", "associated_folder"})
    uninstall_count = len(plan.official_uninstallers)
    if not target.exists() and (footprint_count or registry_count or shortcut_count or uninstall_count):
        return (
            "判斷：目標本體不存在，已進入退役後殘渣掃描。"
            "這通常發生在主程式被其他解除安裝器硬刪後；"
            f"目前找到官方解除安裝 {uninstall_count}、應用程式足跡 {footprint_count}、捷徑 {shortcut_count}、登錄檔/Installer 殘留 {registry_count}。"
        )
    if target.suffix.casefold() == ".exe" and (uninstall_count or install_count or footprint_count or registry_count or shortcut_count):
        return (
            "判斷：這看起來像一個應用程式執行檔。建議先跑官方解除安裝，再清殘留；"
            f"目前找到官方解除安裝 {uninstall_count}、安裝資料夾 {install_count}、應用程式足跡 {footprint_count}、"
            f"執行中/可能佔用 {process_count}、捷徑 {shortcut_count}、登錄檔候選 {registry_count}。"
        )
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
    for column in range(5):
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
