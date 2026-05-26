from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PyQt6.QtCore import QFileInfo, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileIconProvider,
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

from launcher.core.safe_cleanup import InstalledApplication, list_installed_applications
from launcher.ui.theme import preferences_stylesheet


class InstalledApplicationPickerDialog(QDialog):
    def __init__(self, applications: Iterable[InstalledApplication] | None = None, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("選擇本機應用程式")
        self.setMinimumSize(900, 560)
        self.setStyleSheet(preferences_stylesheet())
        self._icon_provider = QFileIconProvider()
        self._all_apps = list(applications) if applications is not None else list_installed_applications()
        self._filtered_apps: list[InstalledApplication] = []

        title = QLabel("選擇本機應用程式")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("從 Windows 解除安裝清單選取應用；工作台會優先使用 InstallLocation，其次 DisplayIcon，最後用產品名稱做殘渣掃描。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜尋名稱 / 發行者 / 版本 / 路徑")
        self._search.textChanged.connect(self._populate)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["名稱", "版本", "發行者", "分析目標", "來源"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(0, 260)
        self._table.setColumnWidth(1, 110)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, 360)
        self._table.setColumnWidth(4, 210)
        self._table.itemSelectionChanged.connect(self._refresh_buttons)
        self._table.cellDoubleClicked.connect(lambda _row, _column: self._accept_current())

        self._status = QLabel()
        self._status.setObjectName("PreferenceHint")

        reload_button = QPushButton("重新讀取")
        reload_button.clicked.connect(self.reload_applications)
        self._accept_button = QPushButton("分析選取應用")
        self._accept_button.setDefault(True)
        self._accept_button.clicked.connect(self._accept_current)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self._status, 1)
        buttons.addWidget(reload_button)
        buttons.addWidget(self._accept_button)
        buttons.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._search)
        layout.addWidget(self._table, 1)
        layout.addLayout(buttons)

        self._populate()

    def selected_application(self) -> InstalledApplication | None:
        return self._current_app()

    def reload_applications(self) -> None:
        try:
            self._all_apps = list_installed_applications()
        except Exception as exc:
            QMessageBox.warning(self, "選擇本機應用程式", f"讀取應用程式清單失敗：\n{exc}")
            return
        self._populate()

    def _populate(self) -> None:
        needle = self._search.text().strip().casefold()
        self._filtered_apps = [app for app in self._all_apps if _matches_app(app, needle)]
        self._table.setRowCount(0)
        for row, app in enumerate(self._filtered_apps):
            self._table.insertRow(row)
            for column, text in enumerate(
                (
                    app.display_name,
                    app.display_version,
                    app.publisher,
                    app.analysis_target,
                    f"{app.root_name}\\{app.registry_key}",
                )
            ):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                item.setData(Qt.ItemDataRole.UserRole, row)
                if column == 0:
                    icon_path = _icon_source_for_app(app)
                    if icon_path:
                        item.setIcon(self._icon_provider.icon(QFileInfo(icon_path)))
                self._table.setItem(row, column, item)
        if self._filtered_apps:
            self._table.selectRow(0)
        self._status.setText(f"共 {len(self._all_apps)} 個應用；目前顯示 {len(self._filtered_apps)} 個。")
        self._refresh_buttons()

    def _current_app(self) -> InstalledApplication | None:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        row = rows[0].row() if rows else self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or index < 0 or index >= len(self._filtered_apps):
            return None
        return self._filtered_apps[index]

    def _accept_current(self) -> None:
        if self._current_app() is None:
            QMessageBox.information(self, "選擇本機應用程式", "請先選擇一個應用程式。")
            return
        self.accept()

    def _refresh_buttons(self) -> None:
        self._accept_button.setEnabled(self._current_app() is not None)


def _matches_app(app: InstalledApplication, needle: str) -> bool:
    if not needle:
        return True
    fields = (
        app.display_name,
        app.display_version,
        app.publisher,
        app.install_location,
        app.display_icon,
        app.uninstall_command,
        app.registry_key,
    )
    return any(needle in field.casefold() for field in fields if field)


def _icon_source_for_app(app: InstalledApplication) -> str:
    for value in (app.display_icon, app.install_location, app.analysis_target):
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return str(path)
    return ""
