from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from launcher.core.context_model import LauncherContext
from launcher.core.paths import plugin_root
from launcher.core.registry import ActionRegistry


class RegistryTests(unittest.TestCase):
    def test_registry_loads_builtin_copy_actions(self) -> None:
        registry = ActionRegistry(plugin_root())
        registry.load()

        self.assertIn("copy.selection", registry.actions)
        self.assertIn("copy.folder_listing", registry.actions)
        self.assertIn("copy.folder_path", registry.actions)
        self.assertNotIn("copy.full_paths", registry.actions)
        self.assertNotIn("copy.folder_file_base_names", registry.actions)
        self.assertIn("system.open_powershell", registry.actions)
        self.assertIn("system.write_file_list", registry.actions)
        self.assertIn("rename.ui_table", registry.actions)
        self.assertIn("rename.selected_from_clipboard", registry.actions)
        self.assertIn("pdf.split_pages", registry.actions)
        self.assertIn("iso.pdf_page_naming", registry.actions)
        self.assertIn("diagnostics.wait_cancel", registry.actions)
        self.assertIn("diagnostics.wait_timeout", registry.actions)

    def test_visible_actions_hide_dev_only_diagnostics_by_default(self) -> None:
        registry = ActionRegistry(plugin_root())
        registry.load()

        action_ids = {action.id for action in registry.visible_actions(developer_mode=False)}

        self.assertIn("diagnostics.echo_context", action_ids)
        self.assertNotIn("diagnostics.wait_cancel", action_ids)
        self.assertNotIn("diagnostics.wait_timeout", action_ids)

    def test_visible_actions_show_dev_only_diagnostics_in_developer_mode(self) -> None:
        registry = ActionRegistry(plugin_root())
        registry.load()

        action_ids = {action.id for action in registry.visible_actions(developer_mode=True)}

        self.assertIn("diagnostics.echo_context", action_ids)
        self.assertIn("diagnostics.wait_cancel", action_ids)
        self.assertIn("diagnostics.wait_timeout", action_ids)

    def test_actions_match_file_context(self) -> None:
        registry = ActionRegistry(plugin_root())
        registry.load()
        context = LauncherContext.from_paths(["C:/Work/A.pdf"], source="test")

        action_ids = {action.id for action in registry.matching_actions(context)}

        self.assertIn("copy.selection", action_ids)
        self.assertIn("copy.folder_path", action_ids)

    def test_actions_requiring_files_do_not_match_empty_context(self) -> None:
        registry = ActionRegistry(plugin_root())
        registry.load()
        context = LauncherContext.empty()

        action_ids = {action.id for action in registry.matching_actions(context)}

        self.assertNotIn("copy.selection", action_ids)
        self.assertNotIn("copy.folder_path", action_ids)

    def test_folder_action_matches_folder_context(self) -> None:
        registry = ActionRegistry(plugin_root())
        registry.load()
        context = LauncherContext(folder=Path("C:/Work"), source="test")

        action_ids = {action.id for action in registry.matching_actions(context)}

        self.assertIn("copy.folder_path", action_ids)
        self.assertIn("copy.folder_listing", action_ids)

    def test_load_skips_broken_plugin_and_reports_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_plugin(root, "good", "Good", [_action("good.echo")])
            broken = root / "broken"
            broken.mkdir()
            (broken / "plugin.json").write_text('{"id": "broken", "title": "Broken"}', encoding="utf-8")
            (broken / "actions.json").write_text("{not json", encoding="utf-8")

            registry = ActionRegistry(root)
            report = registry.load()

            self.assertIn("good.echo", registry.actions)
            self.assertNotIn("broken", registry.plugins)
            self.assertFalse(report.ok)
            self.assertEqual(len(report.issues), 1)

    def test_load_reports_duplicate_action_id_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_plugin(root, "one", "One", [_action("shared.action")])
            _write_plugin(root, "two", "Two", [_action("shared.action")])

            registry = ActionRegistry(root)
            report = registry.load()

            self.assertIn("shared.action", registry.actions)
            self.assertFalse(report.ok)
            self.assertEqual(len(report.issues), 1)

    def test_reload_updates_actions_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_plugin(root, "one", "One", [_action("one.before")])
            registry = ActionRegistry(root)
            registry.load()

            _write_plugin(root, "one", "One", [_action("one.after")])
            report = registry.reload()

            self.assertTrue(report.ok)
            self.assertNotIn("one.before", registry.actions)
            self.assertIn("one.after", registry.actions)

def _write_plugin(root: Path, plugin_id: str, title: str, actions: list[dict[str, object]]) -> None:
    plugin_path = root / plugin_id
    plugin_path.mkdir(exist_ok=True)
    (plugin_path / "plugin.json").write_text(
        json.dumps({"id": plugin_id, "title": title}, ensure_ascii=False),
        encoding="utf-8",
    )
    (plugin_path / "actions.json").write_text(
        json.dumps({"actions": actions}, ensure_ascii=False),
        encoding="utf-8",
    )


def _action(action_id: str) -> dict[str, object]:
    return {
        "id": action_id,
        "title": action_id,
        "category": "測試",
        "command": {
            "type": "python_module",
            "module": "launcher.plugins.diagnostics.echo_context",
            "entry": "echo_context",
        },
    }


if __name__ == "__main__":
    unittest.main()
