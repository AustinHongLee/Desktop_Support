from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, CleanupPlan, evidence_summary
from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.layer_language import language_for_layer

_RISK_LAYERS = {PROCESS_LAYER, REGISTRY_LAYER}


class RiskActionConfirmDialog(QDialog):
    def __init__(self, plan: CleanupPlan, selected_ids: set[str], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("確認進階清理")
        self.setMinimumWidth(620)
        self._selected_ids = {item.id for item in plan.items if item.id in selected_ids and item.layer != BLOCKED_LAYER}
        selected = [item for item in plan.items if item.id in selected_ids and item.layer in _RISK_LAYERS]
        registry_count = sum(1 for item in selected if item.layer == REGISTRY_LAYER)
        process_count = sum(1 for item in selected if item.layer == PROCESS_LAYER)
        self._requires_ack = registry_count > 0

        title = QLabel("即將處理進階項目")
        title.setObjectName("H1")
        summary = QLabel(f"本次包含設定殘留 {registry_count} 項、執行中程序 {process_count} 項。請確認這些項目確實要處理。")
        summary.setObjectName("Muted")
        summary.setWordWrap(True)

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(8)
        for item in selected:
            language = language_for_layer(item.layer)
            card = Card(padding=10, shadow=False)
            label = QLabel(f"{language.title}｜{item.label}")
            label.setObjectName("H2")
            note = QLabel(f"{item.action}\n{item.note}\n證據：{evidence_summary(item)}")
            note.setObjectName("Muted")
            note.setWordWrap(True)
            card.body().addWidget(label)
            card.body().addWidget(note)
            list_layout.addWidget(card)
        list_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setMinimumHeight(220)
        scroll.setWidget(list_widget)

        self._understand = QCheckBox("我了解設定殘留可能影響軟體行為、檔案關聯、授權狀態或重新安裝判斷。")
        self._understand.setVisible(self._requires_ack)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("確認處理")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._understand.stateChanged.connect(self._refresh_ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addWidget(scroll)
        layout.addWidget(self._understand)
        layout.addWidget(buttons)
        self._refresh_ok()

    def confirmed_ids(self) -> set[str]:
        return set(self._selected_ids)

    def _refresh_ok(self) -> None:
        if self._requires_ack and self._understand.checkState() != Qt.CheckState.Checked:
            self._ok_button.setEnabled(False)
            return
        self._ok_button.setEnabled(True)
