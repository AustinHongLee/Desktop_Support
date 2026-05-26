from __future__ import annotations

from dataclasses import dataclass
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from launcher.core.safe_cleanup import CleanupPlanItem
from launcher.ui.theme import preferences_stylesheet

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only integration.
    winreg = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RegistryValueSnapshot:
    name: str
    type_name: str
    data: str


class RegistrySourceDialog(QDialog):
    def __init__(self, item: CleanupPlanItem, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._item = item
        self._values: tuple[RegistryValueSnapshot, ...] = ()
        self.setWindowTitle("登錄檔來源檢視")
        self.setMinimumSize(920, 560)
        self.setStyleSheet(preferences_stylesheet())

        title = QLabel("登錄檔來源檢視")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("直接讀取這個 key 目前的所有值；高亮列是清除建議命中的 value。這裡只檢視與複製，不刪除。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._key_label = QLabel(_registry_path_text(item.root_name, item.registry_key))
        self._key_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._value_label = QLabel(f"命中值：{item.registry_value_name or '(Default)'}")
        self._value_label.setObjectName("PreferenceHint")
        self._value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["值名稱", "型別", "資料"])
        self._table.setAlternatingRowColors(True)
        self._table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(0, 260)
        self._table.setColumnWidth(1, 110)
        self._table.setColumnWidth(2, 620)

        copy_key_button = QPushButton("複製 Key")
        copy_key_button.clicked.connect(self.copy_key)
        copy_value_button = QPushButton("複製命中值")
        copy_value_button.clicked.connect(self.copy_matched_value)
        open_regedit_button = QPushButton("外部開啟 Regedit")
        open_regedit_button.clicked.connect(self.open_regedit)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(copy_key_button)
        buttons.addWidget(copy_value_button)
        buttons.addWidget(open_regedit_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._key_label)
        layout.addWidget(self._value_label)
        layout.addWidget(self._table, 1)
        layout.addLayout(buttons)

        self.reload()

    def reload(self) -> None:
        try:
            self._values = tuple(read_registry_values(self._item.root_name, self._item.registry_key))
        except Exception as exc:
            self._table.setRowCount(0)
            QMessageBox.warning(self, "登錄檔來源檢視", f"讀取登錄檔失敗：\n{exc}")
            return
        self._populate()

    def copy_key(self) -> None:
        QApplication.clipboard().setText(_registry_path_text(self._item.root_name, self._item.registry_key))

    def copy_matched_value(self) -> None:
        value = next((item for item in self._values if item.name == self._item.registry_value_name), None)
        if value is None:
            QApplication.clipboard().setText(self._item.registry_value_data)
            return
        QApplication.clipboard().setText(f"{value.name or '(Default)'} = {value.data}")

    def open_regedit(self) -> None:
        try:
            open_registry_location(self._item.root_name, self._item.registry_key)
        except Exception as exc:
            QMessageBox.warning(self, "登錄檔來源檢視", f"無法開啟 Regedit：\n{exc}")

    def _populate(self) -> None:
        self._table.setRowCount(0)
        selected_row = -1
        for row, value in enumerate(self._values):
            self._table.insertRow(row)
            for column, text in enumerate((value.name or "(Default)", value.type_name, value.data)):
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self._table.setItem(row, column, cell)
            if value.name == self._item.registry_value_name:
                selected_row = row
                for column in range(3):
                    self._table.item(row, column).setForeground(QBrush(QColor("#7c2d12")))
                    self._table.item(row, column).setBackground(QBrush(QColor("#fff3d6")))
        if selected_row >= 0:
            self._table.selectRow(selected_row)
            self._table.scrollToItem(self._table.item(selected_row, 0))


def read_registry_values(root_name: str, key_path: str) -> list[RegistryValueSnapshot]:
    if sys.platform != "win32" or winreg is None:
        raise RuntimeError("目前只支援 Windows 登錄檔讀取。")
    root = _root_handle(root_name)
    if root is None or not key_path:
        raise ValueError(f"不支援的登錄檔根目錄：{root_name}")
    values: list[RegistryValueSnapshot] = []
    with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | _registry_view_flag()) as key:
        index = 0
        while True:
            try:
                name, data, value_type = winreg.EnumValue(key, index)
            except OSError:
                break
            values.append(RegistryValueSnapshot(name=str(name), type_name=_registry_type_name(value_type), data=_registry_data_text(data)))
            index += 1
    return values


def open_registry_location(root_name: str, registry_key: str) -> None:
    if sys.platform != "win32" or winreg is None:
        raise RuntimeError("目前只支援 Windows Regedit 定位。")
    root = _regedit_root_name(root_name)
    if not root or not registry_key:
        raise ValueError(f"不支援的登錄檔根目錄：{root_name}")
    last_key = rf"Computer\{root}\{registry_key}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Applets\Regedit") as key:
        winreg.SetValueEx(key, "LastKey", 0, winreg.REG_SZ, last_key)
    if not hasattr(os, "startfile"):
        raise RuntimeError("目前平台不支援 ShellExecute 啟動 Regedit。")
    os.startfile("regedit.exe", "open", "/m")  # type: ignore[attr-defined]  # noqa: S606 - local desktop action via ShellExecute.


def _registry_path_text(root_name: str, key_path: str) -> str:
    root = _regedit_root_name(root_name) or root_name
    return rf"{root}\{key_path}"


def _root_handle(root_name: str):  # noqa: ANN201
    roots = {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
        "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    }
    return roots.get(root_name.strip().upper())


def _regedit_root_name(root_name: str) -> str:
    roots = {
        "HKCU": "HKEY_CURRENT_USER",
        "HKEY_CURRENT_USER": "HKEY_CURRENT_USER",
        "HKLM": "HKEY_LOCAL_MACHINE",
        "HKEY_LOCAL_MACHINE": "HKEY_LOCAL_MACHINE",
    }
    return roots.get(root_name.strip().upper(), "")


def _registry_view_flag() -> int:
    return getattr(winreg, "KEY_WOW64_64KEY", 0)


def _registry_type_name(value_type: int) -> str:
    names = {
        getattr(winreg, "REG_SZ", 1): "REG_SZ",
        getattr(winreg, "REG_EXPAND_SZ", 2): "REG_EXPAND_SZ",
        getattr(winreg, "REG_BINARY", 3): "REG_BINARY",
        getattr(winreg, "REG_DWORD", 4): "REG_DWORD",
        getattr(winreg, "REG_MULTI_SZ", 7): "REG_MULTI_SZ",
        getattr(winreg, "REG_QWORD", 11): "REG_QWORD",
    }
    return names.get(value_type, f"REG_{value_type}")


def _registry_data_text(data: object) -> str:
    if isinstance(data, bytes):
        return data.hex(" ")
    if isinstance(data, (list, tuple)):
        return "\n".join(str(item) for item in data)
    return str(data)
