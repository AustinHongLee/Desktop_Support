from __future__ import annotations

import unittest

from launcher.core.action_model import ActionDefinition, CommandSpec
from launcher.ui.palette_search import rank_actions


def _action(action_id: str, title: str, category: str, description: str = "") -> ActionDefinition:
    return ActionDefinition(
        id=action_id,
        title=title,
        category=category,
        description=description,
        plugin_id=category.lower(),
        command=CommandSpec(type="noop"),
    )


class PaletteSearchTests(unittest.TestCase):
    def test_exact_title_match_ranks_first(self) -> None:
        actions = [
            _action("copy.full_paths", "複製完整路徑", "複製"),
            _action("system.open_powershell", "在此開啟 PowerShell", "系統"),
        ]

        matches = rank_actions(actions, "powershell")

        self.assertEqual(matches[0].action.id, "system.open_powershell")

    def test_subsequence_match_handles_short_queries(self) -> None:
        actions = [
            _action("copy.folder_file_base_names", "複製目前資料夾檔案 basename", "複製"),
            _action("pdf.split_pages", "PDF 分割單頁", "PDF"),
        ]

        matches = rank_actions(actions, "pds")

        self.assertEqual(matches[0].action.id, "pdf.split_pages")

    def test_recent_actions_are_weighted_when_query_is_empty(self) -> None:
        actions = [
            _action("a.old", "舊指令", "測試"),
            _action("a.recent", "最近指令", "測試"),
        ]

        matches = rank_actions(actions, "", recent_action_ids=["a.recent"])

        self.assertEqual(matches[0].action.id, "a.recent")

    def test_unmatched_query_is_filtered_out(self) -> None:
        actions = [_action("copy.full_paths", "複製完整路徑", "複製")]

        matches = rank_actions(actions, "zzzz")

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
