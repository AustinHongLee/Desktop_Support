from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QVBoxLayout


class Card(QFrame):
    def __init__(self, parent=None, *, padding: int = 16, shadow: bool = True) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("hovered", False)
        self._shadow: QGraphicsDropShadowEffect | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(10)
        self._body = layout

        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(18)
            effect.setOffset(0, 4)
            effect.setColor(QColor(15, 23, 42, 28))
            self.setGraphicsEffect(effect)
            self._shadow = effect

    def body(self) -> QVBoxLayout:
        return self._body

    def enterEvent(self, event) -> None:  # noqa: ANN001
        self.setProperty("hovered", True)
        if self._shadow is not None:
            self._shadow.setBlurRadius(24)
            self._shadow.setOffset(0, 6)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self.setProperty("hovered", False)
        if self._shadow is not None:
            self._shadow.setBlurRadius(18)
            self._shadow.setOffset(0, 4)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)

