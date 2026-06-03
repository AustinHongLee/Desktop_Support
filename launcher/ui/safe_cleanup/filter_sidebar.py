from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QButtonGroup, QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER
from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.layer_language import SAFETY_GUARANTEE_TEXT, language_for_layer

_FILTERS = ("all", SAFE_LAYER, REVIEW_LAYER, PROCESS_LAYER, REGISTRY_LAYER, BLOCKED_LAYER)
_UNLOCKABLE = {PROCESS_LAYER, REGISTRY_LAYER}


class FilterSidebar(QWidget):
    filter_changed = pyqtSignal(str)
    unlock_toggled = pyqtSignal(str, bool)

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._current_filter = "all"
        self._buttons: dict[str, QPushButton] = {}
        self._counts: dict[str, int] = {key: 0 for key in _FILTERS}
        self._unlock_checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        filter_card = Card(padding=12, shadow=False)
        title = QLabel("篩選")
        title.setObjectName("H2")
        filter_card.body().addWidget(title)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        for key in _FILTERS:
            button = QPushButton()
            button.setObjectName("FilterButton")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, target=key: self._set_filter(target))
            self._button_group.addButton(button)
            self._buttons[key] = button
            filter_card.body().addWidget(button)
        self._buttons["all"].setChecked(True)
        layout.addWidget(filter_card)

        safety_card = Card(padding=12, shadow=False)
        safety_title = QLabel("安全保證")
        safety_title.setObjectName("H2")
        safety_text = QLabel(SAFETY_GUARANTEE_TEXT)
        safety_text.setObjectName("Muted")
        safety_text.setWordWrap(True)
        safety_card.body().addWidget(safety_title)
        safety_card.body().addWidget(safety_text)
        layout.addWidget(safety_card)

        unlock_card = Card(padding=12, shadow=False)
        unlock_title = QLabel("進階允許")
        unlock_title.setObjectName("H2")
        unlock_hint = QLabel("開啟後只代表可以手動勾選；套用前仍會再次確認。")
        unlock_hint.setObjectName("Muted")
        unlock_hint.setWordWrap(True)
        unlock_card.body().addWidget(unlock_title)
        unlock_card.body().addWidget(unlock_hint)
        for layer in (PROCESS_LAYER, REGISTRY_LAYER):
            checkbox = QCheckBox(_unlock_label(layer))
            checkbox.setToolTip(language_for_layer(layer).tooltip)
            checkbox.stateChanged.connect(lambda _state, target=layer, control=checkbox: self.unlock_toggled.emit(target, control.isChecked()))
            self._unlock_checks[layer] = checkbox
            unlock_card.body().addWidget(checkbox)
        layout.addWidget(unlock_card)
        layout.addStretch(1)
        self._refresh_labels()

    def set_layer_counts(self, counts: dict[str, int]) -> None:
        self._counts = {key: int(counts.get(key, 0)) for key in _FILTERS}
        self._counts["all"] = sum(self._counts.get(layer, 0) for layer in (SAFE_LAYER, REVIEW_LAYER, PROCESS_LAYER, REGISTRY_LAYER, BLOCKED_LAYER))
        self._refresh_labels()

    def current_filter(self) -> str:
        return self._current_filter

    def set_filter(self, target: str) -> None:
        self._set_filter(target)

    def is_unlocked(self, layer: str) -> bool:
        checkbox = self._unlock_checks.get(layer)
        return bool(checkbox and checkbox.isChecked())

    def unlocked_layers(self) -> set[str]:
        return {layer for layer, checkbox in self._unlock_checks.items() if checkbox.isChecked()}

    def set_enabled_for_activity(self, enabled: bool) -> None:
        for button in self._buttons.values():
            button.setEnabled(enabled)
        for checkbox in self._unlock_checks.values():
            checkbox.setEnabled(enabled)

    def _set_filter(self, target: str) -> None:
        self._current_filter = target
        self._buttons[target].setChecked(True)
        self.filter_changed.emit(target)

    def _refresh_labels(self) -> None:
        self._buttons["all"].setText(f"全部 ({self._counts.get('all', 0)})")
        for layer in (SAFE_LAYER, REVIEW_LAYER, PROCESS_LAYER, REGISTRY_LAYER, BLOCKED_LAYER):
            language = language_for_layer(layer)
            self._buttons[layer].setText(f"{language.title} ({self._counts.get(layer, 0)})")


def _unlock_label(layer: str) -> str:
    if layer == PROCESS_LAYER:
        return "允許嘗試關閉程序"
    if layer == REGISTRY_LAYER:
        return "允許設定殘留清理"
    return f"允許 {language_for_layer(layer).title}"
