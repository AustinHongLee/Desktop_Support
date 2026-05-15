from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from launcher.plugins.iso_tools.rename_plan import RenamePlan, RenamePlanRow
from launcher.ui.theme import preferences_stylesheet


class RenamePlanDialog(QDialog):
    def __init__(self, plan: RenamePlan, parent=None, *, default_export_path: Path | None = None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._plan = plan
        self._default_export_path = default_export_path or self._infer_default_export_path(plan)

        self.setWindowTitle("更名前確認")
        self.setMinimumSize(840, 540)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._summary = QLabel(self._summary_text())
        self._summary.setObjectName("PreferenceHint")

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["套用", "原檔名", "新檔名", "狀態", "備註"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._load_rows()

        export_button = QPushButton("匯出 CSV")
        export_button.clicked.connect(self._export_csv)

        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)

        confirm_button = QPushButton("確認更名")
        confirm_button.setDefault(True)
        confirm_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(export_button)
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(confirm_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("請確認下列檔名變更。這一步還沒有寫入檔案。"))
        layout.addWidget(self._summary)
        layout.addWidget(self._table)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())

    def write_csv(self, path: Path) -> None:
        self._plan.write_csv(path)

    def _load_rows(self) -> None:
        self._table.setRowCount(len(self._plan.rows))
        for index, row in enumerate(self._plan.rows):
            values = [
                "YES" if row.apply else "",
                row.source.name,
                row.target.name,
                self._display_status(row),
                row.note,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if column == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(index, column, item)
        self._table.resizeRowsToContents()

    def _summary_text(self) -> str:
        warning_text = f"，警示 {self._plan.warning_count} 筆" if self._plan.warning_count else ""
        return f"預計更名 {self._plan.operation_count} 個 PDF{warning_text}。可先匯出 CSV 留底或交叉檢查。"

    def _export_csv(self) -> None:
        file_name, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "匯出更名計畫",
            str(self._default_export_path),
            "CSV 檔案 (*.csv)",
        )
        if not file_name:
            return
        path = Path(file_name)
        try:
            self.write_csv(path)
        except Exception as exc:
            QMessageBox.warning(self, "匯出 CSV", str(exc))
            return
        QMessageBox.information(self, "匯出 CSV", f"已匯出：{path}")

    @staticmethod
    def _infer_default_export_path(plan: RenamePlan) -> Path:
        if plan.rows:
            return plan.rows[0].source.parent / "iso_rename_plan.csv"
        return Path.cwd() / "iso_rename_plan.csv"

    @staticmethod
    def _display_status(row: RenamePlanRow) -> str:
        if row.status == "ready":
            return "將更名"
        if row.status == "warning":
            return "需留意"
        return row.status
