from __future__ import annotations

import unittest
from pathlib import Path

from launcher.windows.explorer_context import _location_folder


class FakeWindow:
    LocationURL = "file:///C:/Work/Project%20A"


class ExplorerContextTests(unittest.TestCase):
    def test_location_folder_decodes_file_url(self) -> None:
        self.assertEqual(_location_folder(FakeWindow()), Path("C:/Work/Project A"))


if __name__ == "__main__":
    unittest.main()

