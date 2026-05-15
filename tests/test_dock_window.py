from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from launcher.core.context_inbox import ContextInbox  # noqa: E402
from launcher.core.context_model import LauncherContext  # noqa: E402
from launcher.core.context_service import ContextService  # noqa: E402
from launcher.core.registry import ActionRegistry  # noqa: E402
from launcher.core.runner import ActionRunner  # noqa: E402
from launcher.core.state_store import AppStateStore  # noqa: E402
from launcher.ui.dock_window import DockWindow, _tail_offset_from_point  # noqa: E402
from launcher.ui.edge_positioner import ScreenArea  # noqa: E402


class DockWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_apply_dock_preferences_expands_when_auto_hide_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            state.set_auto_hide_enabled(True)
            window = _make_window(state)
            window._set_collapsed(True)

            state.set_auto_hide_enabled(False)
            window._apply_dock_preferences()

            self.assertFalse(window._collapsed)

    def test_toolbar_uses_merged_recent_and_overflow_buttons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            window = _make_window(state)

            labels = [button.text() for button in window._toolbar_buttons]

            self.assertIn("近期", labels)
            self.assertIn("更多", labels)
            self.assertNotIn("最近指令", labels)
            self.assertNotIn("最近檔案", labels)
            self.assertNotIn("最近資料夾", labels)

    def test_tail_text_reflects_empty_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            window = _make_window(state)

            self.assertEqual(window._tail_text(vertical=False), "○ 工具 Ctrl+K")
            self.assertEqual(window._tail_text(vertical=True), "○")
            self.assertTrue(window._context_label.text().startswith("○ "))

    def test_context_chip_and_tail_expose_source_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            window = _make_window(state)

            window._use_context(LauncherContext(folder=Path("C:/Work"), source="explorer.foreground"), record=False)
            window._set_collapsed(True)

            self.assertTrue(window._context_label.text().startswith("● Explorer"))
            self.assertEqual(window._context_label.property("sourceKind"), "explorer")
            self.assertEqual(window._tail_button.property("sourceKind"), "explorer")
            self.assertEqual(window._tail_button.property("activeJobs"), "false")

    def test_vertical_tail_uses_single_glyph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            window = _make_window(state)
            state.set_edge("left")
            state.set_auto_hide_enabled(True)

            window._set_collapsed(True)

            self.assertEqual(window._tail_button.text(), "○")
            self.assertEqual(window._tail_button.size().width(), 18)
            self.assertEqual(window._tail_button.size().height(), 132)
            self.assertIn("Alt", window._tail_button.toolTip())

    def test_collapsed_tail_uses_saved_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            state.set_auto_hide_enabled(True)
            state.set_tail_offset("top", 0.0)
            window = _make_window(state)

            window._set_collapsed(True)

            self.assertLess(window.x(), 100)

    def test_hovering_collapsed_tail_does_not_expand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            state.set_auto_hide_enabled(True)
            window = _make_window(state)
            window._set_collapsed(True)

            window._handle_dock_enter()

            self.assertTrue(window._collapsed)

    def test_tail_offset_from_point_tracks_current_edge_axis(self) -> None:
        area = ScreenArea(x=100, y=50, width=1920, height=1040)

        self.assertEqual(_tail_offset_from_point(area, "top", 180, 60), 0.0)
        self.assertAlmostEqual(_tail_offset_from_point(area, "top", 980 + 80, 60), 0.5, places=2)
        self.assertEqual(_tail_offset_from_point(area, "right", 2010, 1160), 1.0)

    def test_drop_target_hint_is_toggled_with_drop_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = AppStateStore(Path(tmp) / "state.json")
            window = _make_window(state)
            window._set_collapsed(False)

            window._set_drop_target_active(True)

            self.assertFalse(window._drop_hint.isHidden())
            self.assertTrue(window.property("dropTarget"))

            window._set_drop_target_active(False)

            self.assertTrue(window._drop_hint.isHidden())
            self.assertFalse(window.property("dropTarget"))


def _make_window(state: AppStateStore) -> DockWindow:
    registry = ActionRegistry(Path("missing-plugins"))
    registry.load()
    return DockWindow(
        registry=registry,
        runner=ActionRunner(),
        context_service=_FixedContextService(),
        context_inbox=ContextInbox(),
        state_store=state,
    )


class _FixedContextService(ContextService):
    def current_context(self) -> LauncherContext:
        return LauncherContext.empty()


if __name__ == "__main__":
    unittest.main()
