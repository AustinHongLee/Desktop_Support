from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.ui.preview_cache import PdfPreviewCache


class PdfPreviewCacheTests(unittest.TestCase):
    def test_reuses_cached_copy_when_source_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.pdf"
            source.write_bytes(b"one")
            cache = PdfPreviewCache(root / "cache")

            first = cache.preview_path_for(source)
            second = cache.preview_path_for(source)

            self.assertEqual(first, second)
            self.assertEqual(len(list((root / "cache").iterdir())), 1)

    def test_creates_new_copy_when_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.pdf"
            source.write_bytes(b"one")
            cache = PdfPreviewCache(root / "cache")

            first = cache.preview_path_for(source)
            source.write_bytes(b"one two")
            second = cache.preview_path_for(source)

            self.assertNotEqual(first, second)
            self.assertEqual(second.read_bytes(), b"one two")


if __name__ == "__main__":
    unittest.main()
