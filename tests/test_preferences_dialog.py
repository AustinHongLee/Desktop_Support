from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.state_store import AppStateStore  # noqa: E402
from launcher.ui.preferences_dialog import PreferencesDialog  # noqa: E402


class PreferencesDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_dialog_reflects_state_store_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.set_dock_preferences(
                edge="left",
                screen_name="DISPLAY2",
                auto_hide_enabled=False,
                auto_hide_delay_ms=2200,
            )

            dialog = PreferencesDialog(store, screen_names=["DISPLAY1", "DISPLAY2"])
            preferences = dialog.preferences()

            self.assertEqual(preferences.edge, "left")
            self.assertEqual(preferences.screen_name, "DISPLAY2")
            self.assertFalse(preferences.auto_hide_enabled)
            self.assertEqual(preferences.auto_hide_delay_ms, 2200)
            self.assertEqual(preferences.theme_name, "graphite-light")
            self.assertFalse(preferences.developer_mode)

    def test_dialog_reflects_theme_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.set_theme_name("engineering-blue-2")

            dialog = PreferencesDialog(store, screen_names=[])
            preferences = dialog.preferences()

            self.assertEqual(preferences.theme_name, "engineering-blue-2")

    def test_dialog_reflects_developer_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.set_developer_mode(True)

            dialog = PreferencesDialog(store, screen_names=[])
            preferences = dialog.preferences()

            self.assertTrue(preferences.developer_mode)


if __name__ == "__main__":
    unittest.main()
