from __future__ import annotations

import unittest
from unittest.mock import patch

from launcher.app.main import _instance_mutex_name, _parse_args, main


class AppMainArgumentTests(unittest.TestCase):
    def test_start_hidden_argument_is_supported(self) -> None:
        args = _parse_args(["--start-hidden", "--show-existing"])

        self.assertTrue(args.start_hidden)
        self.assertTrue(args.show_existing)
        self.assertFalse(args.self_test)

    def test_show_context_arguments_still_parse(self) -> None:
        args = _parse_args(["--set-context", "C:/Temp", "--context-source", "test"])

        self.assertEqual(args.set_context, ["C:/Temp"])
        self.assertEqual(args.context_source, "test")

    def test_show_existing_wakes_running_instance(self) -> None:
        class _Guard:
            already_running = True

        with patch("sys.argv", ["launcher", "--show-existing"]):
            with patch("launcher.app.main.SingleInstanceGuard", return_value=_Guard()):
                with patch("launcher.app.main.ContextInbox") as inbox_type:
                    with patch("builtins.print"):
                        result = main()

        self.assertEqual(result, 0)
        inbox_type.return_value.submit_show.assert_called_once()

    def test_instance_mutex_is_project_scoped(self) -> None:
        mutex_name = _instance_mutex_name()

        self.assertTrue(mutex_name.startswith("Local\\EngineeringLauncher_v2_"))
        self.assertGreater(len(mutex_name), len("Local\\EngineeringLauncher_v2_"))


if __name__ == "__main__":
    unittest.main()
