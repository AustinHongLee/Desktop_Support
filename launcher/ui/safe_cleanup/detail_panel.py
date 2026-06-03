from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from launcher.core.safe_cleanup import BLOCKED_LAYER, CleanupPlanItem, ItemImpact, evidence_summary
from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.layer_language import confidence_label, format_size, language_for_layer


class DetailPanel(QWidget):
    locate_requested = pyqtSignal(object)
    copy_requested = pyqtSignal(object)

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._item: CleanupPlanItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        card = Card(padding=12, shadow=False)
        self._title = QLabel("詳細資訊")
        self._title.setObjectName("H2")
        self._title.setWordWrap(True)
        self._subtitle = QLabel("選擇左側項目後會顯示來源、影響與證據。")
        self._subtitle.setObjectName("Muted")
        self._subtitle.setWordWrap(True)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMinimumHeight(280)
        self._locate_button = QPushButton("定位來源")
        self._locate_button.setObjectName("Ghost")
        self._locate_button.clicked.connect(self._emit_locate)
        self._copy_button = QPushButton("複製資訊")
        self._copy_button.setObjectName("Ghost")
        self._copy_button.clicked.connect(self._emit_copy)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self._locate_button)
        actions.addWidget(self._copy_button)
        actions.addStretch(1)

        card.body().addWidget(self._title)
        card.body().addWidget(self._subtitle)
        card.body().addWidget(self._text, 1)
        card.body().addLayout(actions)
        layout.addWidget(card, 1)
        self.clear()

    @property
    def text_edit(self) -> QPlainTextEdit:
        return self._text

    def set_item(self, item: CleanupPlanItem | None, impact: ItemImpact | None = None) -> None:
        self._item = item
        if item is None:
            self.clear()
            return
        language = language_for_layer(item.layer)
        self._title.setText(item.label)
        self._subtitle.setText(language.subtitle)
        lines = [
            f"層級：{language.title}",
            f"類型：{item.kind}",
            f"動作：{item.action}",
            f"信心：{confidence_label(item.confidence)}",
            f"證據摘要：{evidence_summary(item)}",
            f"註解：{item.note}",
            f"可執行：{'是' if item.executable else '否'}",
        ]
        location = _location_text(item)
        if location:
            lines.append(f"來源：{location}")
        if item.path:
            lines.append(f"大小：{format_size(item.size_bytes)}")
        if item.process_id:
            lines.append(f"PID：{item.process_id}")
            lines.append(f"程序：{item.process_name}")
            lines.append(f"程序路徑：{item.process_path or '未知'}")
            lines.append(f"可嘗試關閉：{'是' if item.can_close else '否'}")
        if item.registry_key:
            lines.append(f"登錄檔：{item.root_name}\\{item.registry_key}")
            lines.append(f"值：{item.registry_value_name or '(Default)'}")
            lines.append(f"內容：{item.registry_value_data}")
            if item.layer == BLOCKED_LAYER:
                lines.append("")
                lines.append("重裝影響：可能。HKLM / Windows Installer 殘留可能讓安裝程式誤判已安裝、修復/移除入口異常，或沿用舊路徑。")
                lines.append("為什麼不能打勾：此項屬系統層，需管理員深度清理流程。")
        if impact is not None:
            impact_lines = _impact_lines(impact)
            if impact_lines:
                lines.append("")
                lines.append("影響預估：")
                lines.extend(impact_lines)
        if item.evidence:
            lines.append("")
            lines.append("證據帳本：")
            for evidence in item.evidence:
                sign = "+" if evidence.weight > 0 else "-" if evidence.weight < 0 else " "
                lines.append(f"{sign} {evidence.label}：{evidence.detail}")
        self._text.setPlainText("\n".join(lines))
        self._locate_button.setEnabled(bool(item.path or item.registry_key or item.process_path))
        self._copy_button.setEnabled(True)

    def set_status_text(self, text: str) -> None:
        self._item = None
        self._title.setText("狀態")
        self._subtitle.setText("")
        self._text.setPlainText(text)
        self._locate_button.setEnabled(False)
        self._copy_button.setEnabled(bool(text))

    def clear(self) -> None:
        self._item = None
        self._title.setText("詳細資訊")
        self._subtitle.setText("選擇左側項目後會顯示來源、影響與證據。")
        self._text.setPlainText("尚未選擇項目。")
        self._locate_button.setEnabled(False)
        self._copy_button.setEnabled(False)

    def _emit_locate(self) -> None:
        if self._item is not None:
            self.locate_requested.emit(self._item)

    def _emit_copy(self) -> None:
        if self._item is not None:
            self.copy_requested.emit(self._item)


def _location_text(item: CleanupPlanItem) -> str:
    if item.path:
        return item.path
    if item.process_id:
        return item.process_path or f"PID {item.process_id}"
    if item.registry_key:
        return f"{item.root_name}\\{item.registry_key}\\{item.registry_value_name or '(Default)'}"
    return ""


def _impact_lines(impact: ItemImpact) -> list[str]:
    lines: list[str] = []
    if impact.shortcut_count:
        lines.append(f"- 捷徑引用：{impact.shortcut_count} 個")
    if impact.registry_ref_count:
        lines.append(f"- 登錄引用：{impact.registry_ref_count} 個")
    if impact.process_count:
        lines.append(f"- 執行中程序：{impact.process_count} 個")
    if impact.derived_count:
        lines.append(f"- 衍生項目：{impact.derived_count} 個")
    return lines
