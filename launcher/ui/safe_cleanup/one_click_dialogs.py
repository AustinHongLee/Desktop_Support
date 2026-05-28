from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from launcher.core.safe_cleanup import PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER, CleanupApplyResult, CleanupPlan, is_default_cleanup_candidate
from launcher.ui.components.card import Card


def default_one_click_ids(plan: CleanupPlan) -> set[str]:
    keep_layers = {SAFE_LAYER, REVIEW_LAYER}
    return {
        item.id
        for item in plan.items
        if item.layer in keep_layers and is_default_cleanup_candidate(item)
    }


class OneClickSummaryDialog(QDialog):
    def __init__(self, plan: CleanupPlan, *, selected_ids: set[str], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("一鍵安全清除")
        self.setMinimumWidth(560)

        target_name = plan.targets[0].name if plan.targets else "目前目標"
        title = QLabel(f"即將安全清除：{target_name}")
        title.setObjectName("H1")
        hint = QLabel("將依預設規則處理項目：只選安全層與需確認層，且所有檔案/資料夾都會先移到隔離區。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        selected_count = len(selected_ids)
        deferred_count = len(plan.items) - selected_count
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_mini_card("將清除", f"{selected_count}", "可還原隔離項目"))
        row.addWidget(_mini_card("暫不處理", f"{deferred_count}", "執行中 / 登錄檔 / 系統層"))
        row.addWidget(_mini_card("保留期", "30 天", "可從隔離區檢查與還原"))

        warning = QLabel("不會處理 HKLM / Windows Installer 殘留；管理員深度清理入口即將推出。")
        warning.setObjectName("Muted")
        warning.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("確認執行")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(row)
        layout.addWidget(warning)
        layout.addWidget(buttons)


class OneClickResultDialog(QDialog):
    open_quarantine_requested = False

    def __init__(self, result: CleanupApplyResult, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("安全清除完成")
        self.setMinimumWidth(560)

        title = QLabel("安全清除完成")
        title.setObjectName("H1")
        lines = [
            f"隔離資料夾：{result.quarantine_dir}",
            f"Manifest：{result.manifest_path}",
            f"已隔離檔案/資料夾：{result.moved_count}",
            f"已嘗試關閉程序：{result.closed_process_count}",
            f"已刪 HKCU 登錄值：{result.registry_deleted_count}",
        ]
        if result.errors:
            lines.extend(f"錯誤：{error}" for error in result.errors)
        detail = QLabel("\n".join(lines))
        detail.setObjectName("Mono")
        detail.setWordWrap(True)

        open_button = QPushButton("打開隔離區")
        open_button.setObjectName("Primary")
        open_button.clicked.connect(self._open_quarantine)
        restore_button = QPushButton("全部還原（即將推出）")
        restore_button.setEnabled(False)
        done_button = QPushButton("完成")
        done_button.setObjectName("Ghost")
        done_button.clicked.connect(self.accept)

        actions = QHBoxLayout()
        actions.addWidget(restore_button)
        actions.addStretch(1)
        actions.addWidget(open_button)
        actions.addWidget(done_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addLayout(actions)

    def _open_quarantine(self) -> None:
        self.open_quarantine_requested = True
        self.accept()


def _mini_card(title: str, value: str, subtext: str) -> Card:
    card = Card(padding=12, shadow=False)
    title_label = QLabel(title)
    title_label.setObjectName("Muted")
    value_label = QLabel(value)
    value_label.setObjectName("H1")
    sub_label = QLabel(subtext)
    sub_label.setObjectName("Muted")
    sub_label.setWordWrap(True)
    card.body().addWidget(title_label)
    card.body().addWidget(value_label)
    card.body().addWidget(sub_label)
    return card
