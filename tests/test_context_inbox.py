from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from launcher.core.context_inbox import ContextInbox


class ContextInboxTests(unittest.TestCase):
    def test_submit_and_take_file_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            file_path = root / "a.txt"
            file_path.write_text("x", encoding="utf-8")
            inbox = ContextInbox(root / "request.json")

            inbox.submit([file_path], source="test.menu")
            context = inbox.take()

            self.assertIsNotNone(context)
            assert context is not None
            self.assertEqual(context.source, "test.menu")
            self.assertEqual(context.folder, root)
            self.assertEqual(context.files, (file_path,))
            self.assertIsNone(inbox.take())

    def test_submit_single_folder_context_does_not_become_file_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "folder"
            folder.mkdir()
            inbox = ContextInbox(root / "request.json")

            inbox.submit([folder], source="test.menu")
            context = inbox.take()

            self.assertIsNotNone(context)
            assert context is not None
            self.assertEqual(context.folder, folder)
            self.assertEqual(context.files, ())

    def test_submit_show_creates_wake_request_without_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = ContextInbox(root / "request.json")

            inbox.submit_show()
            request = inbox.take_request()

            self.assertIsNotNone(request)
            assert request is not None
            self.assertEqual(request.command, "show")
            self.assertIsNone(request.context)
            self.assertIsNone(inbox.take_request())

    def test_take_still_returns_context_for_context_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = ContextInbox(root / "request.json")

            inbox.submit([], source="launcher.show")
            context = inbox.take()

            self.assertIsNotNone(context)
            assert context is not None
            self.assertEqual(context.source, "launcher.show")


if __name__ == "__main__":
    unittest.main()
