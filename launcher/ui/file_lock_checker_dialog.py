from __future__ import annotations

import subprocess
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from launcher.core.context_model import LauncherContext
from launcher.core.file_locks import FileLockReport, LockingProcess, close_locking_process, find_locking_processes, targets_from_context
from launcher.core.safe_cleanup import ScanCancelled, ScanCancelToken
from launcher.core.state_store import AppStateStore
from launcher.ui.theme import safe_cleanup_stylesheet, theme_by_name


class FileLockCheckerDialog(QDialog):
    def __init__(self, context: LauncherContext, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._context = context
        self._report = FileLockReport(targets=targets_from_context(context), processes=())
        self._scan_thread: QThread | None = None
        self._scan_worker: _LockScanWorker | None = None
        self._process_by_pid: dict[int, LockingProcess] = {}

        self.setWindowTitle("檔案佔用檢查器")
        self.setMinimumSize(980, 620)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("檔案佔用檢查器")
        title.setObjectName("H1")
        hint = QLabel("檢查目前檔案或資料夾是否被程序佔用；可定位程序、正常關閉，必要時再強制結束。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        self._target_path = QLineEdit()
        self._target_path.setPlaceholderText("選擇檔案 / 資料夾，或貼上路徑")
        self._target_path.returnPressed.connect(self.refresh_scan)
        self._target_path.setText(_target_text(self._report.targets))

        pick_file = QPushButton("選擇檔案")
        pick_file.clicked.connect(self.pick_file)
        pick_folder = QPushButton("選擇資料夾")
        pick_folder.clicked.connect(self.pick_folder)
        self._refresh_button = QPushButton("重新檢查")
        self._refresh_button.setObjectName("Primary")
        self._refresh_button.clicked.connect(self.refresh_scan)
        self._cancel_button = QPushButton("取消檢查")
        self._cancel_button.clicked.connect(self.cancel_scan)
        self._cancel_button.setEnabled(False)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        target_row.addWidget(QLabel("檢查目標"))
        target_row.addWidget(self._target_path, 1)
        target_row.addWidget(self._refresh_button)
        target_row.addWidget(self._cancel_button)
        target_row.addWidget(pick_file)
        target_row.addWidget(pick_folder)

        self._summary = QLabel()
        self._summary.setObjectName("Muted")
        self._summary.setWordWrap(True)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(["程序", "PID", "狀態", "佔用原因", "被佔用檔案", "程序路徑"])
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setRootIsDecorated(False)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._tree.itemSelectionChanged.connect(self._refresh_buttons)
        self._configure_columns()

        self._normal_close_button = QPushButton("正常關閉")
        self._normal_close_button.clicked.connect(lambda: self.close_selected(force=False))
        self._force_close_button = QPushButton("強制結束")
        self._force_close_button.setObjectName("Danger")
        self._force_close_button.clicked.connect(lambda: self.close_selected(force=True))
        self._locate_button = QPushButton("定位程序")
        self._locate_button.clicked.connect(self.locate_selected_process)
        self._copy_button = QPushButton("複製路徑")
        self._copy_button.clicked.connect(self.copy_selected_path)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self._normal_close_button)
        buttons.addWidget(self._force_close_button)
        buttons.addWidget(self._locate_button)
        buttons.addWidget(self._copy_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(target_row)
        layout.addWidget(self._summary)
        layout.addWidget(self._tree, 1)
        layout.addLayout(buttons)

        self.setStyleSheet(safe_cleanup_stylesheet(theme_by_name(AppStateStore().theme_name)))
        self._populate()
        self.refresh_scan()

    def pick_file(self) -> None:
        file_path, _selected_filter = QFileDialog.getOpenFileName(self, "選擇要檢查的檔案", str(_initial_folder(self._context)), "所有檔案 (*.*)")
        if not file_path:
            return
        self._context = LauncherContext.from_paths([file_path], source="picker.file_lock")
        self._target_path.setText(file_path)
        self.refresh_scan()

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "選擇要檢查的資料夾", str(_initial_folder(self._context)))
        if not folder:
            return
        self._context = LauncherContext(folder=Path(folder), source="picker.file_lock")
        self._target_path.setText(folder)
        self.refresh_scan()

    def refresh_scan(self) -> None:
        if self._scan_thread is not None:
            return
        self._sync_context_from_text()
        targets = targets_from_context(self._context)
        self._set_scanning(True)
        thread = QThread(self)
        worker = _LockScanWorker(targets)
        worker.moveToThread(thread)
        worker.finished.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        worker.cancelled.connect(self._on_scan_cancelled)
        thread.started.connect(worker.run)
        thread.finished.connect(lambda: self._remove_scan_thread(thread, worker))
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        self._scan_thread = thread
        self._scan_worker = worker
        thread.start()

    def cancel_scan(self) -> None:
        if self._scan_worker is None:
            return
        self._scan_worker.cancel()
        self._summary.setText("正在取消檢查。")

    def close_selected(self, *, force: bool) -> None:
        process = self._selected_process()
        if process is None:
            return
        if not process.can_close:
            QMessageBox.information(self, "檔案佔用檢查器", f"不建議關閉此程序：{process.close_block_reason or '未知原因'}")
            return
        if force:
            answer = QMessageBox.warning(
                self,
                "強制結束程序",
                (
                    f"將強制結束 {process.name} (PID {process.pid})。\n\n"
                    "未儲存資料可能遺失；確定要繼續？"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            close_locking_process(process.pid, force=force)
        except Exception as exc:
            QMessageBox.warning(self, "檔案佔用檢查器", f"關閉失敗：{exc}")
            return
        self._summary.setText(f"已{'強制結束' if force else '嘗試正常關閉'} {process.name} (PID {process.pid})；正在重新檢查。")
        self.refresh_scan()

    def locate_selected_process(self) -> None:
        process = self._selected_process()
        if process is None or process.path is None:
            return
        try:
            _open_path_location(process.path)
        except Exception as exc:
            QMessageBox.warning(self, "檔案佔用檢查器", f"無法定位程序：{exc}")

    def copy_selected_path(self) -> None:
        process = self._selected_process()
        if process is None:
            return
        QApplication.clipboard().setText(process.path_text or str(process.pid))

    def _sync_context_from_text(self) -> None:
        text = self._target_path.text().strip()
        if not text:
            return
        path = Path(text)
        if path.is_dir():
            self._context = LauncherContext(folder=path, source="typed.file_lock")
        else:
            self._context = LauncherContext.from_paths([path], source="typed.file_lock")

    def _set_scanning(self, active: bool) -> None:
        self._refresh_button.setEnabled(not active)
        self._cancel_button.setEnabled(active)
        if active:
            self._summary.setText("檢查中：正在詢問 Restart Manager 與目前程序清單。")
            self._tree.clear()
            item = QTreeWidgetItem(["檢查中", "", "", "請稍候，完成後會列出佔用程序。", "", ""])
            item.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(item)
        self._refresh_buttons()

    def _on_scan_finished(self, report: object) -> None:
        if isinstance(report, FileLockReport):
            self._report = report
        self._populate()

    def _on_scan_failed(self, message: str) -> None:
        self._report = FileLockReport(targets=targets_from_context(self._context), processes=())
        self._tree.clear()
        self._summary.setText(f"檢查失敗：{message}")
        self._refresh_buttons()

    def _on_scan_cancelled(self) -> None:
        self._tree.clear()
        self._summary.setText("已取消檢查。")
        self._refresh_buttons()

    def _remove_scan_thread(self, thread: QThread, worker: "_LockScanWorker") -> None:
        if self._scan_thread is thread:
            self._scan_thread = None
            self._scan_worker = None
        worker.deleteLater()
        thread.deleteLater()
        self._refresh_buttons()

    def _populate(self) -> None:
        self._tree.clear()
        self._process_by_pid = {process.pid: process for process in self._report.processes}
        self._target_path.setText(_target_text(self._report.targets))
        if not self._report.targets:
            self._summary.setText("尚未選擇檢查目標。")
            self._refresh_buttons()
            return
        if not self._report.processes:
            resource_text = f"｜已檢查 {self._report.scanned_resource_count} 個檔案" if self._report.scanned_resource_count else ""
            self._summary.setText(f"未找到佔用程序{resource_text}｜目標：{_target_text(self._report.targets)}")
            self._refresh_buttons()
            return
        resource_text = f"｜已檢查 {self._report.scanned_resource_count} 個檔案" if self._report.scanned_resource_count else ""
        self._summary.setText(
            f"找到 {len(self._report.processes)} 個可能佔用程序｜可正常關閉 {self._report.can_close_count} 個｜"
            f"檢查時間 {time.strftime('%H:%M:%S')}{resource_text}"
        )
        for process in self._report.processes:
            item = QTreeWidgetItem(
                [
                    process.name,
                    str(process.pid),
                    "可關閉" if process.can_close else f"保留：{process.close_block_reason or '不建議'}",
                    process.reason,
                    process.locked_paths_text,
                    process.path_text,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, process.pid)
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            color = "#155e36" if process.can_close else "#7c2d12"
            for column in range(self._tree.columnCount()):
                item.setForeground(column, QBrush(QColor(color)))
            self._tree.addTopLevelItem(item)
        self._tree.setCurrentItem(self._tree.topLevelItem(0))
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        process = self._selected_process()
        scanning = self._scan_thread is not None
        can_close = process is not None and process.can_close and not scanning
        has_path = process is not None and process.path is not None
        self._normal_close_button.setEnabled(can_close)
        self._force_close_button.setEnabled(can_close)
        self._locate_button.setEnabled(has_path and not scanning)
        self._copy_button.setEnabled(process is not None and not scanning)
        self._cancel_button.setEnabled(scanning)

    def _selected_process(self) -> LockingProcess | None:
        current = self._tree.currentItem()
        if current is None:
            return None
        pid = current.data(0, Qt.ItemDataRole.UserRole)
        try:
            return self._process_by_pid.get(int(pid))
        except (TypeError, ValueError):
            return None

    def _configure_columns(self) -> None:
        header = self._tree.header()
        header.setStretchLastSection(False)
        widths = (220, 84, 170, 360, 460, 560)
        for column, width in enumerate(widths):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self._tree.setColumnWidth(column, width)


class _LockScanWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, targets: tuple[Path, ...]) -> None:
        super().__init__()
        self._targets = targets
        self._cancel_token = ScanCancelToken()

    def cancel(self) -> None:
        self._cancel_token.cancel()

    def run(self) -> None:
        try:
            self.finished.emit(find_locking_processes(self._targets, cancel_token=self._cancel_token))
        except ScanCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


def _target_text(targets: tuple[Path, ...]) -> str:
    if not targets:
        return ""
    if len(targets) == 1:
        return str(targets[0])
    return f"{len(targets)} 個目標，第一個為 {targets[0]}"


def _initial_folder(context: LauncherContext) -> Path:
    if context.files:
        first = context.files[0]
        return first.parent if first.parent else Path.home()
    if context.folder:
        return context.folder
    return Path.home()


def _open_path_location(path: Path) -> None:
    target = path.expanduser().resolve(strict=False)
    if target.exists() and target.is_file():
        subprocess.Popen(["explorer.exe", f"/select,{target}"])  # noqa: S603,S607 - local desktop action.
        return
    parent = target.parent
    if parent.exists():
        subprocess.Popen(["explorer.exe", str(parent)])  # noqa: S603,S607 - local desktop action.
        return
    raise FileNotFoundError(f"找不到可開啟的位置：{target}")
