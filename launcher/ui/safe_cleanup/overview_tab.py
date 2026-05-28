from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER, CleanupPlan
from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.one_click_dialogs import default_one_click_ids
from launcher.ui.safe_cleanup.stat_card import StatCard


class OverviewTab(QWidget):
    layer_selected = pyqtSignal(str)
    one_click_requested = pyqtSignal()
    run_uninstaller_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._cards: dict[str, StatCard] = {}

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        specs = (
            (SAFE_LAYER, "安全可清"),
            (PROCESS_LAYER, "執行中 / 佔用"),
            (REVIEW_LAYER, "需要人工確認"),
            (REGISTRY_LAYER, "登錄檔 HKCU"),
            (BLOCKED_LAYER, "系統層待管理員"),
            ("uninstaller", "官方解除安裝"),
        )
        for index, (layer, title) in enumerate(specs):
            card_layer = layer if layer != "uninstaller" else PROCESS_LAYER
            card = StatCard(title=title, layer=card_layer)
            card.clicked.connect(lambda _layer, target=layer: self.layer_selected.emit(target))
            self._cards[layer] = card
            grid.addWidget(card, index // 3, index % 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        content_layout.addLayout(grid)

        self._uninstaller_banner = Card(padding=12)
        banner_row = QHBoxLayout()
        banner_row.setContentsMargins(0, 0, 0, 0)
        banner_row.setSpacing(10)
        self._uninstaller_label = QLabel()
        self._uninstaller_label.setObjectName("H2")
        self._uninstaller_label.setWordWrap(True)
        self._uninstaller_button = QPushButton("執行官方解除安裝")
        self._uninstaller_button.setObjectName("Ghost")
        self._uninstaller_button.clicked.connect(self.run_uninstaller_requested)
        banner_row.addWidget(self._uninstaller_label, 1)
        banner_row.addWidget(self._uninstaller_button)
        self._uninstaller_banner.body().addLayout(banner_row)
        self._uninstaller_banner.hide()
        content_layout.addWidget(self._uninstaller_banner)

        cta = Card(padding=12)
        cta_row = QHBoxLayout()
        cta_row.setContentsMargins(0, 0, 0, 0)
        cta_row.setSpacing(12)
        cta_text = QLabel("預設只會隔離安全層與需確認層，不會碰 HKCU 登錄檔、執行中程序或系統層。")
        cta_text.setObjectName("Muted")
        cta_text.setWordWrap(True)
        self._one_click_button = QPushButton("一鍵安全清除")
        self._one_click_button.setObjectName("Primary")
        self._one_click_button.clicked.connect(self.one_click_requested)
        cta_row.addWidget(cta_text, 1)
        cta_row.addWidget(self._one_click_button)
        cta.body().addLayout(cta_row)
        content_layout.addWidget(cta)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def set_plan(self, plan: CleanupPlan) -> None:
        self._cards[SAFE_LAYER].set_value(plan.count_by_layer(SAFE_LAYER), f"估計可釋出 {_format_size(_layer_size(plan, SAFE_LAYER))}")
        self._cards[PROCESS_LAYER].set_value(plan.count_by_layer(PROCESS_LAYER), "需手動關閉或明確允許")
        self._cards[REVIEW_LAYER].set_value(plan.count_by_layer(REVIEW_LAYER), "資料夾與衍生檔需人工確認")
        self._cards[REGISTRY_LAYER].set_value(plan.count_by_layer(REGISTRY_LAYER), "不進一鍵流程")
        self._cards[BLOCKED_LAYER].set_value(plan.count_by_layer(BLOCKED_LAYER), "需另外啟動管理員深度清理")
        self._cards["uninstaller"].set_value(len(plan.official_uninstallers), "建議先跑官方解除安裝")

        primary = _primary_uninstaller(plan)
        if primary is not None:
            confidence = int(primary.confidence * 100)
            self._uninstaller_label.setText(f"建議優先動作：{primary.display_name}｜信心 {confidence}%")
            self._uninstaller_banner.show()
        else:
            self._uninstaller_banner.hide()
        self._one_click_button.setEnabled(bool(default_one_click_ids(plan)))

    def set_scanning(self, active: bool) -> None:
        self._one_click_button.setEnabled(not active)
        if active:
            for card in self._cards.values():
                card.set_value("...", "分析中")

    @property
    def uninstaller_banner(self) -> Card:
        return self._uninstaller_banner

    @property
    def uninstaller_label(self) -> QLabel:
        return self._uninstaller_label

    @property
    def uninstaller_button(self) -> QPushButton:
        return self._uninstaller_button

    @property
    def one_click_button(self) -> QPushButton:
        return self._one_click_button


def _layer_size(plan: CleanupPlan, layer: str) -> int:
    return sum(item.size_bytes for item in plan.items if item.layer == layer)


def _primary_uninstaller(plan: CleanupPlan):
    for uninstaller in plan.official_uninstallers:
        if not uninstaller.is_fork_relative and uninstaller.confidence >= 0.6:
            return uninstaller
    return None


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
