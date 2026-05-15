from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.registry import ActionRegistry  # noqa: E402
from launcher.ui.plugin_manager_dialog import PluginManagerDialog  # noqa: E402


class PluginManagerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_shows_loaded_plugins_and_refreshes_after_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_plugin(root, "one", "One", ["one.action"])
            registry = ActionRegistry(root)
            registry.load()
            dialog = PluginManagerDialog(registry)

            self.assertEqual(dialog._table.rowCount(), 1)
            self.assertIn("1 個外掛", dialog._summary.text())

            _write_plugin(root, "two", "Two", ["two.action"])
            dialog.reload_plugins()

            self.assertEqual(dialog._table.rowCount(), 2)
            self.assertIn("2 個外掛", dialog._summary.text())


def _write_plugin(root: Path, plugin_id: str, title: str, action_ids: list[str]) -> None:
    plugin_path = root / plugin_id
    plugin_path.mkdir(exist_ok=True)
    (plugin_path / "plugin.json").write_text(
        json.dumps({"id": plugin_id, "title": title}, ensure_ascii=False),
        encoding="utf-8",
    )
    actions = [
        {
            "id": action_id,
            "title": action_id,
            "category": "測試",
            "command": {
                "type": "python_module",
                "module": "launcher.plugins.diagnostics.echo_context",
                "entry": "echo_context",
            },
        }
        for action_id in action_ids
    ]
    (plugin_path / "actions.json").write_text(
        json.dumps({"actions": actions}, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
