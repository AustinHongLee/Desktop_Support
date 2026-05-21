from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import QEvent, QFileInfo, QPoint, QTimer, Qt
from PyQt6.QtGui import QAction, QCursor, QDragEnterEvent, QDragLeaveEvent, QDropEvent, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFileIconProvider,
    QBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QStyle,
    QToolButton,
    QWidget,
)

from launcher.core.action_model import ActionDefinition
from launcher.core.context_inbox import ContextInbox
from launcher.core.context_model import LauncherContext
from launcher.core.context_service import ContextService
from launcher.core.registry import ActionRegistry
from launcher.core.runner import ActionRunner
from launcher.core.state_store import AppStateStore
from launcher.ui.command_palette import ActionRequest, CommandPalette
from launcher.ui.edge_positioner import EdgePositioner, screen_area_from_qrect
from launcher.ui.iso_pdf_naming_dialog import IsoPdfNamingDialog
from launcher.ui.job_monitor import ActionRunThread, JobMonitor
from launcher.ui.plugin_manager_dialog import PluginManagerDialog
from launcher.ui.preferences_dialog import PreferencesDialog
from launcher.ui.rename_dialog import RenameDialog
from launcher.ui.theme import Theme, dock_stylesheet, theme_by_name
from launcher.windows.clipboard import set_clipboard_text
from launcher.windows.explorer_context import get_open_explorer_contexts


class DockWindow(QWidget):
    def __init__(
        self,
        registry: ActionRegistry,
        runner: ActionRunner,
        context_service: ContextService,
        context_inbox: ContextInbox,
        state_store: AppStateStore,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._runner = runner
        self._context_service = context_service
        self._context_inbox = context_inbox
        self._state_store = state_store
        self._context = context_service.current_context()
        self._threads: list[ActionRunThread] = []
        self._monitors: list[JobMonitor] = []
        self._icon_provider = QFileIconProvider()
        self._positioner = EdgePositioner()
        self._toolbar_buttons: list[QToolButton] = []
        self._drag_anchor: QPoint | None = None
        self._tail_drag_offset: float | None = None
        self._tail_drag_edge: str | None = None
        self._drop_target_active = False
        self._collapsed = state_store.auto_hide_enabled

        self.setWindowTitle("工程工具列")
        self.setAcceptDrops(True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self._state_store.auto_hide_delay_ms)
        self._hide_timer.timeout.connect(self._collapse_if_idle)

        self._title_label = QLabel("工具")
        self._title_label.setObjectName("DockTitle")
        self._context_label = QLabel()
        self._context_label.setObjectName("ContextLabel")
        self._context_label.setMinimumWidth(260)
        self._context_label.setMaximumWidth(420)
        self._context_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._context_label.installEventFilter(self)
        self._drop_hint = QLabel("拖放至此設為目前 context")
        self._drop_hint.setObjectName("DropHint")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setVisible(False)
        self._tail_button = QToolButton()
        self._tail_button.setObjectName("DockTail")
        self._tail_button.setText("工具 Ctrl+K")
        self._tail_button.setToolTip("展開工程工具列")
        self._tail_button.clicked.connect(self._expand_from_tail)
        self._tail_button.installEventFilter(self)

        palette_button = self._tool_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
            "指令",
            self.open_palette,
            text="指令  Ctrl+K",
        )
        palette_button.setProperty("role", "primary")
        iso_button = self._tool_button(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView),
            "開啟 ISO PDF 一鍵處理",
            self.open_iso_workbench,
            text="ISO 命名",
        )
        iso_button.setObjectName("IsoShortcutButton")
        iso_button.setProperty("role", "iso")
        iso_button.setToolTip("開啟 ISO PDF 一鍵處理 / 命名工作台")
        recent_button = self._menu_button("近期", self._build_recent_menu)
        recent_button.setToolTip("最近指令、最近檔案、最近資料夾")
        overflow_button = self._menu_button("更多", self._build_overflow_menu)
        overflow_button.setToolTip("外掛、位置、偏好設定、關閉")

        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._layout.setContentsMargins(10, 4, 10, 4)
        self._layout.setSpacing(6)
        self._layout.addWidget(self._tail_button)
        self._layout.addWidget(self._title_label)
        self._layout.addWidget(palette_button)
        self._layout.addWidget(iso_button)
        self._layout.addWidget(recent_button)
        self._layout.addWidget(self._context_label)
        self._layout.addWidget(self._drop_hint, 1)
        self._layout.addStretch(1)
        self._layout.addWidget(overflow_button)

        shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(self.open_palette)
        self._context_timer = QTimer(self)
        self._context_timer.setInterval(700)
        self._context_timer.timeout.connect(self._poll_context_inbox)
        self._context_timer.start()
        self._apply_style()
        self._update_context_label()
        self._poll_context_inbox()
        self._snap_to_edge()

    def eventFilter(self, watched, event) -> bool:  # noqa: ANN001
        if watched is self._tail_button and event.type() == QEvent.Type.MouseButtonDblClick:
            self._set_auto_hide_enabled(not self._state_store.auto_hide_enabled)
            event.accept()
            return True
        if watched is self._tail_button and event.type() == QEvent.Type.MouseButtonPress:
            if (
                self._collapsed
                and event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.AltModifier
            ):
                self._hide_timer.stop()
                self._tail_drag_edge = self._positioner.normalize_edge(self._state_store.edge)
                self._tail_drag_offset = self._state_store.tail_offset(self._tail_drag_edge)
                self._tail_button.setProperty("movingTail", "true")
                self._tail_button.style().unpolish(self._tail_button)
                self._tail_button.style().polish(self._tail_button)
                event.accept()
                return True
        if watched is self._tail_button and event.type() == QEvent.Type.MouseMove and self._tail_drag_edge is not None:
            self._move_tail_to_global(event.globalPosition().toPoint(), commit=False)
            event.accept()
            return True
        if watched is self._tail_button and event.type() == QEvent.Type.MouseButtonRelease and self._tail_drag_edge is not None:
            self._move_tail_to_global(event.globalPosition().toPoint(), commit=True)
            self._tail_button.setProperty("movingTail", "false")
            self._tail_button.style().unpolish(self._tail_button)
            self._tail_button.style().polish(self._tail_button)
            self._tail_drag_edge = None
            self._tail_drag_offset = None
            event.accept()
            return True
        if watched is self._context_label and event.type() == QEvent.Type.MouseButtonPress:
            menu = self._prepare_menu(self._build_context_menu())
            menu.popup(QCursor.pos())
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def enterEvent(self, event) -> None:  # noqa: ANN001
        self._handle_dock_enter()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: ANN001
        self._schedule_collapse()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if self._state_store.auto_hide_enabled and self._collapsed:
            self._set_collapsed(False)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.AltModifier:
            self._hide_timer.stop()
            self._drag_anchor = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if self._drag_anchor is not None:
            self.move(event.globalPosition().toPoint() - self._drag_anchor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        if self._drag_anchor is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_anchor = None
            self._snap_dragged_position_to_edge(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def refresh_context(self) -> None:
        self._context = self._context_service.current_context()
        self._update_context_label()

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "選擇目前資料夾",
            str(self._context.folder or Path.cwd()),
        )
        if not folder:
            return
        self._use_context(LauncherContext(folder=Path(folder), source="picker.folder"), record=True)

    def pick_files(self) -> None:
        files, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "選擇目前檔案",
            str(self._context.folder or Path.cwd()),
        )
        if not files:
            return
        self._use_context(LauncherContext.from_paths(files, source="picker.files"), record=True)

    def use_cwd_context(self) -> None:
        self._use_context(LauncherContext(folder=Path.cwd(), source="manual.cwd"), record=False)

    def open_palette(self) -> None:
        recent_action_ids = [recent.action_id for recent in self._state_store.recent_actions()]
        palette = CommandPalette(
            self._registry,
            self._context,
            recent_action_ids=recent_action_ids,
            theme=self._theme(),
            developer_mode=self._state_store.developer_mode,
        )
        palette.action_requested.connect(self.run_action)
        palette.exec()

    def open_iso_workbench(self) -> None:
        self._open_iso_workbench("iso.pdf_page_naming", "ISO PDF 拆頁命名", "ISO")

    def _open_iso_workbench(self, action_id: str, title: str, category: str) -> None:
        self._state_store.record_action(action_id, title, category)
        self._state_store.record_context(self._context)
        dialog = IsoPdfNamingDialog(self._context, self, state_store=self._state_store)
        dialog.exec()

    def run_action(self, action: ActionDefinition | ActionRequest) -> None:
        options = {}
        if isinstance(action, ActionRequest):
            options = action.options
            action = action.action
        if action.command.type == "ui_rename_dialog":
            self._state_store.record_action(action.id, action.title, action.category)
            self._state_store.record_context(self._context)
            dialog = RenameDialog(self._context, self)
            dialog.exec()
            return
        if action.command.type == "ui_iso_pdf_rename_dialog":
            self._open_iso_workbench(action.id, action.title, action.category)
            return

        self._state_store.record_action(action.id, action.title, action.category)
        self._state_store.record_context(self._context)
        monitor = JobMonitor(action.title, theme=self._theme())
        thread = ActionRunThread(self._runner, action, self._context, options=options)
        thread.event_received.connect(monitor.append_event)
        thread.result_ready.connect(monitor.finish)
        monitor.cancel_requested.connect(thread.cancel)
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(self._refresh_tail)
        monitor.finished.connect(lambda: self._monitors.remove(monitor) if monitor in self._monitors else None)
        self._threads.append(thread)
        self._monitors.append(monitor)
        self._refresh_tail()
        monitor.show()
        thread.start()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            self._hide_timer.stop()
            if self._state_store.auto_hide_enabled and self._collapsed:
                self._set_collapsed(False)
            self._set_drop_target_active(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drop_target_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drop_target_active(False)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths:
            return
        self._context = LauncherContext.from_paths(paths, source="drop")
        self._state_store.record_context(self._context)
        self._update_context_label()
        event.acceptProposedAction()

    def _update_context_label(self) -> None:
        source = _source_label(self._context.source)
        indicator = _context_indicator(self._context)
        if self._context.file_count:
            parent = self._context.files[0].parent if self._context.files else self._context.folder
            text = f"{indicator} {source} · {self._context.file_count} 個檔案 · {_compact_path(parent)}"
        elif self._context.folder:
            text = f"{indicator} {source} · {_compact_path(self._context.folder)}"
        else:
            text = f"{indicator} 沒有位置"
        self._context_label.setText(text)
        source_kind = _source_kind(self._context)
        self._context_label.setProperty("sourceKind", source_kind)
        self._context_label.style().unpolish(self._context_label)
        self._context_label.style().polish(self._context_label)
        tooltip_lines = ["點擊可切換來源", f"來源：{self._context.source}"]
        if self._context.folder:
            tooltip_lines.append(f"資料夾：{self._context.folder}")
        if self._context.files:
            tooltip_lines.append("檔案：")
            tooltip_lines.extend(str(path) for path in self._context.files[:20])
        self._context_label.setToolTip("\n".join(tooltip_lines))
        self._refresh_tail()

    def _tool_button(
        self,
        icon: QIcon,
        tooltip: str,
        callback,  # noqa: ANN001
        *,
        text: str | None = None,
    ) -> QToolButton:
        button = QToolButton()
        button.setIcon(icon)
        if text:
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        button.setFixedHeight(30)
        self._toolbar_buttons.append(button)
        return button

    def _menu_button(self, text: str, menu_builder) -> QToolButton:  # noqa: ANN001
        button = QToolButton()
        button.setText(text)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setFixedHeight(30)
        button.pressed.connect(lambda: button.setMenu(self._prepare_menu(menu_builder())))
        button.setMenu(self._prepare_menu(menu_builder()))
        self._toolbar_buttons.append(button)
        return button

    def _prepare_menu(self, menu: QMenu) -> QMenu:
        menu.aboutToShow.connect(self._hide_timer.stop)
        menu.aboutToHide.connect(self._schedule_collapse)
        return menu

    def _build_recent_menu(self) -> QMenu:
        menu = QMenu(self)
        recent_actions = self._build_recent_actions_menu()
        recent_actions.setTitle("最近指令")
        menu.addMenu(recent_actions)
        recent_files = self._build_recent_files_menu()
        recent_files.setTitle("最近檔案")
        menu.addMenu(recent_files)
        recent_folders = self._build_recent_folders_menu()
        recent_folders.setTitle("最近資料夾")
        menu.addMenu(recent_folders)
        return menu

    def _build_recent_actions_menu(self) -> QMenu:
        menu = QMenu(self)
        visible_actions = {
            action.id: action
            for action in self._registry.visible_actions(developer_mode=self._state_store.developer_mode)
        }
        for recent in self._state_store.recent_actions():
            action_def = visible_actions.get(recent.action_id)
            if action_def is None:
                continue
            item = QAction(f"{recent.title}  [{recent.category}]", menu)
            item.triggered.connect(lambda _checked=False, selected=action_def: self.run_action(selected))
            menu.addAction(item)
        if menu.isEmpty():
            empty = QAction("尚無近期指令", menu)
            empty.setEnabled(False)
            menu.addAction(empty)
        return menu

    def _build_recent_files_menu(self) -> QMenu:
        menu = QMenu(self)
        paths = self._state_store.recent_files()
        for path in paths:
            menu.addMenu(self._recent_file_menu(path, menu))
        if menu.isEmpty():
            empty = QAction("尚無近期檔案", menu)
            empty.setEnabled(False)
            menu.addAction(empty)
        else:
            menu.addSeparator()
            clear_action = QAction("清空最近檔案", menu)
            clear_action.triggered.connect(self._state_store.clear_recent_files)
            menu.addAction(clear_action)
        return menu

    def _build_recent_folders_menu(self) -> QMenu:
        menu = QMenu(self)
        paths = self._state_store.recent_folders()
        for path in paths:
            menu.addMenu(self._recent_folder_menu(path, menu))
        if menu.isEmpty():
            empty = QAction("尚無近期資料夾", menu)
            empty.setEnabled(False)
            menu.addAction(empty)
        else:
            menu.addSeparator()
            clear_action = QAction("清空最近資料夾", menu)
            clear_action.triggered.connect(self._state_store.clear_recent_folders)
            menu.addAction(clear_action)
        return menu

    def _recent_file_menu(self, path: Path, parent: QMenu) -> QMenu:
        submenu = QMenu(f"{path.name or str(path)} @ {_compact_path(path.parent)}", parent)
        submenu.setIcon(self._path_icon(path))
        submenu.setToolTip(str(path))
        use_action = QAction("設為目前檔案", submenu)
        use_action.triggered.connect(lambda: self._use_context(LauncherContext.from_paths([path], source="recent.file"), record=False))
        open_action = QAction("開啟檔案", submenu)
        open_action.triggered.connect(lambda: self._open_path(path))
        reveal_action = QAction("在 Explorer 定位", submenu)
        reveal_action.triggered.connect(lambda: self._reveal_path(path))
        copy_action = QAction("複製路徑", submenu)
        copy_action.triggered.connect(lambda: set_clipboard_text(str(path)))
        submenu.addAction(use_action)
        submenu.addAction(open_action)
        submenu.addAction(reveal_action)
        submenu.addSeparator()
        submenu.addAction(copy_action)
        return submenu

    def _recent_folder_menu(self, path: Path, parent: QMenu) -> QMenu:
        submenu = QMenu(_folder_menu_label(path), parent)
        submenu.setIcon(self._path_icon(path))
        submenu.setToolTip(str(path))
        use_action = QAction("設為目前資料夾", submenu)
        use_action.triggered.connect(lambda: self._use_context(LauncherContext(folder=path, source="recent.folder"), record=False))
        open_action = QAction("開啟資料夾", submenu)
        open_action.triggered.connect(lambda: self._open_path(path))
        terminal_action = QAction("在此開啟 PowerShell", submenu)
        terminal_action.triggered.connect(lambda: self._open_powershell(path))
        copy_action = QAction("複製路徑", submenu)
        copy_action.triggered.connect(lambda: set_clipboard_text(str(path)))
        submenu.addAction(use_action)
        submenu.addAction(open_action)
        submenu.addAction(terminal_action)
        submenu.addSeparator()
        submenu.addAction(copy_action)
        return submenu

    def _build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        explorer = QAction("抓取最上層 Explorer", menu)
        explorer.setToolTip("讀取目前桌面上最前面的檔案總管資料夾與選取檔案")
        explorer.triggered.connect(self.refresh_context)
        explorer_windows_menu = QMenu("選擇 Explorer 視窗", menu)
        explorer_contexts = get_open_explorer_contexts()
        for context in explorer_contexts:
            item = QAction(_explorer_context_label(context), explorer_windows_menu)
            item.setToolTip(_context_tooltip(context))
            item.triggered.connect(lambda _checked=False, selected=context: self._use_context(selected, record=False))
            explorer_windows_menu.addAction(item)
        if not explorer_contexts:
            empty = QAction("目前沒有可讀取的 Explorer 視窗", explorer_windows_menu)
            empty.setEnabled(False)
            explorer_windows_menu.addAction(empty)
        pick_folder = QAction("手動選擇資料夾...", menu)
        pick_folder.triggered.connect(self.pick_folder)
        pick_files = QAction("手動選擇檔案...", menu)
        pick_files.triggered.connect(self.pick_files)
        cwd = QAction("開發用：使用程式目錄", menu)
        cwd.triggered.connect(self.use_cwd_context)
        menu.addAction(explorer)
        menu.addMenu(explorer_windows_menu)
        menu.addSeparator()
        menu.addAction(pick_folder)
        menu.addAction(pick_files)
        menu.addSeparator()
        menu.addAction(cwd)
        return menu

    def _build_plugin_menu(self) -> QMenu:
        menu = QMenu(self)
        report = self._registry.last_report
        summary = QAction(
            f"{report.plugin_count} 個外掛 / {report.action_count} 個指令",
            menu,
        )
        summary.setEnabled(False)
        menu.addAction(summary)
        if report.issues:
            issue_summary = QAction(f"{len(report.issues)} 個載入問題", menu)
            issue_summary.setEnabled(False)
            menu.addAction(issue_summary)
        menu.addSeparator()
        manage = QAction("外掛管理...", menu)
        manage.triggered.connect(self.open_plugin_manager)
        reload_action = QAction("重新載入外掛", menu)
        reload_action.triggered.connect(self.reload_plugins)
        open_folder = QAction("開啟外掛資料夾", menu)
        open_folder.triggered.connect(self._open_plugin_folder)
        menu.addAction(manage)
        menu.addAction(reload_action)
        menu.addAction(open_folder)
        return menu

    def _build_edge_menu(self) -> QMenu:
        menu = QMenu(self)
        edges = {
            "top": "貼上方",
            "bottom": "貼下方",
            "left": "貼左側",
            "right": "貼右側",
        }
        for edge, title in edges.items():
            item = QAction(title, menu)
            item.triggered.connect(lambda _checked=False, selected=edge: self._set_edge(selected))
            menu.addAction(item)
        menu.addSeparator()
        auto_hide = QAction("自動收合／留尾巴", menu)
        auto_hide.setCheckable(True)
        auto_hide.setChecked(self._state_store.auto_hide_enabled)
        auto_hide.triggered.connect(self._set_auto_hide_enabled)
        menu.addAction(auto_hide)
        collapse_now = QAction("立即收合", menu)
        collapse_now.setEnabled(self._state_store.auto_hide_enabled)
        collapse_now.triggered.connect(lambda: self._set_collapsed(True))
        menu.addAction(collapse_now)
        menu.addSeparator()
        cursor_screen = QAction("移到滑鼠所在螢幕", menu)
        cursor_screen.triggered.connect(self._set_screen_at_cursor)
        menu.addAction(cursor_screen)
        screen_menu = menu.addMenu("指定螢幕")
        for screen in QApplication.screens():
            geometry = screen.availableGeometry()
            title = f"{screen.name()}  {geometry.width()}x{geometry.height()}"
            item = QAction(title, screen_menu)
            item.triggered.connect(lambda _checked=False, selected=screen.name(): self._set_screen(selected))
            screen_menu.addAction(item)
        menu.addSeparator()
        preferences = QAction("偏好設定...", menu)
        preferences.triggered.connect(self.open_preferences)
        menu.addAction(preferences)
        return menu

    def _build_overflow_menu(self) -> QMenu:
        menu = QMenu(self)
        plugin_menu = self._build_plugin_menu()
        plugin_menu.setTitle("外掛")
        menu.addMenu(plugin_menu)
        edge_menu = self._build_edge_menu()
        edge_menu.setTitle("位置與收合")
        menu.addMenu(edge_menu)
        menu.addSeparator()
        quit_action = QAction("關閉工具列", menu)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        return menu

    def open_plugin_manager(self) -> None:
        dialog = PluginManagerDialog(self._registry, self)
        dialog.exec()

    def reload_plugins(self) -> None:
        report = self._registry.reload()
        if report.ok:
            QMessageBox.information(
                self,
                "外掛已重新載入",
                f"已載入 {report.plugin_count} 個外掛，{report.action_count} 個指令。",
            )
            return
        QMessageBox.warning(
            self,
            "外掛重新載入完成，但有問題",
            f"已載入 {report.plugin_count} 個外掛，{report.action_count} 個指令。\n"
            f"另有 {len(report.issues)} 個載入問題，請到外掛管理查看。",
        )

    def _open_plugin_folder(self) -> None:
        self._registry.plugin_root.mkdir(parents=True, exist_ok=True)
        self._open_path(self._registry.plugin_root)

    def open_preferences(self) -> None:
        dialog = PreferencesDialog(
            self._state_store,
            screen_names=[screen.name() for screen in QApplication.screens()],
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        preferences = dialog.preferences()
        self._state_store.set_dock_preferences(
            edge=preferences.edge,
            screen_name=preferences.screen_name,
            auto_hide_enabled=preferences.auto_hide_enabled,
            auto_hide_delay_ms=preferences.auto_hide_delay_ms,
            theme_name=preferences.theme_name,
            developer_mode=preferences.developer_mode,
        )
        self._apply_dock_preferences()

    def _use_context(self, context: LauncherContext, *, record: bool = True) -> None:
        self._context = context
        if record:
            self._state_store.record_context(context)
        self._update_context_label()

    def _set_drop_target_active(self, active: bool) -> None:
        if self._drop_target_active == active:
            return
        self._drop_target_active = active
        self._drop_hint.setVisible(active)
        self.setProperty("dropTarget", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _set_edge(self, edge: str) -> None:
        self._state_store.set_edge(edge)
        self._snap_to_edge()

    def _set_auto_hide_enabled(self, enabled: bool) -> None:
        self._state_store.set_auto_hide_enabled(enabled)
        self._apply_dock_preferences()

    def _set_screen(self, screen_name: str) -> None:
        self._state_store.set_screen_name(screen_name)
        self._snap_to_edge()

    def _set_screen_at_cursor(self) -> None:
        screen = QApplication.screenAt(QCursor.pos())
        if screen is not None:
            self._set_screen(screen.name())

    def _apply_dock_preferences(self) -> None:
        self._hide_timer.stop()
        self._hide_timer.setInterval(self._state_store.auto_hide_delay_ms)
        self._apply_style()
        if self._state_store.auto_hide_enabled:
            self._set_collapsed(True)
        else:
            self._set_collapsed(False)

    def _snap_to_edge(self) -> None:
        screen = self._target_screen()
        if screen is None:
            self.resize(760, 40)
            self.move(0, 0)
            return

        area = screen.availableGeometry()
        edge = self._positioner.normalize_edge(self._state_store.edge)
        placement = self._positioner.compute(
            screen_area_from_qrect(area),
            edge=edge,
            collapsed=self._collapsed,
            tail_offset=self._tail_offset_for_edge(edge),
        )
        self._apply_edge_layout(edge)
        self.setFixedSize(placement.width, placement.height)
        self.move(placement.x, placement.y)

    def _snap_dragged_position_to_edge(self, global_position: QPoint) -> None:
        screen = QApplication.screenAt(global_position) or self._target_screen()
        if screen is None:
            return
        edge = self._positioner.nearest_edge(
            screen_area_from_qrect(screen.availableGeometry()),
            global_position.x(),
            global_position.y(),
        )
        self._state_store.set_screen_name(screen.name())
        self._state_store.set_edge(edge)
        self._set_collapsed(False)

    def _apply_edge_layout(self, edge: str) -> None:
        vertical = edge in {"left", "right"}
        direction = QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.LeftToRight
        self._layout.setDirection(direction)
        if vertical:
            self._layout.setContentsMargins(6, 10, 6, 10)
            self._context_label.setWordWrap(True)
            self._context_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._context_label.setMinimumWidth(96)
            self._context_label.setMaximumWidth(106)
            self._context_label.setMinimumHeight(88)
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for button in self._toolbar_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                button.setFixedSize(104, 46)
        else:
            self._layout.setContentsMargins(10, 4, 10, 4)
            self._context_label.setWordWrap(False)
            self._context_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._context_label.setMinimumWidth(260)
            self._context_label.setMaximumWidth(420)
            self._context_label.setMinimumHeight(0)
            self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            for button in self._toolbar_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setFixedHeight(30)
                button.setMaximumWidth(16777215)
                button.setMinimumWidth(0)
        self._sync_tail_visibility(edge)

    def _sync_tail_visibility(self, edge: str) -> None:
        controls = [self._title_label, self._context_label, *self._toolbar_buttons]
        for widget in controls:
            widget.setVisible(not self._collapsed)
        self._drop_hint.setVisible(self._drop_target_active and not self._collapsed)
        self._tail_button.setVisible(self._collapsed)
        vertical = edge in {"left", "right"}
        if self._collapsed:
            self._layout.setSpacing(0)
            self._layout.setContentsMargins(1, 1, 1, 1)
            self._tail_button.setProperty("tailOrientation", "vertical" if vertical else "horizontal")
            self._tail_button.setText(self._tail_text(vertical))
            self._tail_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self._tail_button.setToolTip(self._tail_tooltip())
            self._tail_button.setProperty("sourceKind", _source_kind(self._context))
            self._tail_button.setProperty("activeJobs", "true" if self._active_job_count() else "false")
            if vertical:
                self._tail_button.setFixedSize(18, 132)
            else:
                self._tail_button.setFixedSize(160, 18)
            self._tail_button.style().unpolish(self._tail_button)
            self._tail_button.style().polish(self._tail_button)
        else:
            self._tail_button.setProperty("tailOrientation", "expanded")
            self._tail_button.setProperty("sourceKind", _source_kind(self._context))
            self._tail_button.setProperty("activeJobs", "true" if self._active_job_count() else "false")
            self._tail_button.setMinimumSize(0, 0)
            self._tail_button.setMaximumSize(16777215, 16777215)

    def _set_collapsed(self, collapsed: bool) -> None:
        if collapsed and not self._state_store.auto_hide_enabled:
            return
        self._collapsed = collapsed
        self._snap_to_edge()
        if not collapsed:
            self.raise_()

    def _expand_from_tail(self) -> None:
        self._hide_timer.stop()
        self._set_collapsed(False)

    def _handle_dock_enter(self) -> None:
        self._hide_timer.stop()

    def _schedule_collapse(self) -> None:
        if self._state_store.auto_hide_enabled and not self._collapsed:
            self._hide_timer.start()

    def _collapse_if_idle(self) -> None:
        if not self._state_store.auto_hide_enabled or self._collapsed:
            return
        if self.underMouse() or QApplication.activePopupWidget() is not None:
            self._hide_timer.start()
            return
        self._set_collapsed(True)

    def _tail_text(self, vertical: bool) -> str:
        active_jobs = self._active_job_count()
        has_context = self._context.file_count > 0 or self._context.folder is not None
        dot = "●" if has_context else "○"
        if vertical:
            return str(min(active_jobs, 9)) if active_jobs else dot
        suffix = f"{active_jobs} 工作" if active_jobs else "Ctrl+K"
        return f"{dot} 工具 {suffix}"

    def _tail_tooltip(self) -> str:
        active_jobs = self._active_job_count()
        has_context = self._context.file_count > 0 or self._context.folder is not None
        context_text = "已有 Context" if has_context else "目前沒有 Context"
        job_text = f"{active_jobs} 個工作進行中" if active_jobs else "沒有工作進行中"
        return f"展開工程工具列\n{context_text}\n{job_text}\n快捷鍵：Ctrl+K\n按住 Alt 拖曳可移動尾巴位置"

    def _refresh_tail(self) -> None:
        edge = self._positioner.normalize_edge(self._state_store.edge)
        self._sync_tail_visibility(edge)

    def _active_job_count(self) -> int:
        return sum(1 for thread in self._threads if thread.isRunning())

    def _tail_offset_for_edge(self, edge: str) -> float:
        if self._tail_drag_edge == edge and self._tail_drag_offset is not None:
            return self._tail_drag_offset
        return self._state_store.tail_offset(edge)

    def _move_tail_to_global(self, global_position: QPoint, *, commit: bool) -> None:
        edge = self._tail_drag_edge or self._positioner.normalize_edge(self._state_store.edge)
        screen = QApplication.screenAt(global_position) or self._target_screen()
        if screen is None:
            return
        area = screen_area_from_qrect(screen.availableGeometry())
        offset = _tail_offset_from_point(area, edge, global_position.x(), global_position.y())
        if commit:
            self._state_store.set_screen_name(screen.name())
            self._state_store.set_tail_offset(edge, offset)
        else:
            self._tail_drag_offset = offset
        self._snap_to_edge()

    def _target_screen(self):
        screen_name = self._state_store.screen_name
        for screen in QApplication.screens():
            if screen.name() == screen_name:
                return screen
        return QApplication.primaryScreen() or QApplication.screenAt(QCursor.pos())

    def _path_icon(self, path: Path) -> QIcon:
        return self._icon_provider.icon(QFileInfo(str(path)))

    def _open_path(self, path: Path) -> None:
        os.startfile(path)  # noqa: S606

    def _reveal_path(self, path: Path) -> None:
        if path.is_dir():
            os.startfile(path)  # noqa: S606
        else:
            subprocess.Popen(["explorer.exe", f"/select,{path}"])

    def _open_powershell(self, folder: Path) -> None:
        shell = "pwsh.exe"
        try:
            subprocess.Popen([shell, "-NoExit"], cwd=str(folder))
        except FileNotFoundError:
            subprocess.Popen(["powershell.exe", "-NoExit"], cwd=str(folder))

    def _poll_context_inbox(self) -> None:
        if hasattr(self._context_inbox, "take_request"):
            request = self._context_inbox.take_request()
        else:
            context = self._context_inbox.take()
            request = _ContextWakeRequest(command="context", context=context) if context is not None else None
        if request is None:
            return
        context = getattr(request, "context", None)
        if context is not None:
            self._use_context(context, record=True)
        self.show()
        self.raise_()
        self.activateWindow()
        if self._state_store.auto_hide_enabled:
            self._set_collapsed(False)
            self._hide_timer.start(1800)

    def _apply_style(self) -> None:
        self.setStyleSheet(dock_stylesheet(self._theme()))

    def _theme(self) -> Theme:
        return theme_by_name(self._state_store.theme_name)


def _source_label(source: str) -> str:
    labels = {
        "explorer.foreground": "Explorer",
        "explorer.topmost": "Explorer",
        "explorer.window": "Explorer",
        "explorer.menu": "右鍵",
        "explorer": "Explorer",
        "drop": "拖放",
        "picker.folder": "手動資料夾",
        "picker.files": "手動檔案",
        "picker": "選取",
        "manual.cwd": "手動",
        "fallback.cwd": "備援",
        "recent.file": "最近檔案",
        "recent.folder": "最近資料夾",
        "self-test": "測試",
    }
    return labels.get(source, source.replace(".", " "))


class _ContextWakeRequest:
    def __init__(self, *, command: str, context: LauncherContext | None = None) -> None:
        self.command = command
        self.context = context


def _source_kind(context: LauncherContext) -> str:
    if context.file_count == 0 and context.folder is None:
        return "empty"
    source = context.source
    if source.startswith("explorer"):
        return "explorer"
    if source.startswith("picker") or source.startswith("manual") or source.startswith("fallback"):
        return "manual"
    if source.startswith("recent"):
        return "recent"
    if source == "drop":
        return "drop"
    return "manual"


def _context_indicator(context: LauncherContext) -> str:
    return "○" if _source_kind(context) == "empty" else "●"


def _tail_offset_from_point(area, edge: str, point_x: int, point_y: int) -> float:  # noqa: ANN001
    if edge in {"top", "bottom"}:
        tail_size = 160
        available = max(1, area.width - tail_size)
        value = (point_x - area.x - tail_size / 2) / available
    else:
        tail_size = 132
        available = max(1, area.height - tail_size)
        value = (point_y - area.y - tail_size / 2) / available
    return min(max(float(value), 0.0), 1.0)


def _folder_menu_label(path: Path) -> str:
    return _compact_path(path)


def _explorer_context_label(context: LauncherContext) -> str:
    if context.file_count:
        folder = context.folder or context.files[0].parent
        return f"{context.file_count} 個檔案 @ {_compact_path(folder)}"
    if context.folder:
        return _compact_path(context.folder)
    return "Explorer：沒有位置"


def _context_tooltip(context: LauncherContext) -> str:
    lines = [f"來源：{context.source}"]
    if context.folder:
        lines.append(f"資料夾：{context.folder}")
    if context.files:
        lines.append("檔案：")
        lines.extend(str(path) for path in context.files[:20])
    return "\n".join(lines)


def _compact_path(path: Path | None) -> str:
    if path is None:
        return "沒有資料夾"
    text = str(path)
    if len(text) <= 70:
        return text
    parts = path.parts
    if len(parts) <= 4:
        return text
    return str(Path(parts[0], "...", *parts[-3:]))
