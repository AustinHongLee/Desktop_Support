from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.core.action_model import ActionDefinition, CommandSpec
from launcher.core.context_model import LauncherContext
from launcher.core.job_model import JobEvent
from launcher.core.runner import ActionRunner, RunControl


class _FakeStdin:
    def __init__(self) -> None:
        self.text = ""
        self.closed = False

    def write(self, value: str) -> int:
        self.text += value
        return len(value)

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, stdout: str = "", return_code: int | None = 0) -> None:
        self.stdin = _FakeStdin()
        self.stdout = io.StringIO(stdout)
        self._return_code = return_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._return_code

    def terminate(self) -> None:
        self.terminated = True
        if self._return_code is None:
            self._return_code = -15

    def kill(self) -> None:
        self.killed = True
        self._return_code = -9

    def wait(self, timeout: float | None = None) -> int:
        if self._return_code is None:
            self._return_code = 0
        return self._return_code


class ActionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.action = ActionDefinition(
            id="test.action",
            title="測試指令",
            category="測試",
            plugin_id="tests",
            command=CommandSpec(
                type="python_module",
                module="tests.fake_worker",
                entry="main",
            ),
        )
        self.context = LauncherContext(folder=Path("C:/Work"), source="test")

    def test_parse_json_event(self) -> None:
        event = ActionRunner._parse_event('{"type":"message","message":"hello","count":2}\n')

        self.assertEqual(event.type, "message")
        self.assertEqual(event.message, "hello")
        self.assertEqual(event.data["count"], 2)

    def test_parse_plain_output_as_log(self) -> None:
        event = ActionRunner._parse_event("plain output\n")

        self.assertEqual(event.type, "log")
        self.assertEqual(event.message, "plain output")

    def test_run_adds_failure_event_when_worker_exits_without_error(self) -> None:
        process = _FakeProcess(stdout="last thing printed\n", return_code=7)
        received: list[JobEvent] = []

        with patch("launcher.core.runner.subprocess.Popen", return_value=process):
            result = ActionRunner().run(self.action, self.context, on_event=received.append)

        self.assertEqual(result.return_code, 7)
        self.assertFalse(result.ok)
        self.assertEqual(result.events[-1].type, "error")
        self.assertIn("exit code 7", result.events[-1].message)
        self.assertEqual(received[-1], result.events[-1])

    def test_run_does_not_duplicate_worker_error(self) -> None:
        process = _FakeProcess(
            stdout='{"type":"error","message":"worker failed"}\n',
            return_code=1,
        )

        with patch("launcher.core.runner.subprocess.Popen", return_value=process):
            result = ActionRunner().run(self.action, self.context)

        self.assertEqual([event.type for event in result.events], ["error"])

    def test_run_passes_action_options_to_worker_payload(self) -> None:
        process = _FakeProcess(stdout="", return_code=0)

        with patch("launcher.core.runner.subprocess.Popen", return_value=process):
            result = ActionRunner().run(
                self.action,
                self.context,
                options={"mode": "basename", "include": "files"},
            )

        payload = json.loads(process.stdin.text)
        self.assertTrue(result.ok)
        self.assertTrue(process.stdin.closed)
        self.assertEqual(payload["options"], {"mode": "basename", "include": "files"})

    def test_run_reports_worker_start_failure(self) -> None:
        received: list[JobEvent] = []

        with patch("launcher.core.runner.subprocess.Popen", side_effect=OSError("missing python")):
            result = ActionRunner().run(self.action, self.context, on_event=received.append)

        self.assertEqual(result.return_code, -1)
        self.assertFalse(result.ok)
        self.assertEqual(result.events[0].type, "error")
        self.assertIn("無法啟動 worker", result.events[0].message)
        self.assertEqual(received, list(result.events))

    def test_run_can_cancel_before_process_writes_output(self) -> None:
        process = _FakeProcess(stdout="", return_code=None)
        control = RunControl()
        control.cancel()

        with patch("launcher.core.runner.subprocess.Popen", return_value=process):
            result = ActionRunner().run(self.action, self.context, control=control)

        self.assertTrue(process.terminated)
        self.assertEqual(result.return_code, -15)
        self.assertIn("cancelled", [event.type for event in result.events])

    def test_run_times_out_and_terminates_worker(self) -> None:
        process = _FakeProcess(stdout="", return_code=None)

        with patch("launcher.core.runner.subprocess.Popen", return_value=process):
            result = ActionRunner().run(self.action, self.context, timeout_seconds=0.001)

        self.assertTrue(process.terminated)
        self.assertEqual(result.return_code, -15)
        self.assertIn("timeout", [event.type for event in result.events])

    def test_action_definition_reads_timeout_seconds(self) -> None:
        action = ActionDefinition.from_dict(
            {
                "id": "test.timeout",
                "title": "有時間限制",
                "category": "測試",
                "timeout_seconds": 12.5,
                "command": {
                    "type": "python_module",
                    "module": "tests.fake_worker",
                    "entry": "main",
                },
            },
            plugin_id="tests",
            plugin_path=Path("C:/Plugins/tests"),
        )

        self.assertEqual(action.timeout_seconds, 12.5)
        self.assertEqual(action.to_payload()["timeout_seconds"], 12.5)


if __name__ == "__main__":
    unittest.main()
