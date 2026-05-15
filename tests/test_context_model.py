from __future__ import annotations

import unittest
from pathlib import Path

from launcher.core.context_model import LauncherContext


class ContextModelTests(unittest.TestCase):
    def test_context_payload_round_trip(self) -> None:
        context = LauncherContext.from_paths(
            ["C:/Project/A.dwg", "C:/Project/B.dwg"],
            folder="C:/Project",
            source="test",
        )

        restored = LauncherContext.from_payload(context.to_payload())

        self.assertEqual(restored.folder, Path("C:/Project"))
        self.assertEqual(restored.files, (Path("C:/Project/A.dwg"), Path("C:/Project/B.dwg")))
        self.assertEqual(restored.source, "test")

    def test_context_extensions_are_lowercase(self) -> None:
        context = LauncherContext.from_paths(["C:/Project/A.DWG", "C:/Project/B.pdf"])

        self.assertEqual(context.extensions, {".dwg", ".pdf"})


if __name__ == "__main__":
    unittest.main()
