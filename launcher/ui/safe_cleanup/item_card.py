from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, CleanupPlanItem, ItemImpact
from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.layer_language import confidence_label, format_size, language_for_layer
from launcher.ui.safe_cleanup.risk_badge import RiskBadge

_LOCKED_LAYERS = {PROCESS_LAYER, REGISTRY_LAYER}


class ItemCard(Card):
    toggled = pyqtSignal(str, bool)
    clicked = pyqtSignal(object)
    locate_requested = pyqtSignal(object)

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent=parent, padding=12, shadow=False)
        self.setObjectName("ItemCard")
        self.setProperty("selected", False)
        self.setProperty("locked", False)
        self.setProperty("layer", "")
        self._item: CleanupPlanItem | None = None
        self._unlocked = False

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self._checkbox = QCheckBox()
        self._checkbox.stateChanged.connect(self._emit_toggle)
        self._lock_label = QLabel("鎖")
        self._lock_label.setObjectName("LockPill")
        self._lock_label.hide()
        self._badge = RiskBadge(layer="")
        self._title = QLabel()
        self._title.setObjectName("CardTitle")
        self._title.setWordWrap(True)
        self._confidence = QLabel()
        self._confidence.setObjectName("Muted")
        self._locate_button = QPushButton("定位")
        self._locate_button.setObjectName("Ghost")
        self._locate_button.clicked.connect(self._emit_locate)

        top_row.addWidget(self._checkbox)
        top_row.addWidget(self._lock_label)
        top_row.addWidget(self._badge)
        top_row.addWidget(self._title, 1)
        top_row.addWidget(self._confidence)
        top_row.addWidget(self._locate_button)

        self._subtitle = QLabel()
        self._subtitle.setObjectName("Muted")
        self._subtitle.setWordWrap(True)
        self._note = QLabel()
        self._note.setWordWrap(True)
        self._note.setObjectName("Muted")
        self._impact = QLabel()
        self._impact.setObjectName("ImpactText")
        self._impact.setWordWrap(True)
        self._evidence_box = QWidget()
        self._evidence_layout = QVBoxLayout(self._evidence_box)
        self._evidence_layout.setContentsMargins(0, 0, 0, 0)
        self._evidence_layout.setSpacing(3)

        self.body().addLayout(top_row)
        self.body().addWidget(self._subtitle)
        self.body().addWidget(self._note)
        self.body().addWidget(self._impact)
        self.body().addWidget(self._evidence_box)

    def set_item(self, item: CleanupPlanItem, impact: ItemImpact) -> None:
        self._item = item
        language = language_for_layer(item.layer)
        self.setProperty("layer", item.layer)
        self._badge.setProperty("layer", item.layer)
        self._badge.setText(language.title)
        self._badge.setToolTip(language.tooltip)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)
        self._title.setText(item.label)
        self._subtitle.setText(language.subtitle)
        self._note.setText(item.note)
        self._confidence.setText(confidence_label(item.confidence))
        self._locate_button.setEnabled(bool(item.path or item.registry_key or item.process_path))
        self._impact.setText(_impact_text(impact))
        self._impact.setVisible(bool(self._impact.text()))
        self._set_evidence_lines(item)
        self._refresh_check_state()
        self.style().unpolish(self)
        self.style().polish(self)

    def set_unlocked(self, unlocked: bool) -> None:
        self._unlocked = unlocked
        if not self._can_user_check():
            self.set_checked(False)
        self._refresh_check_state()

    def set_checked(self, checked: bool) -> None:
        self._checkbox.blockSignals(True)
        self._checkbox.setChecked(checked and self._can_user_check())
        self._checkbox.blockSignals(False)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def is_checked(self) -> bool:
        return self._checkbox.isChecked() and self._can_user_check()

    def item_id(self) -> str:
        return self._item.id if self._item else ""

    def item(self) -> CleanupPlanItem | None:
        return self._item

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if self._item is not None and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._item)
        super().mousePressEvent(event)

    def _emit_toggle(self, _state: int) -> None:
        if self._item is None:
            return
        self.toggled.emit(self._item.id, self.is_checked())

    def _emit_locate(self) -> None:
        if self._item is not None:
            self.locate_requested.emit(self._item)

    def _can_user_check(self) -> bool:
        if self._item is None or not self._item.executable or self._item.layer == BLOCKED_LAYER:
            return False
        if self._item.layer in _LOCKED_LAYERS and not self._unlocked:
            return False
        return True

    def _refresh_check_state(self) -> None:
        checkable = self._can_user_check()
        locked = not checkable
        self.setProperty("locked", locked)
        self._checkbox.setVisible(checkable)
        self._checkbox.setEnabled(checkable)
        self._lock_label.setVisible(locked)
        self._lock_label.setText(_lock_text(self._item, self._unlocked))
        self.setToolTip(_lock_tooltip(self._item, self._unlocked) if locked else "")
        self.style().unpolish(self)
        self.style().polish(self)

    def _set_evidence_lines(self, item: CleanupPlanItem) -> None:
        while self._evidence_layout.count():
            entry = self._evidence_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()
        show_evidence = item.layer == REVIEW_LAYER
        self._evidence_box.setVisible(show_evidence)
        if not show_evidence:
            return
        evidence = item.evidence[:2]
        if not evidence:
            evidence = ()
        for entry in evidence:
            line = QLabel(f"{_sign(entry.weight)} {entry.label}：{entry.detail}")
            line.setObjectName("EvidenceLine")
            line.setWordWrap(True)
            self._evidence_layout.addWidget(line)
        if not evidence:
            line = QLabel("沒有足夠具體的證據，請打開右側詳情確認。")
            line.setObjectName("EvidenceLine")
            line.setWordWrap(True)
            self._evidence_layout.addWidget(line)


def _impact_text(impact: ItemImpact) -> str:
    parts: list[str] = []
    if impact.shortcut_count:
        parts.append(f"捷徑 {impact.shortcut_count}")
    if impact.registry_ref_count:
        parts.append(f"登錄引用 {impact.registry_ref_count}")
    if impact.process_count:
        parts.append(f"程序 {impact.process_count}")
    if impact.derived_count:
        parts.append(f"衍生項 {impact.derived_count}")
    return "｜".join(parts)


def _lock_text(item: CleanupPlanItem | None, unlocked: bool) -> str:
    if item is None:
        return "鎖"
    if item.layer == BLOCKED_LAYER:
        return "只列出"
    if item.layer == PROCESS_LAYER and not unlocked:
        return "需允許"
    if item.layer == REGISTRY_LAYER and not unlocked:
        return "需允許"
    if not item.executable:
        return "不可執行"
    return "鎖"


def _lock_tooltip(item: CleanupPlanItem | None, unlocked: bool) -> str:
    if item is None:
        return ""
    if item.layer == BLOCKED_LAYER:
        return "系統層項目一般模式只列出，不會清理。"
    if item.layer == PROCESS_LAYER and not unlocked:
        return "請先在左側允許嘗試關閉程序，之後仍需手動勾選。"
    if item.layer == REGISTRY_LAYER and not unlocked:
        return "請先在左側允許設定殘留清理，套用前還會二次確認。"
    if not item.executable:
        return "此項目目前不可執行，可能缺少路徑、PID 或權限。"
    return ""


def _sign(weight: float) -> str:
    if weight > 0:
        return "+"
    if weight < 0:
        return "-"
    return " "
