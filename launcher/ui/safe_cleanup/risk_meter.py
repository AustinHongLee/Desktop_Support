from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER, CleanupPlan

_LAYERS = (SAFE_LAYER, PROCESS_LAYER, REVIEW_LAYER, REGISTRY_LAYER, BLOCKED_LAYER)
_COLORS = {
    SAFE_LAYER: "#10b981",
    PROCESS_LAYER: "#0ea5e9",
    REVIEW_LAYER: "#f59e0b",
    REGISTRY_LAYER: "#f43f5e",
    BLOCKED_LAYER: "#94a3b8",
}
_LABELS = {
    SAFE_LAYER: "綠",
    PROCESS_LAYER: "藍",
    REVIEW_LAYER: "橘",
    REGISTRY_LAYER: "紅",
    BLOCKED_LAYER: "灰",
}


class RiskMeter(QWidget):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._counts = {layer: 0 for layer in _LAYERS}
        self.setMinimumHeight(34)

    def set_plan(self, plan: CleanupPlan | None) -> None:
        if plan is None:
            self._counts = {layer: 0 for layer in _LAYERS}
        else:
            self._counts = {layer: plan.count_by_layer(layer) for layer in _LAYERS}
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(260, 38)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total = sum(self._counts.values())
        margin = 1
        bar_height = 8
        bar_y = 2
        width = max(1, self.width() - margin * 2)
        radius = bar_height / 2
        bar_rect = self.rect().adjusted(margin, bar_y, -margin, -(self.height() - bar_y - bar_height))
        path = QPainterPath()
        path.addRoundedRect(bar_rect.toRectF(), radius, radius)
        painter.fillPath(path, QColor("#e5e7eb"))

        if total:
            x = float(bar_rect.left())
            painter.setClipPath(path)
            remaining = float(width)
            for index, layer in enumerate(_LAYERS):
                count = self._counts[layer]
                if count <= 0:
                    continue
                if index == len(_LAYERS) - 1:
                    segment_width = remaining
                else:
                    segment_width = max(1.0, width * count / total)
                    remaining -= segment_width
                painter.fillRect(int(x), bar_rect.top(), int(segment_width + 0.5), bar_height, QColor(_COLORS[layer]))
                x += segment_width
            painter.setClipping(False)

        painter.setPen(QPen(QColor("#64748b")))
        painter.setFont(self.font())
        if not total:
            text = "尚未分析"
        else:
            parts = [f"{_LABELS[layer]} {self._counts[layer]}" for layer in _LAYERS]
            text = "｜".join(parts) + f"｜總計 {total} 項"
        painter.drawText(0, bar_y + bar_height + 4, self.width(), self.height() - bar_height - 4, Qt.AlignmentFlag.AlignLeft, text)

