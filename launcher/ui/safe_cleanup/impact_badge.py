from __future__ import annotations

from PyQt6.QtWidgets import QLabel

from launcher.core.safe_cleanup import ItemImpact


class ImpactBadge(QLabel):
    def __init__(self, impact: ItemImpact, parent=None) -> None:  # noqa: ANN001
        super().__init__("", parent)
        self.setObjectName("Muted")
        self.set_impact(impact)

    def set_impact(self, impact: ItemImpact) -> None:
        parts: list[str] = []
        if impact.shortcut_count:
            parts.append(f"捷徑 {impact.shortcut_count}")
        if impact.registry_ref_count:
            parts.append(f"登錄檔 {impact.registry_ref_count}")
        if impact.process_count:
            parts.append(f"程序 {impact.process_count}")
        if impact.derived_count:
            parts.append(f"牽連 {impact.derived_count}")
        self.setText("｜".join(parts))
        self.setVisible(bool(parts))

