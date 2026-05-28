from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel

from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.risk_badge import RiskBadge, layer_label


class StatCard(Card):
    clicked = pyqtSignal(str)

    def __init__(self, *, title: str, layer: str, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent, padding=12)
        self._layer = layer

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        text_layout = self.body()
        self._title = QLabel(title)
        self._title.setObjectName("Muted")
        self._value = QLabel("0")
        self._value.setObjectName("H1")
        self._sub = QLabel("")
        self._sub.setObjectName("Muted")
        self._sub.setWordWrap(True)

        text_layout.addWidget(self._title)
        text_layout.addWidget(self._value)
        text_layout.addWidget(self._sub)

        self._badge = RiskBadge(layer=layer, text=layer_label(layer))
        row.addStretch(1)
        row.addWidget(self._badge)
        self.body().insertLayout(0, row)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_value(self, value: int | str, subtext: str = "") -> None:
        self._value.setText(str(value))
        self._sub.setText(subtext)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        self.clicked.emit(self._layer)
        super().mousePressEvent(event)
