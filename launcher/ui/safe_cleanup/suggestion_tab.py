from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QSplitter, QVBoxLayout, QWidget, QLabel

from launcher.core.safe_cleanup import (
    BLOCKED_LAYER,
    PROCESS_LAYER,
    REGISTRY_LAYER,
    REVIEW_LAYER,
    SAFE_LAYER,
    CleanupPlan,
    CleanupPlanItem,
    ItemImpact,
    compute_impact,
)
from launcher.ui.safe_cleanup.detail_panel import DetailPanel
from launcher.ui.safe_cleanup.filter_sidebar import FilterSidebar
from launcher.ui.safe_cleanup.item_card import ItemCard
from launcher.ui.safe_cleanup.layer_language import language_for_layer

_LAYERS = (SAFE_LAYER, REVIEW_LAYER, PROCESS_LAYER, REGISTRY_LAYER, BLOCKED_LAYER)


class SuggestionTab(QWidget):
    selection_changed = pyqtSignal(object)
    locate_requested = pyqtSignal(object)
    copy_requested = pyqtSignal(object)

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._plan: CleanupPlan | None = None
        self._item_cards: dict[str, ItemCard] = {}
        self._item_by_id: dict[str, CleanupPlanItem] = {}
        self._impact_by_id: dict[str, ItemImpact] = {}
        self._section_labels: dict[str, QLabel] = {}
        self._selected_item_id: str | None = None
        self._applying = False
        self._scanning = False

        self._sidebar = FilterSidebar()
        self._sidebar.filter_changed.connect(self._apply_filter)
        self._sidebar.unlock_toggled.connect(self._set_layer_unlocked)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setWidget(self._list_widget)

        self._detail = DetailPanel()
        self._detail.locate_requested.connect(self.locate_requested)
        self._detail.copy_requested.connect(self.copy_requested)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._sidebar)
        splitter.addWidget(self._scroll)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([230, 610, 360])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter, 1)

    @property
    def detail_text_edit(self):
        return self._detail.text_edit

    def set_plan(self, plan: CleanupPlan) -> None:
        self._plan = plan
        self._selected_item_id = None
        self._item_by_id = {item.id: item for item in plan.items}
        self._impact_by_id = _precompute_impacts(plan)
        self._clear_cards()
        self._sidebar.set_layer_counts({layer: plan.count_by_layer(layer) for layer in _LAYERS})
        for layer in _LAYERS:
            layer_items = [item for item in plan.items if item.layer == layer]
            if not layer_items:
                continue
            language = language_for_layer(layer)
            header = QLabel(f"{language.title} ({len(layer_items)})")
            header.setObjectName("SectionHeader")
            self._section_labels[layer] = header
            self._list_layout.addWidget(header)
            for item in layer_items:
                card = ItemCard()
                card.set_item(item, self._impact_by_id[item.id])
                card.set_unlocked(self._sidebar.is_unlocked(item.layer))
                card.set_checked(_initial_checked(item))
                card.clicked.connect(self._select_item)
                card.toggled.connect(lambda _item_id, _checked: None)
                card.locate_requested.connect(self.locate_requested)
                self._item_cards[item.id] = card
                self._list_layout.addWidget(card)
        self._list_layout.addStretch(1)
        self._apply_filter(self._sidebar.current_filter())
        first = next(iter(self._item_cards.values()), None)
        if first is not None and first.item() is not None:
            self._select_item(first.item())
        else:
            self._detail.clear()
        self.set_scanning(self._scanning)
        self.set_applying(self._applying)

    def set_scanning(self, active: bool) -> None:
        self._scanning = active
        self._sidebar.set_enabled_for_activity(not active and not self._applying)
        for card in self._item_cards.values():
            card.setEnabled(not active and not self._applying)
        if active:
            self._detail.set_status_text("分析中；大型資料夾或登錄檔候選較多時，視窗仍可移動與關閉。")

    def set_applying(self, active: bool) -> None:
        self._applying = active
        self._sidebar.set_enabled_for_activity(not active and not self._scanning)
        for card in self._item_cards.values():
            card.setEnabled(not active and not self._scanning)

    def selected_item_ids(self) -> set[str]:
        return {item_id for item_id, card in self._item_cards.items() if card.is_checked()}

    def plan_items(self) -> dict[str, CleanupPlanItem]:
        return dict(self._item_by_id)

    def current_item(self) -> CleanupPlanItem | None:
        if self._selected_item_id is None:
            return None
        return self._item_by_id.get(self._selected_item_id)

    def focus_layer(self, layer: str) -> None:
        self._sidebar.set_filter(layer)
        for item in self._item_by_id.values():
            if item.layer == layer:
                self._select_item(item)
                card = self._item_cards.get(item.id)
                if card is not None:
                    self._scroll.ensureWidgetVisible(card)
                return

    def set_status_text(self, text: str) -> None:
        self._detail.set_status_text(text)

    def _select_item(self, item: CleanupPlanItem) -> None:
        self._selected_item_id = item.id
        for item_id, card in self._item_cards.items():
            card.set_selected(item_id == item.id)
        self._detail.set_item(item, self._impact_by_id.get(item.id))
        self.selection_changed.emit(item)

    def _apply_filter(self, layer: str) -> None:
        for item_id, card in self._item_cards.items():
            item = self._item_by_id[item_id]
            visible = layer == "all" or item.layer == layer
            card.setVisible(visible)
        for section_layer, label in self._section_labels.items():
            label.setVisible(layer == "all" or section_layer == layer)

    def _set_layer_unlocked(self, layer: str, unlocked: bool) -> None:
        for item_id, card in self._item_cards.items():
            item = self._item_by_id[item_id]
            if item.layer == layer:
                card.set_unlocked(unlocked)

    def _clear_cards(self) -> None:
        while self._list_layout.count():
            entry = self._list_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
        self._item_cards = {}
        self._section_labels = {}


def _initial_checked(item: CleanupPlanItem) -> bool:
    if item.layer in {REVIEW_LAYER, PROCESS_LAYER, REGISTRY_LAYER, BLOCKED_LAYER}:
        return False
    return item.checked_default and item.executable


def _precompute_impacts(plan: CleanupPlan) -> dict[str, ItemImpact]:
    return {item.id: compute_impact(plan, item) for item in plan.items}
