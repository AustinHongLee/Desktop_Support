from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QFileInfo, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileIconProvider,
)

from launcher.core.safe_cleanup import (
    QuarantineSession,
    RestoreConflictPolicy,
    delete_quarantine_session,
    list_quarantine_sessions,
    load_quarantine_manifest,
    restore_quarantine_items,
)
from launcher.ui.theme import preferences_stylesheet


class QuarantineBrowserDialog(QDialog):
    def __init__(self, *, quarantine_root: Path | None = None, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._root = quarantine_root
        self._sessions: list[QuarantineSession] = []
        self._manifest: dict[str, Any] = {}
        self._records: list[dict[str, Any]] = []
        self._icon_provider = QFileIconProvider()

        self.setWindowTitle("隔離區管理")
        self.setMinimumSize(1050, 650)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("隔離區管理")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("這裡管理安全清除工作台搬走的檔案。可先還原、確認無誤後再永久刪除隔離 session。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._session_table = QTableWidget(0, 5)
        self._session_table.setHorizontalHeaderLabels(["時間", "項目", "已還原", "大小", "目標"])
        self._session_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._session_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._session_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._session_table.itemSelectionChanged.connect(self._on_session_changed)

        self._record_table = QTableWidget(0, 5)
        self._record_table.setHorizontalHeaderLabels(["狀態", "原始位置", "隔離位置", "大小", "SHA256"])
        self._record_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._record_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._record_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._record_table.itemSelectionChanged.connect(self._update_detail)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(115)

        self._conflict_policy = QComboBox()
        self._conflict_policy.addItem("衝突時略過", RestoreConflictPolicy.SKIP.value)
        self._conflict_policy.addItem("衝突時改名還原", RestoreConflictPolicy.RENAME.value)
        self._conflict_policy.addItem("衝突時覆蓋原位置", RestoreConflictPolicy.OVERWRITE.value)
        self._conflict_policy.currentIndexChanged.connect(lambda _index: self._update_conflict_controls())
        self._overwrite_confirm = QCheckBox("我確認允許覆蓋原位置")
        self._overwrite_confirm.setEnabled(False)

        refresh_button = QPushButton("重新整理")
        refresh_button.clicked.connect(self.refresh_sessions)
        self._open_folder_button = QPushButton("開啟隔離資料夾")
        self._open_folder_button.clicked.connect(self.open_current_folder)
        self._restore_selected_button = QPushButton("還原選取")
        self._restore_selected_button.clicked.connect(self.restore_selected)
        self._restore_all_button = QPushButton("還原全部")
        self._restore_all_button.clicked.connect(self.restore_all)
        self._delete_button = QPushButton("永久刪除此 session")
        self._delete_button.clicked.connect(self.delete_current_session)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        session_panel = QWidget()
        session_layout = QVBoxLayout(session_panel)
        session_layout.setContentsMargins(0, 0, 0, 0)
        session_layout.setSpacing(8)
        session_title = QLabel("隔離紀錄")
        session_title.setObjectName("PreferenceTitle")
        session_layout.addWidget(session_title)
        session_layout.addWidget(self._session_table, 1)

        record_panel = QWidget()
        record_layout = QVBoxLayout(record_panel)
        record_layout.setContentsMargins(0, 0, 0, 0)
        record_layout.setSpacing(8)
        record_title = QLabel("此 session 內容")
        record_title.setObjectName("PreferenceTitle")
        record_layout.addWidget(record_title)
        record_layout.addWidget(self._record_table, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(session_panel)
        splitter.addWidget(record_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh_button)
        buttons.addWidget(self._open_folder_button)
        buttons.addWidget(QLabel("還原衝突"))
        buttons.addWidget(self._conflict_policy)
        buttons.addWidget(self._overwrite_confirm)
        buttons.addStretch(1)
        buttons.addWidget(self._restore_selected_button)
        buttons.addWidget(self._restore_all_button)
        buttons.addWidget(self._delete_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())
        self.refresh_sessions()

    def refresh_sessions(self) -> None:
        current = self._current_session_path()
        self._refresh_sessions(preselect=current)

    def open_current_folder(self) -> None:
        session = self._current_session()
        if session is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(session.path)))

    def restore_selected(self) -> None:
        session = self._current_session()
        if session is None:
            return
        indices = self._selected_record_indices()
        if not indices:
            QMessageBox.information(self, "隔離區管理", "請先選取要還原的項目。")
            return
        if not self._validate_restore_policy():
            return
        if not self._confirm_restore(len(indices)):
            return
        result = restore_quarantine_items(session.path, indices, conflict_policy=self._selected_conflict_policy())
        self._show_restore_result(result.restored_count, result.errors)
        self._refresh_sessions(preselect=session.path)

    def restore_all(self) -> None:
        session = self._current_session()
        if session is None:
            return
        pending = [index for index, record in enumerate(self._records) if not record.get("restored_at")]
        if not pending:
            QMessageBox.information(self, "隔離區管理", "此 session 目前沒有待還原項目。")
            return
        if not self._validate_restore_policy():
            return
        if not self._confirm_restore(len(pending)):
            return
        result = restore_quarantine_items(session.path, set(pending), conflict_policy=self._selected_conflict_policy())
        self._show_restore_result(result.restored_count, result.errors)
        self._refresh_sessions(preselect=session.path)

    def delete_current_session(self) -> None:
        session = self._current_session()
        if session is None:
            return
        answer = QMessageBox.question(
            self,
            "永久刪除隔離 session",
            f"將永久刪除這個隔離 session：\n{session.path}\n\n已還原的原始檔不會受影響；仍在隔離區內的檔案會被刪除。確定？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_quarantine_session(session.path, root=self._root)
        except Exception as exc:
            QMessageBox.warning(self, "隔離區管理", f"刪除失敗：{exc}")
            return
        self._refresh_sessions()

    def _refresh_sessions(self, *, preselect: Path | None = None) -> None:
        self._sessions = list_quarantine_sessions(self._root)
        self._session_table.blockSignals(True)
        self._session_table.setRowCount(len(self._sessions))
        selected_row = 0 if self._sessions else -1
        for row, session in enumerate(self._sessions):
            if preselect is not None and session.path == preselect:
                selected_row = row
            values = [
                _format_time(session.created_at, session.path.name),
                str(session.moved_count),
                f"{session.restored_count} / {session.moved_count}",
                _format_size(session.size_bytes),
                _targets_text(session.targets),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                if column == 0:
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                self._session_table.setItem(row, column, item)
        self._session_table.blockSignals(False)
        self._session_table.resizeColumnsToContents()
        self._session_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        if selected_row >= 0:
            self._session_table.setCurrentCell(selected_row, 0)
            self._load_session(selected_row)
        else:
            self._load_session(None)

    def _on_session_changed(self) -> None:
        row = self._session_table.currentRow()
        self._load_session(row if row >= 0 else None)

    def _load_session(self, row: int | None) -> None:
        self._manifest = {}
        self._records = []
        if row is not None and 0 <= row < len(self._sessions):
            try:
                self._manifest = load_quarantine_manifest(self._sessions[row].path)
                self._records = _moved_records(self._manifest)
            except Exception as exc:
                self._detail.setPlainText(f"讀取 manifest 失敗：{exc}")
        self._populate_records()
        self._update_button_states()

    def _populate_records(self) -> None:
        self._record_table.blockSignals(True)
        self._record_table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            restored = bool(record.get("restored_at"))
            status = "已還原" if restored else "待處理"
            original = str(record.get("original_path") or record.get("item", {}).get("path") or "")
            destination = str(record.get("destination") or "")
            values = [
                status,
                original,
                destination,
                _format_size(_record_size(record)),
                str(record.get("original_sha256") or ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                if column == 0:
                    item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton if restored else QStyle.StandardPixmap.SP_FileIcon))
                if column == 1 and original:
                    icon = self._icon_provider.icon(QFileInfo(original))
                    if not icon.isNull():
                        item.setIcon(icon)
                if restored:
                    item.setForeground(QBrush(QColor("#64748b")))
                self._record_table.setItem(row, column, item)
        self._record_table.blockSignals(False)
        self._record_table.resizeColumnsToContents()
        self._record_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._record_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        if self._records:
            self._record_table.setCurrentCell(0, 0)
        else:
            self._detail.setPlainText("目前沒有隔離紀錄。")

    def _update_detail(self) -> None:
        record = self._current_record()
        session = self._current_session()
        if record is None:
            if session is None:
                self._detail.setPlainText("目前沒有隔離 session。")
            return
        item = record.get("item", {}) if isinstance(record.get("item"), dict) else {}
        restored_text = _format_time(float(record.get("restored_at") or 0), "") if record.get("restored_at") else "否"
        lines = [
            f"項目：{item.get('label') or Path(str(record.get('original_path') or '')).name}",
            f"狀態：{'已還原' if record.get('restored_at') else '待處理'}",
            f"原始位置：{record.get('original_path') or item.get('path') or ''}",
            f"隔離位置：{record.get('destination') or ''}",
            f"大小：{_format_size(_record_size(record))}",
            f"SHA256：{record.get('original_sha256') or '未記錄或目錄'}",
            f"移入時間：{_format_time(float(record.get('moved_at') or 0), '')}",
            f"還原時間：{restored_text}",
        ]
        self._detail.setPlainText("\n".join(lines))

    def _update_button_states(self) -> None:
        has_session = self._current_session() is not None
        has_pending = any(not record.get("restored_at") for record in self._records)
        self._open_folder_button.setEnabled(has_session)
        self._restore_selected_button.setEnabled(has_session and has_pending)
        self._restore_all_button.setEnabled(has_session and has_pending)
        self._delete_button.setEnabled(has_session)
        self._conflict_policy.setEnabled(has_session and has_pending)
        self._update_conflict_controls()

    def _current_session(self) -> QuarantineSession | None:
        row = self._session_table.currentRow()
        if 0 <= row < len(self._sessions):
            return self._sessions[row]
        return None

    def _current_session_path(self) -> Path | None:
        session = self._current_session()
        return session.path if session is not None else None

    def _current_record(self) -> dict[str, Any] | None:
        row = self._record_table.currentRow()
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def _selected_record_indices(self) -> set[int]:
        indices: set[int] = set()
        for item in self._record_table.selectedItems():
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, int):
                indices.add(value)
        return indices

    def _confirm_restore(self, count: int) -> bool:
        policy_text = self._conflict_policy.currentText()
        answer = QMessageBox.question(
            self,
            "還原隔離項目",
            f"將還原 {count} 個項目。\n衝突策略：{policy_text}\n\n確定？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _selected_conflict_policy(self) -> RestoreConflictPolicy:
        return RestoreConflictPolicy(str(self._conflict_policy.currentData() or RestoreConflictPolicy.SKIP.value))

    def _validate_restore_policy(self) -> bool:
        if self._selected_conflict_policy() != RestoreConflictPolicy.OVERWRITE:
            return True
        if self._overwrite_confirm.isChecked():
            return True
        QMessageBox.warning(self, "隔離區管理", "覆蓋原位置前，請先勾選確認。")
        return False

    def _update_conflict_controls(self) -> None:
        overwrite = self._selected_conflict_policy() == RestoreConflictPolicy.OVERWRITE
        self._overwrite_confirm.setEnabled(overwrite and self._conflict_policy.isEnabled())
        if not overwrite:
            self._overwrite_confirm.setChecked(False)

    def _show_restore_result(self, restored_count: int, errors: tuple[str, ...]) -> None:
        lines = [f"已還原：{restored_count} 個項目"]
        if errors:
            lines.append("")
            lines.extend(f"錯誤：{error}" for error in errors)
        QMessageBox.information(self, "隔離區管理", "\n".join(lines))


def _moved_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    moved = manifest.get("moved", [])
    return [record for record in moved if isinstance(record, dict)] if isinstance(moved, list) else []


def _record_size(record: dict[str, Any]) -> int:
    try:
        return int(record.get("original_size_bytes") or record.get("item", {}).get("size_bytes") or 0)
    except (TypeError, ValueError):
        return 0


def _targets_text(targets: tuple[str, ...]) -> str:
    if not targets:
        return "未記錄"
    if len(targets) == 1:
        return targets[0]
    return f"{len(targets)} 個目標，第一個：{targets[0]}"


def _format_time(value: float, fallback: str) -> str:
    if value <= 0:
        return fallback or "未知"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
