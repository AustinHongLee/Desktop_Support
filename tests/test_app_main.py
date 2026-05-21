from __future__ import annotations

import unittest

from launcher.app.main import _parse_args


class AppMainArgumentTests(unittest.TestCase):
    def test_start_hidden_argument_is_supported(self) -> None:
        args = _parse_args(["--start-hidden"])

        self.assertTrue(args.start_hidden)
        self.assertFalse(args.self_test)

    def test_show_context_arguments_still_parse(self) -> None:
        args = _parse_args(["--set-context", "C:/Temp", "--context-source", "test"])

        self.assertEqual(args.set_context, ["C:/Temp"])
        self.assertEqual(args.context_source, "test")


if __name__ == "__main__":
    unittest.main()
