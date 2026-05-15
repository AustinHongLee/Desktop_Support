from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from launcher.core.context_model import LauncherContext
from launcher.plugins.rename_tools.rename_actions import (
    RenameOperation,
    _apply_operations,
    _validate_operations,
)


class RenameDialog(QDialog):
    def __init__(self, context: LauncherContext, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._context = context
        self._targets = self._resolve_targets(context)

        self.setWindowTitle("批次更名")
        self.setMinimumSize(820, 520)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._find = QLineEdit()
        self._find.setPlaceholderText("尋找")
        self._replace = QLineEdit()
        self._replace.setPlaceholderText("取代")
        self._prefix = QLineEdit()
        self._prefix.setPlaceholderText("前綴")
        self._suffix = QLineEdit()
        self._suffix.setPlaceholderText("後綴")

        apply_rule_button = QPushButton("套用規則")
        apply_rule_button.clicked.connect(self._apply_rule)
        check_changed_button = QPushButton("勾選變更")
        check_changed_button.clicked.connect(self._check_changed)
        reset_button = QPushButton("還原")
        reset_button.clicked.connect(self._load_rows)
        execute_button = QPushButton("執行更名")
        execute_button.clicked.connect(self._execute)

        controls = QHBoxLayout()
        controls.addWidget(self._find)
        controls.addWidget(self._replace)
        controls.addWidget(self._prefix)
        controls.addWidget(self._suffix)
        controls.addWidget(apply_rule_button)
        controls.addWidget(check_changed_button)
        controls.addWidget(reset_button)
        controls.addWidget(execute_button)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["套用", "原檔名", "新檔名", "狀態"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemChanged.connect(self._on_item_changed)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._context_label()))
        layout.addLayout(controls)
        layout.addWidget(self._table)

        self._apply_style()
        self._load_rows()

    def _resolve_targets(self, context: LauncherContext) -> list[Path]:
        if context.files:
            return [path for path in context.files if path.exists() and path.is_file()]
        if context.folder and context.folder.exists():
            return sorted((path for path in context.folder.iterdir() if path.is_file()), key=lambda path: path.name.lower())
        return []

    def _load_rows(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._targets))
        for row, path in enumerate(self._targets):
            apply_item = QTableWidgetItem()
            apply_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            apply_item.setCheckState(Qt.CheckState.Unchecked)
            original_item = QTableWidgetItem(path.name)
            original_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            new_item = QTableWidgetItem(path.name)
            status_item = QTableWidgetItem("")
            status_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(row, 0, apply_item)
            self._table.setItem(row, 1, original_item)
            self._table.setItem(row, 2, new_item)
            self._table.setItem(row, 3, status_item)
        self._table.blockSignals(False)
        self._refresh_statuses()

    def _apply_rule(self) -> None:
        find = self._find.text()
        replace = self._replace.text()
        prefix = self._prefix.text()
        suffix = self._suffix.text()
        self._table.blockSignals(True)
        for row, path in enumerate(self._targets):
            stem = path.stem
            if find:
                stem = stem.replace(find, replace)
            new_name = f"{prefix}{stem}{suffix}{path.suffix}"
            self._table.item(row, 2).setText(new_name)
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked if new_name != path.name else Qt.CheckState.Unchecked)
        self._table.blockSignals(False)
        self._refresh_statuses()

    def _check_changed(self) -> None:
        for row, path in enumerate(self._targets):
            new_name = self._table.item(row, 2).text().strip()
            self._table.item(row, 0).setCheckState(Qt.CheckState.Checked if new_name and new_name != path.name else Qt.CheckState.Unchecked)
        self._refresh_statuses()

    def _execute(self) -> None:
        try:
            operations = self._operations()
            if not operations:
                QMessageBox.information(self, "批次更名", "沒有勾選需要更名的列。")
                return
            _validate_operations(operations)
        except Exception as exc:
            QMessageBox.warning(self, "批次更名", str(exc))
            self._refresh_statuses()
            return

        answer = QMessageBox.question(self, "確認更名", f"確定要更名 {len(operations)} 個檔案？")
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            _apply_operations(operations)
        except Exception as exc:
            QMessageBox.critical(self, "批次更名", str(exc))
            return

        QMessageBox.information(self, "批次更名", f"已更名 {len(operations)} 個檔案。")
        renamed = {operation.source: operation.target for operation in operations}
        self._targets = [renamed.get(target, target) for target in self._targets]
        self._load_rows()

    def _operations(self) -> list[RenameOperation]:
        operations: list[RenameOperation] = []
        for row, source in enumerate(self._targets):
            apply_item = self._table.item(row, 0)
            if apply_item.checkState() != Qt.CheckState.Checked:
                continue
            new_name = self._table.item(row, 2).text().strip()
            if not new_name or new_name == source.name:
                continue
            operations.append(RenameOperation(source=source, target=source.with_name(new_name)))
        return operations

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 2:
            row = item.row()
            source = self._targets[row]
            apply_item = self._table.item(row, 0)
            apply_item.setCheckState(Qt.CheckState.Checked if item.text().strip() != source.name else Qt.CheckState.Unchecked)
        self._refresh_statuses()

    def _refresh_statuses(self) -> None:
        self._table.blockSignals(True)
        for row, source in enumerate(self._targets):
            new_name = self._table.item(row, 2).text().strip()
            status = ""
            if not source.exists():
                status = "來源不存在"
            elif not new_name:
                status = "新檔名空白"
            elif new_name == source.name:
                status = "未變更"
            elif source.with_name(new_name).exists():
                status = "目標已存在"
            else:
                status = "可更名"
            self._table.item(row, 3).setText(status)
        self._table.blockSignals(False)

    def _context_label(self) -> str:
        if self._context.files:
            return f"目前檔案：{len(self._context.files)} 個"
        if self._context.folder:
            return f"目前資料夾：{self._context.folder}"
        return "目前沒有可更名 context"

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f7f9fb;
                color: #17202a;
            }
            QLineEdit, QTableWidget {
                background: #ffffff;
                color: #17202a;
                border: 1px solid #c1ccd6;
                border-radius: 4px;
            }
            QLineEdit {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background: #d7e8f7;
                color: #17202a;
            }
            QPushButton {
                background: #ffffff;
                color: #17202a;
                border: 1px solid #aeb9c4;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background: #e5eef7;
            }
            """
        )
