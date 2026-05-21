from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from launcher.ui.theme import preferences_stylesheet


@dataclass(frozen=True)
class IsoAutopilotResultSummary:
    total_pdfs: int
    ready_count: int
    warning_count: int
    blocked_count: int
    message: str
    detail: str = ""
    can_open_rename_plan: bool = False
    can_view_problems: bool = False


class IsoAutopilotResultDialog(QDialog):
    def __init__(self, summary: IsoAutopilotResultSummary, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._summary = summary
        self._action = "close"

        self.setObjectName("IsoAutopilotResultDialog")
        self.setWindowTitle("ISO 一鍵處理結果")
        self.setMinimumSize(720, 460)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("ISO 一鍵處理結果")
        title.setObjectName("PreferenceTitle")
        message = QLabel(summary.message)
        message.setObjectName("PreferenceHint")
        message.setWordWrap(True)

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(summary.detail or "沒有額外問題明細。")
        details.setMinimumHeight(150)

        close_button = QPushButton("關閉")
        close_button.clicked.connect(lambda: self._finish("close"))
        problems_button = QPushButton("查看問題列")
        problems_button.setEnabled(summary.can_view_problems)
        problems_button.clicked.connect(lambda: self._finish("problems"))
        rename_button = QPushButton("開啟更名確認")
        rename_button.setDefault(summary.can_open_rename_plan)
        rename_button.setEnabled(summary.can_open_rename_plan)
        rename_button.clicked.connect(lambda: self._finish("rename"))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(problems_button)
        buttons.addWidget(close_button)
        buttons.addWidget(rename_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addLayout(self._metric_row())
        layout.addWidget(message)
        layout.addWidget(details, 1)
        layout.addLayout(buttons)
        self.setStyleSheet(preferences_stylesheet())

    @property
    def action(self) -> str:
        return self._action

    def _metric_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_metric_card("PDF", str(self._summary.total_pdfs), "info"))
        row.addWidget(_metric_card("可更名", str(self._summary.ready_count), "ok"))
        row.addWidget(_metric_card("需確認", str(self._summary.warning_count), "warn"))
        row.addWidget(_metric_card("阻擋", str(self._summary.blocked_count), "blocked"))
        return row

    def _finish(self, action: str) -> None:
        self._action = action
        self.accept()


def _metric_card(title: str, value: str, state: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("ResultMetric")
    frame.setProperty("state", state)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(4)
    value_label = QLabel(value)
    value_label.setObjectName("ResultMetricValue")
    title_label = QLabel(title)
    title_label.setObjectName("ResultMetricTitle")
    value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(value_label)
    layout.addWidget(title_label)
    return frame
