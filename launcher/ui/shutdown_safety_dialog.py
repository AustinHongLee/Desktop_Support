from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from launcher.core.shutdown_safety import (
    ShutdownBlocker,
    ShutdownSafetyReport,
    apply_shutdown_policy,
    report_to_table,
    scan_shutdown_blockers,
    stop_blocker,
    write_report,
)
from launcher.core.state_store import AppStateStore
from launcher.ui.theme import safe_cleanup_stylesheet, theme_by_name


class ShutdownSafetyDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        scan_reason: str = "manual.ui",
        allow_cancel: bool = True,
        report: ShutdownSafetyReport | None = None,
    ) -> None:
        super().__init__(parent)
        self._scan_reason = scan_reason
        self._allow_cancel = allow_cancel
        self._report = report or scan_shutdown_blockers(scan_reason=scan_reason)
        self._report_path = write_report(self._report)
        self._blocker_by_id: dict[str, ShutdownBlocker] = {}
        self._ignored_ids: set[str] = set()

        self.setWindowTitle("Shutdown Safety Inspector")
        self.setMinimumSize(1120, 720)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("Shutdown Safety Inspector")
        title.setObjectName("H1")
        hint = QLabel("關閉 app、登出、重開機或關機前，先列出仍咬著本專案 runtime 的程序、job、lock、暫存與檔案關係。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        self._summary = QLabel()
        self._summary.setObjectName("Muted")
        self._summary.setWordWrap(True)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(9)
        self._tree.setHeaderLabels(["誰", "PID", "PPID", "SafeToKill", "角色", "Job", "啟動時間", "原因", "命令摘要"])
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setRootIsDecorated(False)
        self._tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._tree.itemSelectionChanged.connect(self._refresh_detail)
        self._configure_columns()

        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._graph = QPlainTextEdit()
        self._graph.setReadOnly(True)
        self._graph.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._raw = QPlainTextEdit()
        self._raw.setReadOnly(True)
        self._raw.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._details, "細節")
        self._tabs.addTab(self._graph, "Dependency graph")
        self._tabs.addTab(self._raw, "報告")

        self._wait_button = QPushButton("Wait / 重新掃描")
        self._wait_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self._wait_button.clicked.connect(self.refresh_scan)
        self._graceful_button = QPushButton("Graceful stop")
        self._graceful_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self._graceful_button.clicked.connect(lambda: self.stop_selected(force=False))
        self._force_button = QPushButton("Force stop")
        self._force_button.setObjectName("Danger")
        self._force_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))
        self._force_button.clicked.connect(lambda: self.stop_selected(force=True))
        self._open_log_button = QPushButton("Open log")
        self._open_log_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        self._open_log_button.clicked.connect(self.open_selected_log)
        self._open_folder_button = QPushButton("Open folder")
        self._open_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self._open_folder_button.clicked.connect(self.open_selected_folder)
        self._graph_button = QPushButton("Inspect graph")
        self._graph_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self._graph_button.clicked.connect(self.inspect_dependency_graph)
        self._ignore_button = QPushButton("Ignore once")
        self._ignore_button.clicked.connect(self.ignore_selected_once)

        self._cancel_close_button = QPushButton("Cancel shutdown / close")
        self._cancel_close_button.clicked.connect(self.reject)
        self._proceed_button = QPushButton("套用 Safe 並繼續")
        self._proceed_button.setObjectName("Primary")
        self._proceed_button.clicked.connect(self.apply_safe_and_accept)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        for button in (
            self._wait_button,
            self._graceful_button,
            self._force_button,
            self._open_log_button,
            self._open_folder_button,
            self._graph_button,
            self._ignore_button,
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)
        if self._allow_cancel:
            action_row.addWidget(self._cancel_close_button)
        action_row.addWidget(self._proceed_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._summary)
        layout.addWidget(self._tree, 2)
        layout.addWidget(self._tabs, 1)
        layout.addLayout(action_row)

        self.setStyleSheet(safe_cleanup_stylesheet(theme_by_name(AppStateStore().theme_name)))
        self._populate()

    @property
    def report_path(self) -> Path:
        return self._report_path

    def refresh_scan(self) -> None:
        self._report = scan_shutdown_blockers(scan_reason=self._scan_reason)
        self._report_path = write_report(self._report)
        self._populate()

    def stop_selected(self, *, force: bool) -> None:
        blocker = self._selected_blocker()
        if blocker is None:
            return
        if not blocker.is_killable:
            QMessageBox.information(
                self,
                "Shutdown Safety Inspector",
                "拒絕停止：此 PID 不是可驗證的本專案 command line，或是目前 UI 主程序。",
            )
            return
        if force:
            answer = QMessageBox.warning(
                self,
                "Force stop",
                (
                    f"將強制結束 {blocker.process_name} (PID {blocker.pid}) 的本專案 process tree。\n\n"
                    f"SafeToKill：{blocker.safe_to_kill}\n"
                    f"後遺症：{'; '.join(blocker.kill_consequence[:3])}\n\n"
                    "不會處理 command line 不含本專案路徑的程序。確定要繼續？"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            stop_blocker(blocker, force=force)
        except Exception as exc:
            QMessageBox.warning(self, "Shutdown Safety Inspector", f"停止失敗：{exc}")
            return
        self.refresh_scan()

    def apply_safe_and_accept(self) -> None:
        result = apply_shutdown_policy(self._filtered_report(), kill_safe=True)
        if result.errors:
            QMessageBox.warning(self, "Shutdown Safety Inspector", "\n".join(result.errors[:8]))
            self.refresh_scan()
            return
        self.accept()

    def open_selected_log(self) -> None:
        blocker = self._selected_blocker()
        if blocker is None:
            return
        for value in blocker.log_files:
            path = Path(value)
            if path.exists():
                _open_path(path)
                return
        _open_path(self._report_path)

    def open_selected_folder(self) -> None:
        blocker = self._selected_blocker()
        if blocker is None:
            return
        candidates = [*blocker.temp_dirs, *blocker.output_files, *blocker.input_files, blocker.executable_path]
        for value in candidates:
            if not value:
                continue
            path = Path(value)
            target = path if path.is_dir() else path.parent
            if target.exists():
                _open_path(target)
                return
        _open_path(Path(self._report.project_root))

    def inspect_dependency_graph(self) -> None:
        blocker = self._selected_blocker()
        if blocker is None:
            return
        self._graph.setPlainText(blocker.dependency_graph_text)
        self._tabs.setCurrentWidget(self._graph)

    def ignore_selected_once(self) -> None:
        blocker = self._selected_blocker()
        if blocker is None:
            return
        self._ignored_ids.add(blocker.id)
        self._populate()

    def _populate(self) -> None:
        self._tree.clear()
        self._blocker_by_id = {blocker.id: blocker for blocker in self._report.blockers if blocker.id not in self._ignored_ids}
        blockers = tuple(self._blocker_by_id.values())
        self._summary.setText(
            "掃描結果："
            f"{len(blockers)} 個 blocker｜Safe {sum(1 for item in blockers if item.safe_to_kill == 'Safe')}｜"
            f"Caution {sum(1 for item in blockers if item.safe_to_kill == 'Caution')}｜"
            f"Dangerous {sum(1 for item in blockers if item.safe_to_kill == 'Dangerous')}｜"
            f"Unknown {sum(1 for item in blockers if item.safe_to_kill == 'Unknown')}｜"
            f"JSON：{self._report_path}"
        )
        self._raw.setPlainText(report_to_table(self._filtered_report()))
        if not blockers:
            item = QTreeWidgetItem(["沒有 blocker", "", "", "", "", "", "", "本專案 runtime 目前沒有仍在執行的 process/job/lock。", ""])
            item.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(item)
            self._details.setPlainText("沒有需要處理的 shutdown blocker。")
            self._graph.setPlainText("")
            self._refresh_buttons()
            return
        for blocker in blockers:
            item = QTreeWidgetItem(
                [
                    blocker.process_name,
                    str(blocker.pid),
                    str(blocker.parent_pid or ""),
                    blocker.safe_to_kill,
                    blocker.process_role,
                    blocker.job_id,
                    blocker.started_at,
                    "; ".join(blocker.reasons[:2]),
                    blocker.command_summary,
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, blocker.id)
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            color = _level_color(blocker.safe_to_kill)
            for column in range(self._tree.columnCount()):
                item.setForeground(column, QBrush(QColor(color)))
            self._tree.addTopLevelItem(item)
        self._tree.setCurrentItem(self._tree.topLevelItem(0))
        self._refresh_detail()

    def _refresh_detail(self) -> None:
        blocker = self._selected_blocker()
        if blocker is None:
            self._details.setPlainText("")
            self._graph.setPlainText("")
            self._refresh_buttons()
            return
        self._details.setPlainText(_detail_text(blocker))
        self._graph.setPlainText(blocker.dependency_graph_text)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        blocker = self._selected_blocker()
        has_blocker = blocker is not None
        killable = has_blocker and blocker.is_killable
        self._graceful_button.setEnabled(bool(killable and blocker.safe_to_kill in {"Safe", "Caution"}))
        self._force_button.setEnabled(bool(killable))
        self._open_log_button.setEnabled(has_blocker)
        self._open_folder_button.setEnabled(has_blocker)
        self._graph_button.setEnabled(has_blocker)
        self._ignore_button.setEnabled(has_blocker)
        self._proceed_button.setText("關閉" if not self._blocker_by_id else "套用 Safe 並繼續")

    def _selected_blocker(self) -> ShutdownBlocker | None:
        current = self._tree.currentItem()
        if current is None:
            return None
        blocker_id = current.data(0, Qt.ItemDataRole.UserRole)
        return self._blocker_by_id.get(str(blocker_id))

    def _filtered_report(self) -> ShutdownSafetyReport:
        return ShutdownSafetyReport(
            project_root=self._report.project_root,
            scan_reason=self._report.scan_reason,
            created_at=self._report.created_at,
            blockers=tuple(self._blocker_by_id.values()),
            stale_locks_removed=self._report.stale_locks_removed,
            report_path=str(self._report_path),
        )

    def _configure_columns(self) -> None:
        header = self._tree.header()
        header.setStretchLastSection(False)
        widths = (190, 80, 80, 110, 170, 210, 190, 360, 520)
        for column, width in enumerate(widths):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            self._tree.setColumnWidth(column, width)


def run_shutdown_safety_dialog(parent: QWidget | None = None, *, scan_reason: str, allow_cancel: bool = True) -> bool:
    dialog = ShutdownSafetyDialog(parent, scan_reason=scan_reason, allow_cancel=allow_cancel)
    return dialog.exec() == QDialog.DialogCode.Accepted


def _detail_text(blocker: ShutdownBlocker) -> str:
    sections = [
        ("他是誰", [f"{blocker.process_role}", f"{blocker.process_name} (PID {blocker.pid})", f"Parent PID: {blocker.parent_pid} {blocker.parent_process}".rstrip()]),
        ("CommandLine 摘要", [blocker.command_summary, blocker.command_line]),
        ("Job", [f"job_id: {blocker.job_id or '無'}", f"component: {blocker.component or '未知'}", f"started_at: {blocker.started_at or '未知'}"]),
        ("判斷原因", list(blocker.reasons)),
        ("SafeToKill", [blocker.safe_to_kill, f"可自動停止: {'是' if blocker.can_automatically_stop else '否'}"]),
        ("關掉後遺症", list(blocker.kill_consequence)),
        ("Lock file", list(blocker.lock_files) or ["無"]),
        ("Temp dir", list(blocker.temp_dirs) or ["無"]),
        ("Input file", list(blocker.input_files) or ["無"]),
        ("Output file", list(blocker.output_files) or ["無"]),
        ("Log file", list(blocker.log_files) or ["無"]),
        ("Child process tree", [", ".join(str(pid) for pid in blocker.child_pids) if blocker.child_pids else "無"]),
        ("建議動作", list(blocker.suggested_actions)),
    ]
    lines: list[str] = []
    for title, values in sections:
        lines.append(f"[{title}]")
        lines.extend(f"- {value}" for value in values if value)
        lines.append("")
    return "\n".join(lines).strip()


def _level_color(level: str) -> str:
    return {
        "Safe": "#155e36",
        "Caution": "#92400e",
        "Dangerous": "#991b1b",
        "Unknown": "#334155",
    }.get(level, "#334155")


def _open_path(path: Path) -> None:
    target = path.expanduser().resolve(strict=False)
    if sys_platform_is_windows():
        if target.exists() and target.is_file():
            subprocess.Popen(["explorer.exe", f"/select,{target}"])
            return
        os.startfile(target)  # noqa: S606
        return
    subprocess.Popen(["xdg-open", str(target)])


def sys_platform_is_windows() -> bool:
    import sys

    return sys.platform == "win32"
