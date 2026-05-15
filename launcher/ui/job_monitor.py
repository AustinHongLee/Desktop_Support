from __future__ import annotations

import traceback
from datetime import datetime
from typing import Any

from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from launcher.core.action_model import ActionDefinition
from launcher.core.context_model import LauncherContext
from launcher.core.job_model import JobEvent, JobResult
from launcher.core.runner import ActionRunner, RunControl
from launcher.ui.theme import Theme, job_monitor_stylesheet


class ActionRunThread(QThread):
    event_received = pyqtSignal(object)
    result_ready = pyqtSignal(object)

    def __init__(
        self,
        runner: ActionRunner,
        action: ActionDefinition,
        context: LauncherContext,
        *,
        options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._action = action
        self._context = context
        self._options = dict(options or {})
        self._control = RunControl()

    def cancel(self) -> None:
        self._control.cancel()

    def run(self) -> None:
        started_at = datetime.now()
        try:
            result = self._runner.run(
                self._action,
                self._context,
                on_event=self.event_received.emit,
                control=self._control,
                options=self._options,
            )
        except Exception as exc:  # pragma: no cover - defensive guard for UI threads
            event = JobEvent(
                type="error",
                message=f"執行器例外：{exc}",
                data={"traceback": traceback.format_exc()},
            )
            self.event_received.emit(event)
            result = JobResult(
                action_id=self._action.id,
                return_code=-1,
                started_at=started_at,
                finished_at=datetime.now(),
                events=(event,),
            )
        self.result_ready.emit(result)


class JobMonitor(QDialog):
    cancel_requested = pyqtSignal()

    def __init__(self, title: str, *, theme: Theme | None = None) -> None:
        super().__init__()
        self._title = title
        self._theme = theme
        self._started_at = datetime.now()
        self._event_count = 0
        self._error_count = 0
        self._artifact_count = 0
        self.setWindowTitle(f"工作紀錄：{title}")
        self.setMinimumSize(720, 460)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._status = QLabel("執行中")
        self._status.setObjectName("JobStatus")
        self._status.setProperty("state", "running")
        self._summary = QLabel(title)
        self._summary.setObjectName("JobSummary")
        self._summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._elapsed = QLabel("00:00")
        self._elapsed.setObjectName("JobElapsed")
        self._substatus = QLabel("等待工具回報...")
        self._substatus.setObjectName("JobSubstatus")
        self._substatus.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setObjectName("JobProgress")
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("執行中")

        self._copy_log_button = QPushButton("複製紀錄")
        self._copy_log_button.clicked.connect(self._copy_log)
        self._cancel_button = QPushButton("取消")
        self._cancel_button.clicked.connect(self._request_cancel)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._errors = QPlainTextEdit()
        self._errors.setReadOnly(True)
        self._errors.setPlaceholderText("目前沒有錯誤")
        self._errors.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._artifacts = QPlainTextEdit()
        self._artifacts.setReadOnly(True)
        self._artifacts.setPlaceholderText("工具有產出檔案或開啟位置時會顯示在這裡")
        self._artifacts.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("JobTabs")
        self._tabs.addTab(self._log, "全部 0")
        self._tabs.addTab(self._errors, "錯誤 0")
        self._tabs.addTab(self._artifacts, "產出 0")

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        actions.addWidget(self._cancel_button)
        actions.addWidget(self._copy_log_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._build_hero())
        layout.addWidget(self._tabs, 1)
        layout.addLayout(actions)
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(500)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._elapsed_timer.start()
        self._apply_style()

    def append_event(self, event: JobEvent) -> None:
        self._event_count += 1
        line = _format_event(event)
        self._log.appendPlainText(line)
        self._apply_progress(event)
        self._set_substatus(event.message)
        if event.type == "error":
            self._error_count += 1
            self._errors.appendPlainText(line)
            self._set_status("已有錯誤", "error")
            self._tabs.setCurrentIndex(1)
        elif event.type == "cancelled":
            self._error_count += 1
            self._errors.appendPlainText(line)
            self._set_status("取消中", "error")
            self._tabs.setCurrentIndex(1)
        elif event.type == "timeout":
            self._error_count += 1
            self._errors.appendPlainText(line)
            self._set_status("逾時", "error")
            self._tabs.setCurrentIndex(1)
        elif event.type == "artifact":
            self._artifact_count += 1
            self._artifacts.appendPlainText(_format_artifact(event))
        self._update_tab_titles()

    def finish(self, result: JobResult) -> None:
        self._elapsed_timer.stop()
        self._update_elapsed(reference=result.finished_at)
        self._cancel_button.setEnabled(False)
        if any(event.type == "cancelled" for event in result.events):
            state = "已取消"
        elif any(event.type == "timeout" for event in result.events):
            state = "逾時"
        else:
            state = "完成" if result.ok else f"失敗 ({result.return_code})"
        elapsed = result.finished_at - result.started_at
        line = f"[{state}] {elapsed.total_seconds():.2f}s"
        self._log.appendPlainText(line)
        if result.ok:
            self._set_status("完成", "ok")
            self._substatus.setText(f"完成 · 耗時 {elapsed.total_seconds():.2f}s")
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._progress.setFormat("100 %")
        else:
            self._set_status(state, "error")
            self._substatus.setText(f"{state} · 耗時 {elapsed.total_seconds():.2f}s")
            self._progress.setRange(0, 100)
            self._progress.setValue(100)
            self._progress.setFormat(state)
            if not any(event.type == "error" for event in result.events):
                self._error_count += 1
                self._errors.appendPlainText("任務失敗，但 worker 沒有回傳明確錯誤。")
                self._tabs.setCurrentIndex(1)
        self._update_tab_titles()

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self._log.toPlainText())

    def _request_cancel(self) -> None:
        self._cancel_button.setEnabled(False)
        self._set_status("取消中", "error")
        self._substatus.setText("已送出取消要求，等待目前步驟停止...")
        self.cancel_requested.emit()

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._hero.setProperty("state", state)
        self._hero.style().unpolish(self._hero)
        self._hero.style().polish(self._hero)

    def _apply_style(self) -> None:
        self.setStyleSheet(job_monitor_stylesheet(self._theme) if self._theme is not None else job_monitor_stylesheet())

    def _build_hero(self) -> QFrame:
        self._hero = QFrame()
        self._hero.setObjectName("JobHero")
        self._hero.setProperty("state", "running")
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(self._status)
        title_row.addWidget(self._summary, 1)
        title_row.addWidget(self._elapsed)

        layout = QVBoxLayout(self._hero)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addLayout(title_row)
        layout.addWidget(self._substatus)
        layout.addWidget(self._progress)
        return self._hero

    def _update_elapsed(self, *, reference: datetime | None = None) -> None:
        now = reference or datetime.now()
        elapsed = max(0, int((now - self._started_at).total_seconds()))
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            self._elapsed.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self._elapsed.setText(f"{minutes:02d}:{seconds:02d}")

    def _set_substatus(self, text: str) -> None:
        if text:
            self._substatus.setText(text)

    def _update_tab_titles(self) -> None:
        self._tabs.setTabText(0, f"全部 {self._event_count}")
        self._tabs.setTabText(1, f"錯誤 {self._error_count}")
        self._tabs.setTabText(2, f"產出 {self._artifact_count}")

    def _apply_progress(self, event: JobEvent) -> None:
        current, total = _progress_numbers(event)
        if current is not None and total is not None and total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(max(0, min(current, total)))
            self._progress.setFormat(f"{current} / {total}")
            return
        percent = _progress_percent(event)
        if percent is not None:
            value = max(0, min(percent, 100))
            self._progress.setRange(0, 100)
            self._progress.setValue(value)
            self._progress.setFormat(f"{value} %")


def _format_event(event: JobEvent) -> str:
    prefix = _event_label(event.type)
    message = event.message or _format_data(event.data)
    lines = [f"[{prefix}] {message}"]

    for key, label in (
        ("path", "路徑"),
        ("count", "數量"),
        ("return_code", "結束碼"),
        ("timeout_seconds", "逾時秒數"),
        ("recent_output", "最近輸出"),
        ("traceback", "追蹤"),
    ):
        value = event.data.get(key)
        if value not in (None, ""):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _format_artifact(event: JobEvent) -> str:
    parts = [event.message or "產出"]
    path = event.data.get("path")
    if path:
        parts.append(str(path))
    count = event.data.get("count")
    if count is not None:
        parts.append(f"數量: {count}")
    return "\n".join(parts)


def _format_data(data: dict[str, object]) -> str:
    if not data:
        return ""
    return ", ".join(f"{key}={value}" for key, value in data.items())


def _progress_numbers(event: JobEvent) -> tuple[int | None, int | None]:
    current = _int_from_data(event.data, "current", "done", "processed", "index")
    total = _int_from_data(event.data, "total", "count_total")
    return current, total


def _progress_percent(event: JobEvent) -> int | None:
    value = _float_from_data(event.data, "percent", "progress")
    if value is None:
        return None
    if 0 <= value <= 1:
        value *= 100
    return round(value)


def _int_from_data(data: dict[str, object], *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _float_from_data(data: dict[str, object], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _event_label(event_type: str) -> str:
    return {
        "started": "開始",
        "message": "訊息",
        "progress": "進度",
        "artifact": "產出",
        "completed": "完成",
        "error": "錯誤",
        "cancelled": "取消",
        "timeout": "逾時",
        "log": "紀錄",
    }.get(event_type, event_type.upper())
