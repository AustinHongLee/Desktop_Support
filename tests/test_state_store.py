from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from launcher.core.context_model import LauncherContext
from launcher.core.state_store import AppStateStore


class StateStoreTests(unittest.TestCase):
    def test_recent_actions_are_unique_and_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.record_action("a.one", "One", "Test")
            store.record_action("a.two", "Two", "Test")
            store.record_action("a.one", "One", "Test")

            self.assertEqual([action.action_id for action in store.recent_actions()], ["a.one", "a.two"])

    def test_fallback_cwd_context_is_not_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.record_context(LauncherContext(folder=Path("C:/App"), source="fallback.cwd"))

            self.assertEqual(store.recent_contexts(), [])
            self.assertEqual(store.recent_folders(), [])

    def test_edge_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)
            store.set_edge("bottom")

            self.assertEqual(AppStateStore(path).edge, "bottom")

    def test_screen_name_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)
            store.set_screen_name("DISPLAY2")

            self.assertEqual(AppStateStore(path).screen_name, "DISPLAY2")

    def test_auto_hide_defaults_to_enabled_and_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            self.assertTrue(store.auto_hide_enabled)
            store.set_auto_hide_enabled(False)

            self.assertFalse(AppStateStore(path).auto_hide_enabled)

    def test_auto_hide_delay_defaults_clamps_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            self.assertEqual(store.auto_hide_delay_ms, 1500)
            store.set_auto_hide_delay_ms(12000)

            self.assertEqual(AppStateStore(path).auto_hide_delay_ms, 10000)

    def test_tail_offsets_are_edge_specific_clamped_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            self.assertEqual(store.tail_offset("top"), 0.5)
            store.set_tail_offset("top", 0.2)
            store.set_tail_offset("right", 2.0)

            restored = AppStateStore(path)
            self.assertEqual(restored.tail_offset("top"), 0.2)
            self.assertEqual(restored.tail_offset("right"), 1.0)
            self.assertEqual(restored.tail_offset("left"), 0.5)

    def test_dock_preferences_are_saved_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)
            store.set_dock_preferences(
                edge="right",
                screen_name=None,
                auto_hide_enabled=False,
                auto_hide_delay_ms=250,
                theme_name="engineering-blue-2",
            )

            restored = AppStateStore(path)
            self.assertEqual(restored.edge, "right")
            self.assertIsNone(restored.screen_name)
            self.assertFalse(restored.auto_hide_enabled)
            self.assertEqual(restored.auto_hide_delay_ms, 300)
            self.assertEqual(restored.theme_name, "engineering-blue-2")

    def test_theme_name_defaults_validates_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            self.assertEqual(store.theme_name, "graphite-light")
            store.set_theme_name("engineering-blue-2")

            self.assertEqual(AppStateStore(path).theme_name, "engineering-blue-2")
            with self.assertRaises(ValueError):
                store.set_theme_name("unknown")

    def test_developer_mode_defaults_false_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            self.assertFalse(store.developer_mode)
            store.set_developer_mode(True)

            self.assertTrue(AppStateStore(path).developer_mode)

    def test_iso_naming_profiles_are_lru_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            for index in range(55):
                folder = Path(tmp) / f"job-{index}"
                folder.mkdir()
                store.set_iso_naming_profile(folder, {"pattern": f"{index}.pdf"})

            self.assertIsNone(AppStateStore(path).iso_naming_profile(Path(tmp) / "job-0"))
            self.assertEqual(AppStateStore(path).iso_naming_profile(Path(tmp) / "job-54")["pattern"], "54.pdf")

    def test_recent_files_and_folders_are_recorded_from_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.record_context(
                LauncherContext.from_paths(
                    ["C:/Work/A.dwg", "C:/Work/B.pdf"],
                    folder="C:/Work",
                    source="explorer.test",
                )
            )

            self.assertEqual(store.recent_folders(), [Path("C:/Work")])
            self.assertEqual(store.recent_files(), [Path("C:/Work/A.dwg"), Path("C:/Work/B.pdf")])

    def test_recent_files_and_folders_can_be_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AppStateStore(Path(tmp) / "state.json")
            store.record_context(
                LauncherContext.from_paths(
                    ["C:/Work/A.dwg"],
                    folder="C:/Work",
                    source="explorer.test",
                )
            )

            store.clear_recent_files()
            store.clear_recent_folders()

            self.assertEqual(store.recent_files(), [])
            self.assertEqual(store.recent_folders(), [])

    def test_save_uses_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)

            with patch("launcher.core.state_store.os.replace") as replace:
                store.set_edge("left")

            replace.assert_called_once_with(path.with_name("state.json.tmp"), path)

    def test_save_writes_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = AppStateStore(path)
            store.set_edge("left")

            self.assertIn('"schema_version": 1', path.read_text(encoding="utf-8"))

    def test_invalid_json_loads_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")

            store = AppStateStore(path)

            self.assertEqual(store.edge, "top")

    def test_non_object_json_loads_empty_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("[]", encoding="utf-8")

            store = AppStateStore(path)

            self.assertEqual(store.recent_files(), [])


if __name__ == "__main__":
    unittest.main()
