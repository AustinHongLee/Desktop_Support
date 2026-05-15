from __future__ import annotations

import unittest
from dataclasses import replace

from launcher.ui.theme import (
    DEFAULT_LIGHT,
    ENGINEERING_BLUE_LIGHT,
    THEME_OPTIONS,
    dock_stylesheet,
    job_monitor_stylesheet,
    palette_stylesheet,
    preferences_stylesheet,
    theme_by_name,
)


class ThemeTests(unittest.TestCase):
    def test_stylesheets_use_shared_theme_tokens(self) -> None:
        theme = replace(
            DEFAULT_LIGHT,
            text="#010203",
            primary="#0a64f0",
            panel="#f0f4f8",
            surface="#ffffff",
        )

        stylesheets = [
            dock_stylesheet(theme),
            palette_stylesheet(theme),
            job_monitor_stylesheet(theme),
            preferences_stylesheet(theme),
        ]

        for stylesheet in stylesheets:
            self.assertIn(theme.text, stylesheet)
            self.assertIn(theme.primary, stylesheet)
            self.assertIn(theme.panel, stylesheet)
            self.assertIn(theme.surface, stylesheet)

    def test_dock_stylesheet_has_context_source_states(self) -> None:
        stylesheet = dock_stylesheet()

        for source_kind in ["explorer", "manual", "recent", "drop", "empty"]:
            self.assertIn(f'sourceKind="{source_kind}"', stylesheet)

    def test_theme_registry_resolves_supported_themes(self) -> None:
        self.assertIs(theme_by_name("graphite-light"), DEFAULT_LIGHT)
        self.assertIs(theme_by_name("engineering-blue-2"), ENGINEERING_BLUE_LIGHT)
        self.assertIs(theme_by_name("missing"), DEFAULT_LIGHT)
        self.assertIn(("engineering-blue-2", "Engineering Blue 2.0"), THEME_OPTIONS)


if __name__ == "__main__":
    unittest.main()
