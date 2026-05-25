from __future__ import annotations

import os
import re
from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from launcher.ui.theme import preferences_stylesheet
from launcher.windows.context_menu_registry import (
    ContextMenuEntry,
    context_menu_status,
    entry_detail_lines,
    install_context_menu,
    list_context_menu_entries,
    set_context_menu_entry_enabled,
    status_lines,
    uninstall_context_menu,
)


class ExplorerContextMenuDialog(QDialog):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("右鍵登錄管理員")
        self.setMinimumSize(980, 620)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._entries: list[ContextMenuEntry] = []
        self._entry_by_id: dict[str, ContextMenuEntry] = {}
        self._icon_provider = QFileIconProvider()

        title = QLabel("右鍵登錄管理員")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("盤點 Explorer 右鍵來源，並管理可安全停用的 shell 選單。COM shell extension 先列出供辨識，不直接改動。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._summary = QLabel("尚未檢查")
        self._summary.setObjectName("PreferenceHint")
        self._search = QLineEdit()
        self._search.setPlaceholderText("搜尋名稱、位置、來源、指令")
        self._search.textChanged.connect(self._apply_filter)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(["狀態", "名稱", "位置", "類型", "來源", "Command / CLSID"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._update_selection_detail)
        self._table.setMinimumHeight(260)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(130)

        refresh_button = QPushButton("重新檢查")
        refresh_button.clicked.connect(self.refresh_status)
        disable_button = QPushButton("停用選取")
        disable_button.clicked.connect(lambda: self._set_selected_enabled(False))
        enable_button = QPushButton("恢復選取")
        enable_button.clicked.connect(lambda: self._set_selected_enabled(True))
        install_button = QPushButton("安裝 / 修復工程工具列右鍵")
        install_button.setDefault(True)
        install_button.clicked.connect(self.install_or_update)
        remove_button = QPushButton("移除工程工具列右鍵")
        remove_button.clicked.connect(self.remove_context_menu)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh_button)
        buttons.addWidget(disable_button)
        buttons.addWidget(enable_button)
        buttons.addStretch(1)
        buttons.addWidget(remove_button)
        buttons.addWidget(install_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._summary)
        layout.addWidget(self._search)
        layout.addWidget(self._table, 1)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())
        self.refresh_status()

    def refresh_status(self) -> None:
        try:
            status = context_menu_status()
            self._entries = list_context_menu_entries()
        except Exception as exc:
            self._summary.setText("狀態：檢查失敗")
            self._detail.setPlainText(str(exc))
            return
        editable_count = sum(1 for entry in self._entries if entry.editable)
        disabled_count = sum(1 for entry in self._entries if not entry.enabled)
        self._summary.setText(
            f"工程工具列右鍵：{status.summary}｜掃描 {len(self._entries)} 項｜可停用/恢復 {editable_count} 項｜已停用 {disabled_count} 項"
        )
        self._entry_by_id = {entry.id: entry for entry in self._entries}
        self._populate_table(self._entries)
        if self._entries:
            self._update_selection_detail()
        else:
            self._detail.setPlainText("\n".join(status_lines(status)))

    def install_or_update(self) -> None:
        try:
            status = install_context_menu()
        except Exception as exc:
            QMessageBox.critical(self, "右鍵登錄管理員", str(exc))
            self.refresh_status()
            return
        self._summary.setText(f"狀態：{status.summary}")
        self._detail.setPlainText("[完成] 已安裝 / 修復 Explorer 右鍵選單。\n\n" + "\n".join(status_lines(status)))
        self.refresh_status()

    def remove_context_menu(self) -> None:
        answer = QMessageBox.question(
            self,
            "移除右鍵選單",
            "確定要移除 Explorer 右鍵選單「送到工程工具列」嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            status = uninstall_context_menu()
        except Exception as exc:
            QMessageBox.critical(self, "右鍵登錄管理員", str(exc))
            self.refresh_status()
            return
        self._summary.setText(f"狀態：{status.summary}")
        self._detail.setPlainText("[完成] 已移除 Explorer 右鍵選單。\n\n" + "\n".join(status_lines(status)))
        self.refresh_status()

    def _populate_table(self, entries: list[ContextMenuEntry]) -> None:
        self._table.setRowCount(0)
        for entry in entries:
            row = self._table.rowCount()
            self._table.insertRow(row)
            values = [
                "啟用" if entry.enabled else "停用",
                entry.label,
                entry.location.label,
                entry.kind,
                entry.root_name,
                entry.command or entry.details,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, entry.id)
                    item.setIcon(self._status_icon(entry))
                    if not entry.enabled:
                        item.setForeground(QBrush(QColor("#8a4b00")))
                if column == 1:
                    item.setIcon(self._entry_icon(entry))
                    if not entry.editable:
                        item.setForeground(QBrush(QColor("#5d6675")))
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()
        self._apply_filter()
        if self._table.rowCount() > 0:
            self._table.selectRow(0)

    def _apply_filter(self) -> None:
        needle = self._search.text().strip().casefold()
        for row in range(self._table.rowCount()):
            haystack = " ".join(
                self._table.item(row, column).text()
                for column in range(self._table.columnCount())
                if self._table.item(row, column) is not None
            ).casefold()
            self._table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _selected_entry(self) -> ContextMenuEntry | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        return self._entry_by_id.get(str(item.data(Qt.ItemDataRole.UserRole)))

    def _update_selection_detail(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._detail.setPlainText("\n".join(line for line in entry_detail_lines(entry) if line))

    def _set_selected_enabled(self, enabled: bool) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, "右鍵登錄管理員", "請先選取一個右鍵項目。")
            return
        if not entry.editable:
            QMessageBox.information(self, "右鍵登錄管理員", entry.disabled_reason or "此項目目前不支援直接停用。")
            return
        try:
            set_context_menu_entry_enabled(entry, enabled)
        except Exception as exc:
            QMessageBox.critical(self, "右鍵登錄管理員", str(exc))
            return
        self.refresh_status()

    def _status_icon(self, entry: ContextMenuEntry) -> QIcon:
        pixmap = QStyle.StandardPixmap.SP_DialogApplyButton if entry.enabled else QStyle.StandardPixmap.SP_DialogCancelButton
        return self.style().standardIcon(pixmap)

    def _entry_icon(self, entry: ContextMenuEntry) -> QIcon:
        icon_path = _resolved_icon_path(entry.icon) or _resolved_icon_path(entry.command)
        if icon_path is not None:
            icon = self._icon_provider.icon(QFileInfo(str(icon_path)))
            if not icon.isNull():
                return icon
        if entry.kind == "shellex":
            return self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        if "磁碟" in entry.location.label:
            return self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        if "資料夾" in entry.location.label or entry.location.label == "Folder":
            return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)


def _resolved_icon_path(value: str) -> Path | None:
    raw = value.strip()
    if not raw:
        return None
    raw = os.path.expandvars(raw)
    match = re.match(r'^"([^"]+)"', raw)
    if match:
        candidate = match.group(1)
    else:
        candidate = raw.split()[0]
    if "," in candidate:
        candidate = candidate.split(",", 1)[0]
    candidate = candidate.strip().strip('"')
    if not candidate:
        return None
    path = Path(candidate)
    return path if path.exists() else None
