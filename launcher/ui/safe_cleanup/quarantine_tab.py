from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from launcher.ui.components.card import Card


class QuarantineTab(QWidget):
    open_browser_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        card = Card(padding=18)
        title = QLabel("隔離區")
        title.setObjectName("H1")
        hint = QLabel("這裡會管理安全清除搬走的檔案與登錄檔備份。完整瀏覽器沿用既有隔離區管理視窗。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        button = QPushButton("管理隔離區")
        button.setObjectName("Primary")
        button.clicked.connect(self.open_browser_requested)
        card.body().addWidget(title)
        card.body().addWidget(hint)
        card.body().addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        layout.addStretch(1)

