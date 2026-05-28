from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER


def layer_label(layer: str) -> str:
    labels = {
        SAFE_LAYER: "安全可清",
        PROCESS_LAYER: "執行中",
        REVIEW_LAYER: "需確認",
        REGISTRY_LAYER: "HKCU 登錄檔",
        BLOCKED_LAYER: "系統層",
    }
    return labels.get(layer, layer)


class RiskBadge(QLabel):
    def __init__(self, *, layer: str, text: str | None = None, parent=None) -> None:  # noqa: ANN001
        super().__init__(text or layer_label(layer), parent)
        self.setProperty("layer", layer)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

