from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from launcher.core.registry import ActionRegistry, PluginDefinition, RegistryLoadReport
from launcher.ui.theme import preferences_stylesheet


class PluginManagerDialog(QDialog):
    def __init__(self, registry: ActionRegistry, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._registry = registry

        self.setWindowTitle("外掛管理")
        self.setMinimumSize(720, 460)

        self._summary = QLabel()
        self._summary.setObjectName("PreferenceHint")
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Plugin", "名稱", "指令數", "路徑"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self._issues = QPlainTextEdit()
        self._issues.setReadOnly(True)
        self._issues.setPlaceholderText("目前沒有外掛載入錯誤")

        self._reload_button = QPushButton("重新載入")
        self._reload_button.clicked.connect(self.reload_plugins)
        self._open_folder_button = QPushButton("開啟外掛資料夾")
        self._open_folder_button.clicked.connect(self._open_plugin_root)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.addWidget(self._reload_button)
        actions.addWidget(self._open_folder_button)
        actions.addStretch(1)
        actions.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._summary)
        layout.addWidget(self._table, 2)
        layout.addWidget(QLabel("載入問題"))
        layout.addWidget(self._issues, 1)
        layout.addLayout(actions)

        self.setStyleSheet(preferences_stylesheet())
        self.refresh()

    def reload_plugins(self) -> None:
        self._registry.reload()
        self.refresh()

    def refresh(self) -> None:
        report = self._registry.last_report
        self._summary.setText(_summary_text(report))
        self._populate_plugins()
        self._populate_issues(report)

    def _populate_plugins(self) -> None:
        plugins = sorted(self._registry.plugins.values(), key=lambda plugin: plugin.id)
        self._table.setRowCount(len(plugins))
        for row, plugin in enumerate(plugins):
            action_count = _action_count_for_plugin(self._registry, plugin)
            values = [plugin.id, plugin.title, str(action_count), str(plugin.path)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self._table.setItem(row, column, item)

    def _populate_issues(self, report: RegistryLoadReport) -> None:
        if not report.issues:
            self._issues.clear()
            return
        self._issues.setPlainText(
            "\n".join(f"{issue.path}\n  {issue.message}" for issue in report.issues)
        )

    def _open_plugin_root(self) -> None:
        self._registry.plugin_root.mkdir(parents=True, exist_ok=True)
        os.startfile(self._registry.plugin_root)  # noqa: S606


def _summary_text(report: RegistryLoadReport) -> str:
    if report.ok:
        return f"已載入 {report.plugin_count} 個外掛，{report.action_count} 個指令。"
    return f"已載入 {report.plugin_count} 個外掛，{report.action_count} 個指令；有 {len(report.issues)} 個載入問題。"


def _action_count_for_plugin(registry: ActionRegistry, plugin: PluginDefinition) -> int:
    return sum(1 for action in registry.actions.values() if action.plugin_id == plugin.id)
