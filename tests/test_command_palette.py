from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QListWidget  # noqa: E402

from launcher.core.action_model import ActionAccepts, ActionDefinition, CommandSpec  # noqa: E402
from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.ui.command_palette import ActionRequest, CommandPalette  # noqa: E402


class CommandPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_palette_uses_two_column_layout_with_action_preview(self) -> None:
        registry = _Registry(
            [
                _action("copy.names", "複製檔名", "系統", "複製目前檔案名稱"),
                _action("pdf.iso", "ISO PDF 命名工作台", "PDF", "拆頁、判讀流水號並產生命名草稿"),
            ]
        )

        palette = CommandPalette(registry, LauncherContext.empty(), recent_action_ids=["pdf.iso"])

        list_widget = palette.findChild(QListWidget, "PaletteList")
        preview_title = palette.findChild(QLabel, "PalettePreviewTitle")
        context_bar = palette.findChild(QLabel, "PaletteContextBar")

        self.assertIsNotNone(list_widget)
        self.assertIsNotNone(preview_title)
        self.assertIsNotNone(context_bar)
        assert list_widget is not None
        self.assertEqual(list_widget.item(0).text(), "")
        self.assertEqual(list_widget.item(1).text(), "")
        row_widget = list_widget.itemWidget(list_widget.item(1))
        self.assertIsNotNone(row_widget)
        assert row_widget is not None
        header_widget = list_widget.itemWidget(list_widget.item(0))
        self.assertIsNotNone(header_widget)
        assert header_widget is not None
        header_labels = [label.text() for label in header_widget.findChildren(QLabel)]
        self.assertIn("最近使用", header_labels)
        self.assertIn("1", header_labels)
        row_labels = [label.text() for label in row_widget.findChildren(QLabel)]
        self.assertIn("ISO PDF 命名工作台", row_labels)
        self.assertIn("PDF", row_labels)
        self.assertIn("Ctrl+1", row_labels)
        self.assertIn("最近", row_labels)
        self.assertIn("Ctrl+1", list_widget.item(1).data(Qt.ItemDataRole.UserRole + 1))
        self.assertEqual(preview_title.text(), "ISO PDF 命名工作台")
        self.assertIn("Context ·", context_bar.text())

    def test_palette_empty_search_updates_preview_panel(self) -> None:
        registry = _Registry([_action("copy.names", "複製檔名", "系統", "複製目前檔案名稱")])
        palette = CommandPalette(registry, LauncherContext.empty())

        palette._query.setText("zzzz")

        self.assertEqual(palette._preview_title.text(), "沒有可執行指令")
        self.assertIn("沒有匹配", palette._list.item(0).text())

    def test_palette_hides_dev_only_actions_without_developer_mode(self) -> None:
        registry = _Registry(
            [
                _action("diagnostics.echo_context", "顯示目前 Context", "診斷", "顯示 context"),
                _action("diagnostics.wait_cancel", "測試取消：等待 30 秒", "診斷", "測試取消"),
            ]
        )

        palette = CommandPalette(registry, LauncherContext.empty(), developer_mode=False)

        self.assertIn("diagnostics.echo_context", palette._shortcut_action_ids)
        self.assertNotIn("diagnostics.wait_cancel", palette._shortcut_action_ids)

    def test_palette_shows_dev_only_actions_in_developer_mode(self) -> None:
        registry = _Registry(
            [
                _action("diagnostics.echo_context", "顯示目前 Context", "診斷", "顯示 context"),
                _action("diagnostics.wait_cancel", "測試取消：等待 30 秒", "診斷", "測試取消"),
            ]
        )

        palette = CommandPalette(registry, LauncherContext.empty(), developer_mode=True)

        self.assertIn("diagnostics.echo_context", palette._shortcut_action_ids)
        self.assertIn("diagnostics.wait_cancel", palette._shortcut_action_ids)

    def test_copy_selection_shortcut_emits_default_action_request(self) -> None:
        registry = _Registry(
            [
                _action(
                    "copy.selection",
                    "複製選取項目",
                    "剪貼簿",
                    "依模式複製選取項目",
                    accepts=ActionAccepts(min_files=1),
                )
            ]
        )
        palette = CommandPalette(registry, LauncherContext.from_paths(["C:/Work/A-101.pdf"], source="test"))
        emitted: list[object] = []
        palette.action_requested.connect(emitted.append)

        palette._run_selected(skip_options=True)

        self.assertEqual(len(emitted), 1)
        self.assertIsInstance(emitted[0], ActionRequest)
        request = emitted[0]
        assert isinstance(request, ActionRequest)
        self.assertEqual(request.action.id, "copy.selection")
        self.assertEqual(request.options, {"mode": "path"})

    def test_copy_folder_listing_shortcut_emits_default_action_request(self) -> None:
        registry = _Registry(
            [
                _action(
                    "copy.folder_listing",
                    "複製資料夾清單",
                    "剪貼簿",
                    "依模式複製資料夾清單",
                    accepts=ActionAccepts(requires_folder=True),
                )
            ]
        )
        palette = CommandPalette(registry, LauncherContext(folder=Path("C:/Work"), source="test"))
        emitted: list[object] = []
        palette.action_requested.connect(emitted.append)

        palette._run_selected(skip_options=True)

        self.assertEqual(len(emitted), 1)
        self.assertIsInstance(emitted[0], ActionRequest)
        request = emitted[0]
        assert isinstance(request, ActionRequest)
        self.assertEqual(request.action.id, "copy.folder_listing")
        self.assertEqual(request.options, {"include": "all", "mode": "name"})


class _Registry:
    def __init__(self, actions: list[ActionDefinition]) -> None:
        self.actions = {action.id: action for action in actions}

    def matching_actions(self, _context: LauncherContext) -> list[ActionDefinition]:
        return list(self.actions.values())

    def visible_actions(self, *, developer_mode: bool) -> list[ActionDefinition]:
        if developer_mode:
            return list(self.actions.values())
        return [action for action in self.actions.values() if action.id != "diagnostics.wait_cancel"]

    def matching_visible_actions(self, context: LauncherContext, *, developer_mode: bool) -> list[ActionDefinition]:
        return [action for action in self.visible_actions(developer_mode=developer_mode) if action.matches(context)]


def _action(
    action_id: str,
    title: str,
    category: str,
    description: str,
    *,
    accepts: ActionAccepts | None = None,
) -> ActionDefinition:
    return ActionDefinition(
        id=action_id,
        title=title,
        category=category,
        description=description,
        plugin_id=category.lower(),
        accepts=accepts or ActionAccepts(),
        command=CommandSpec(type="noop"),
    )


if __name__ == "__main__":
    unittest.main()
