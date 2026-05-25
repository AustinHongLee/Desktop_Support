from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout

from launcher.ui.theme import preferences_stylesheet
from launcher.windows.context_menu_registry import context_menu_status, install_context_menu, status_lines, uninstall_context_menu


class ExplorerContextMenuDialog(QDialog):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("右鍵選單管理")
        self.setMinimumSize(720, 460)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("Explorer 右鍵選單")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("管理「送到工程工具列」右鍵入口。此功能寫入 HKCU，不需要系統管理員權限。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._summary = QLabel("尚未檢查")
        self._summary.setObjectName("PreferenceHint")
        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(230)

        refresh_button = QPushButton("重新檢查")
        refresh_button.clicked.connect(self.refresh_status)
        install_button = QPushButton("安裝 / 更新")
        install_button.setDefault(True)
        install_button.clicked.connect(self.install_or_update)
        remove_button = QPushButton("移除右鍵")
        remove_button.clicked.connect(self.remove_context_menu)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh_button)
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
        layout.addWidget(self._detail, 1)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())
        self.refresh_status()

    def refresh_status(self) -> None:
        try:
            status = context_menu_status()
        except Exception as exc:
            self._summary.setText("狀態：檢查失敗")
            self._detail.setPlainText(str(exc))
            return
        self._summary.setText(f"狀態：{status.summary}")
        self._detail.setPlainText("\n".join(status_lines(status)))

    def install_or_update(self) -> None:
        try:
            status = install_context_menu()
        except Exception as exc:
            QMessageBox.critical(self, "右鍵選單管理", str(exc))
            self.refresh_status()
            return
        self._summary.setText(f"狀態：{status.summary}")
        self._detail.setPlainText("[完成] 已安裝 / 更新 Explorer 右鍵選單。\n\n" + "\n".join(status_lines(status)))

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
            QMessageBox.critical(self, "右鍵選單管理", str(exc))
            self.refresh_status()
            return
        self._summary.setText(f"狀態：{status.summary}")
        self._detail.setPlainText("[完成] 已移除 Explorer 右鍵選單。\n\n" + "\n".join(status_lines(status)))
