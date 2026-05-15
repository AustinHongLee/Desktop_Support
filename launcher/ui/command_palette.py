from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from launcher.core.action_model import ActionDefinition
from launcher.core.context_model import LauncherContext
from launcher.core.registry import ActionRegistry
from launcher.ui.copy_options_dialog import CopyFolderListingOptionsDialog, CopySelectionOptionsDialog
from launcher.ui.palette_search import PaletteMatch, rank_actions
from launcher.ui.theme import Theme, palette_stylesheet


@dataclass(frozen=True)
class ActionRequest:
    action: ActionDefinition
    options: dict[str, Any]


class CommandPalette(QDialog):
    action_requested = pyqtSignal(object)

    def __init__(
        self,
        registry: ActionRegistry,
        context: LauncherContext,
        *,
        recent_action_ids: list[str] | None = None,
        theme: Theme | None = None,
        developer_mode: bool = False,
    ) -> None:
        super().__init__()
        self._registry = registry
        self._context = context
        self._recent_action_ids = recent_action_ids or []
        self._theme = theme
        self._developer_mode = developer_mode
        self._visible_actions: list[ActionDefinition] = []
        self._shortcut_action_ids: list[str] = []

        self.setWindowTitle("指令面板")
        self.setMinimumSize(780, 460)
        self.resize(840, 500)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        self._query = QLineEdit()
        self._query.setObjectName("PaletteSearch")
        self._query.setPlaceholderText("搜尋指令...")
        self._query.installEventFilter(self)
        self._list = QListWidget()
        self._list.setObjectName("PaletteList")
        self._list.setSpacing(4)
        self._list.installEventFilter(self)
        self._context_label = QLabel(_context_summary(context))
        self._context_label.setObjectName("PaletteContextBar")
        self._context_label.setWordWrap(True)
        self._preview_title = QLabel("選擇一個指令")
        self._preview_title.setObjectName("PalettePreviewTitle")
        self._preview_title.setWordWrap(True)
        self._preview_meta = QLabel("")
        self._preview_meta.setObjectName("PalettePreviewMeta")
        self._preview_meta.setWordWrap(True)
        self._preview_description = QLabel("左側選取指令後，這裡會顯示用途、條件與快捷鍵。")
        self._preview_description.setObjectName("PalettePreviewDescription")
        self._preview_description.setWordWrap(True)
        self._preview_accepts = QLabel("")
        self._preview_accepts.setObjectName("PalettePreviewHint")
        self._preview_accepts.setWordWrap(True)
        self._preview_shortcut = QLabel("Enter 執行 / Esc 關閉")
        self._preview_shortcut.setObjectName("KeyboardHint")
        self._preview_shortcut.setWordWrap(True)
        self._preview_command = QLabel("")
        self._preview_command.setObjectName("PalettePreviewHint")
        self._preview_command.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self._query)
        layout.addWidget(self._context_label)
        layout.addLayout(self._build_content_layout(), 1)

        self._query.textChanged.connect(self._refresh)
        self._query.returnPressed.connect(lambda: self._run_selected())
        self._list.itemDoubleClicked.connect(lambda _item: self._run_selected())
        self._list.currentItemChanged.connect(lambda current, _previous: self._update_preview_for_item(current))
        for index in range(1, 10):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda selected=index: self._run_visible_index(selected - 1))
        self._apply_style()
        self._refresh()

    def eventFilter(self, watched, event) -> bool:  # noqa: ANN001
        if watched is self._query and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_selected(skip_options=bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
                return True
            if key == Qt.Key.Key_Down:
                self._move_selection(1)
                return True
            if key == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
            if key == Qt.Key.Key_Escape:
                if self._query.text():
                    self._query.clear()
                else:
                    self.reject()
                return True
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Right):
                self._list.setFocus()
                return True
        if watched is self._list and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._run_selected(skip_options=bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier))
                return True
            if key == Qt.Key.Key_Left:
                self._query.setFocus()
                self._query.selectAll()
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:  # noqa: ANN001
        super().showEvent(event)
        self._query.setFocus()
        self._query.selectAll()

    def _refresh(self) -> None:
        query = self._query.text().strip()
        actions = _matching_visible_actions(self._registry, self._context, developer_mode=self._developer_mode)
        matches = rank_actions(actions, query, recent_action_ids=self._recent_action_ids)
        groups, ordered_actions = _display_groups(matches, recent_action_ids=self._recent_action_ids)
        self._visible_actions = ordered_actions
        self._shortcut_action_ids = [action.id for action in ordered_actions[:9]]
        self._list.clear()
        if not matches:
            empty = QListWidgetItem("沒有匹配。試試 pdf、copy、rename")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            empty.setForeground(QColor("#607080"))
            self._list.addItem(empty)
            self._update_preview_for_action(None)
            return
        display_index = 1
        recent_ids = set(self._recent_action_ids)
        for category, grouped_matches in groups.items():
            header = QListWidgetItem("")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            header.setForeground(QColor("#506070"))
            header.setToolTip(f"{category} ({len(grouped_matches)})")
            header.setSizeHint(QSize(0, 28))
            self._list.addItem(header)
            self._list.setItemWidget(header, _group_header_widget(category, len(grouped_matches)))
            for match in grouped_matches:
                action = match.action
                shortcut = f"Ctrl+{display_index}" if display_index <= 9 else ""
                recent = action.id in recent_ids
                item = QListWidgetItem("")
                item.setData(Qt.ItemDataRole.UserRole, action.id)
                item.setData(Qt.ItemDataRole.UserRole + 1, _action_item_text(action, shortcut=shortcut, recent=recent))
                item.setToolTip(action.description or action.id)
                item.setSizeHint(QSize(0, 70))
                self._list.addItem(item)
                self._list.setItemWidget(item, _action_row_widget(action, shortcut=shortcut, recent=recent))
                display_index += 1
        if self._list.count():
            self._select_first_action()

    def _run_selected(self, *, skip_options: bool = False) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        action_id = item.data(Qt.ItemDataRole.UserRole)
        if action_id is None:
            self._move_selection(1)
            item = self._list.currentItem()
            action_id = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if action_id is None:
            return
        action = self._registry.actions.get(action_id)
        if action is None:
            return
        request = self._build_action_request(action, skip_options=skip_options)
        if request is None:
            return
        self.action_requested.emit(request)
        self.accept()

    def _run_visible_index(self, index: int) -> None:
        if index < 0 or index >= len(self._shortcut_action_ids):
            return
        action = self._registry.actions.get(self._shortcut_action_ids[index])
        if action is None:
            return
        request = self._build_action_request(action, skip_options=True)
        if request is None:
            return
        self.action_requested.emit(request)
        self.accept()

    def _move_selection(self, delta: int) -> None:
        if not self._list.count() or not self._shortcut_action_ids:
            return
        row = self._list.currentRow()
        if row < 0:
            row = 0 if delta >= 0 else self._list.count() - 1
        for step in range(1, self._list.count() + 1):
            next_row = (row + delta * step) % self._list.count()
            item = self._list.item(next_row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self._list.setCurrentRow(next_row)
                return

    def _select_first_action(self) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) is not None:
                self._list.setCurrentRow(row)
                return

    def _apply_style(self) -> None:
        self.setStyleSheet(palette_stylesheet(self._theme) if self._theme is not None else palette_stylesheet())

    def _build_action_request(self, action: ActionDefinition, *, skip_options: bool) -> ActionDefinition | ActionRequest | None:
        if action.id == "copy.selection":
            if skip_options:
                return ActionRequest(action, CopySelectionOptionsDialog.default_options())
            dialog = CopySelectionOptionsDialog(parent=self, theme=self._theme)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return ActionRequest(action, dialog.options())
        if action.id == "copy.folder_listing":
            if skip_options:
                return ActionRequest(action, CopyFolderListingOptionsDialog.default_options())
            dialog = CopyFolderListingOptionsDialog(parent=self, theme=self._theme)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            return ActionRequest(action, dialog.options())
        return action

    def _build_content_layout(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)
        layout.addWidget(self._list, 3)
        layout.addWidget(self._build_preview_panel(), 2)
        return layout

    def _build_preview_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("PalettePreview")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(self._preview_title)
        layout.addWidget(self._preview_meta)
        layout.addWidget(_preview_section("用途"))
        layout.addWidget(self._preview_description)
        layout.addWidget(_preview_section("條件"))
        layout.addWidget(self._preview_accepts)
        layout.addWidget(_preview_section("執行"))
        layout.addWidget(self._preview_shortcut)
        layout.addWidget(self._preview_command)
        layout.addStretch(1)
        return panel

    def _update_preview_for_item(self, item: QListWidgetItem | None) -> None:
        action = None
        if item is not None:
            action_id = item.data(Qt.ItemDataRole.UserRole)
            if action_id is not None:
                action = self._registry.actions.get(action_id)
        self._update_preview_for_action(action)

    def _update_preview_for_action(self, action: ActionDefinition | None) -> None:
        if action is None:
            self._preview_title.setText("沒有可執行指令")
            self._preview_meta.setText("")
            self._preview_description.setText("調整搜尋字或目前 context 後再試一次。")
            self._preview_accepts.setText("")
            self._preview_shortcut.setText("Esc 關閉")
            self._preview_command.setText("")
            return
        self._preview_title.setText(action.title)
        self._preview_meta.setText(f"{action.category} · {action.plugin_id}")
        self._preview_description.setText(action.description or action.id)
        self._preview_accepts.setText(_accepts_summary(action))
        self._preview_shortcut.setText(_shortcut_summary(action.id, self._shortcut_action_ids))
        self._preview_command.setText(_command_summary(action))


def _group_matches(matches: list[PaletteMatch]) -> OrderedDict[str, list[PaletteMatch]]:
    groups: OrderedDict[str, list[PaletteMatch]] = OrderedDict()
    for match in matches:
        groups.setdefault(match.action.category, []).append(match)
    return groups


def _matching_visible_actions(registry: ActionRegistry, context: LauncherContext, *, developer_mode: bool) -> list[ActionDefinition]:
    if hasattr(registry, "matching_visible_actions"):
        return registry.matching_visible_actions(context, developer_mode=developer_mode)
    return registry.matching_actions(context)


def _display_groups(
    matches: list[PaletteMatch],
    *,
    recent_action_ids: list[str],
) -> tuple[OrderedDict[str, list[PaletteMatch]], list[ActionDefinition]]:
    recent_ids = set(recent_action_ids)
    groups: OrderedDict[str, list[PaletteMatch]] = OrderedDict()
    if recent_ids:
        recent_matches = [match for match in matches if match.action.id in recent_ids]
        if recent_matches:
            groups["最近使用"] = recent_matches
    for category, grouped_matches in _group_matches([match for match in matches if match.action.id not in recent_ids]).items():
        groups[category] = grouped_matches
    ordered_actions = [match.action for grouped_matches in groups.values() for match in grouped_matches]
    return groups, ordered_actions


def _context_summary(context: LauncherContext) -> str:
    if context.file_count:
        folder = f" · {context.folder}" if context.folder else ""
        return f"Context · {context.source} · {context.file_count} 個檔案{folder}"
    if context.folder:
        return f"Context · {context.source} · {context.folder}"
    return "Context · 沒有位置"


def _action_item_text(action: ActionDefinition, *, shortcut: str, recent: bool) -> str:
    hint = f"    {shortcut}" if shortcut else ""
    recent_text = "    最近" if recent else ""
    return f"{action.title}{hint}    [{action.category}]{recent_text}"


def _group_header_widget(category: str, count: int) -> QWidget:
    widget = QWidget()
    widget.setObjectName("PaletteGroupHeader")
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(8, 4, 8, 4)
    layout.setSpacing(8)
    label = QLabel(f"{category}")
    label.setObjectName("PaletteGroupHeaderText")
    count_label = QLabel(str(count))
    count_label.setObjectName("PaletteCountPill")
    layout.addWidget(label)
    layout.addWidget(count_label)
    layout.addStretch(1)
    return widget


def _action_row_widget(action: ActionDefinition, *, shortcut: str, recent: bool) -> QWidget:
    widget = QWidget()
    widget.setObjectName("PaletteActionRow")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(4)

    title_row = QHBoxLayout()
    title_row.setContentsMargins(0, 0, 0, 0)
    title_row.setSpacing(6)
    title = QLabel(action.title)
    title.setObjectName("PaletteActionTitle")
    title.setWordWrap(False)
    title_row.addWidget(title, 1)
    if shortcut:
        shortcut_label = QLabel(shortcut)
        shortcut_label.setObjectName("PaletteShortcutPill")
        title_row.addWidget(shortcut_label)
    category = QLabel(action.category)
    category.setObjectName("PaletteCategoryPill")
    title_row.addWidget(category)
    if recent:
        recent_label = QLabel("最近")
        recent_label.setObjectName("PaletteRecentPill")
        title_row.addWidget(recent_label)
    layout.addLayout(title_row)

    description = QLabel(action.description or action.id)
    description.setObjectName("PaletteActionDescription")
    description.setTextFormat(Qt.TextFormat.PlainText)
    description.setWordWrap(False)
    description.setToolTip(action.description or action.id)
    layout.addWidget(description)
    return widget


def _preview_section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PalettePreviewSection")
    return label


def _accepts_summary(action: ActionDefinition) -> str:
    accepts = action.accepts
    parts: list[str] = []
    if accepts.requires_folder:
        parts.append("需要目前資料夾")
    if accepts.min_files:
        if accepts.max_files is not None and accepts.max_files == accepts.min_files:
            parts.append(f"需要 {accepts.min_files} 個檔案")
        elif accepts.max_files is not None:
            parts.append(f"需要 {accepts.min_files}-{accepts.max_files} 個檔案")
        else:
            parts.append(f"至少 {accepts.min_files} 個檔案")
    elif accepts.max_files is not None:
        parts.append(f"最多 {accepts.max_files} 個檔案")
    if accepts.extensions:
        parts.append("副檔名 " + ", ".join(sorted(accepts.extensions)))
    return " · ".join(parts) if parts else "目前 context 可直接執行"


def _shortcut_summary(action_id: str, shortcut_action_ids: list[str]) -> str:
    try:
        index = shortcut_action_ids.index(action_id)
    except ValueError:
        return "Enter 執行"
    return f"Ctrl+{index + 1} 或 Enter 執行"


def _command_summary(action: ActionDefinition) -> str:
    command_type = action.command.type
    if action.command.type == "python" and action.command.module:
        command_type = f"python · {action.command.module}"
    elif action.command.type == "subprocess" and action.command.executable:
        command_type = f"subprocess · {action.command.executable}"
    return f"命令：{command_type}"
