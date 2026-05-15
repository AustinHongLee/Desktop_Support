from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.plugins.copy_utils.copy_paths import copy_folder_listing, copy_selection


class CopyPathsTests(unittest.TestCase):
    def test_copy_selection_supports_modes(self) -> None:
        payload = {
            "context": {"files": ["C:/Work/A-001.pdf", "C:/Work/B-002.dwg"]},
            "options": {"mode": "basename"},
        }

        with patch("launcher.plugins.copy_utils.copy_paths.set_clipboard_text") as set_clipboard:
            events = copy_selection(payload)

        set_clipboard.assert_called_once_with("A-001\nB-002")
        self.assertEqual(events[0]["count"], 2)
        self.assertEqual(events[0]["mode"], "basename")

    def test_copy_selection_requires_files(self) -> None:
        with self.assertRaises(ValueError):
            copy_selection({"context": {"files": []}, "options": {}})

    def test_copy_folder_listing_can_copy_all_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "B.pdf").write_text("b", encoding="utf-8")
            (folder / "A.txt").write_text("a", encoding="utf-8")
            (folder / "Sub").mkdir()
            payload = {
                "context": {"folder": str(folder), "files": []},
                "options": {"include": "all", "mode": "name"},
            }

            with patch("launcher.plugins.copy_utils.copy_paths.set_clipboard_text") as set_clipboard:
                events = copy_folder_listing(payload)

        set_clipboard.assert_called_once_with("A.txt\nB.pdf\nSub")
        self.assertEqual(events[0]["count"], 3)
        self.assertEqual(events[0]["include"], "all")

    def test_copy_folder_listing_can_copy_file_basenames_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "B.pdf").write_text("b", encoding="utf-8")
            (folder / "A.txt").write_text("a", encoding="utf-8")
            (folder / "Sub").mkdir()
            payload = {
                "context": {"folder": str(folder), "files": []},
                "options": {"include": "files", "mode": "basename"},
            }

            with patch("launcher.plugins.copy_utils.copy_paths.set_clipboard_text") as set_clipboard:
                events = copy_folder_listing(payload)

        set_clipboard.assert_called_once_with("A\nB")
        self.assertEqual(events[0]["count"], 2)
        self.assertEqual(events[0]["mode"], "basename")


if __name__ == "__main__":
    unittest.main()
