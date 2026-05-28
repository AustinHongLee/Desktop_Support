from __future__ import annotations

from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget


class ActivityLogTab(QWidget):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._log)

    def append_message(self, message: str) -> None:
        self._log.appendPlainText(message)

    def set_text(self, text: str) -> None:
        self._log.setPlainText(text)

    def text(self) -> str:
        return self._log.toPlainText()

