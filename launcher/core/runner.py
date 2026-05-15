from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from typing import Any, Callable

from launcher.core.action_model import ActionDefinition
from launcher.core.context_model import LauncherContext
from launcher.core.job_model import JobEvent, JobResult
from launcher.core.paths import project_root

EventCallback = Callable[[JobEvent], None]


class RunControl:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    @property
    def cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    def attach_process(self, process: subprocess.Popen[str]) -> None:
        terminate_now = False
        with self._lock:
            self._process = process
            terminate_now = self._cancel_requested
        if terminate_now:
            _request_terminate(process)

    def cancel(self) -> None:
        process: subprocess.Popen[str] | None = None
        with self._lock:
            self._cancel_requested = True
            process = self._process
        if process is not None:
            _request_terminate(process)


class ActionRunner:
    def run(
        self,
        action: ActionDefinition,
        context: LauncherContext,
        *,
        on_event: EventCallback | None = None,
        timeout_seconds: float | None = None,
        control: RunControl | None = None,
        options: dict[str, Any] | None = None,
    ) -> JobResult:
        if action.command.type != "python_module":
            raise ValueError(f"Unsupported command type: {action.command.type}")

        started_at = datetime.now()
        effective_timeout = timeout_seconds if timeout_seconds is not None else action.timeout_seconds
        payload = {
            "action": action.to_payload(),
            "context": context.to_payload(),
            "options": dict(options or {}),
        }
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", "launcher.workers.worker_host"],
                cwd=str(project_root()),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except OSError as exc:
            finished_at = datetime.now()
            event = JobEvent(
                type="error",
                message=f"無法啟動 worker：{exc}",
                data={"exception": exc.__class__.__name__},
            )
            if on_event:
                on_event(event)
            return JobResult(
                action_id=action.id,
                return_code=-1,
                started_at=started_at,
                finished_at=finished_at,
                events=(event,),
            )
        if control is not None:
            control.attach_process(process)
        assert process.stdin is not None
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False))
            process.stdin.close()
        except OSError as exc:
            event = JobEvent(
                type="error",
                message=f"無法送出任務給 worker：{exc}",
                data={"exception": exc.__class__.__name__},
            )
            _emit_event(event, on_event)
            _terminate_process(process)
            return JobResult(
                action_id=action.id,
                return_code=process.wait(),
                started_at=started_at,
                finished_at=datetime.now(),
                events=(event,),
            )

        events: list[JobEvent] = []
        assert process.stdout is not None
        lines: queue.Queue[str | None] = queue.Queue()
        reader = threading.Thread(target=_read_stdout_lines, args=(process.stdout, lines), daemon=True)
        reader.start()

        return_code = self._drain_worker(
            action,
            process,
            lines,
            events,
            on_event,
            effective_timeout,
            control,
        )
        failure_event = self._failure_event(action, return_code, events)
        if failure_event is not None:
            events.append(failure_event)
            _emit_event(failure_event, on_event)
        finished_at = datetime.now()
        return JobResult(
            action_id=action.id,
            return_code=return_code,
            started_at=started_at,
            finished_at=finished_at,
            events=tuple(events),
        )

    @staticmethod
    def _parse_event(line: str) -> JobEvent:
        try:
            payload = json.loads(line)
            if isinstance(payload, dict):
                return JobEvent.from_payload(payload)
        except json.JSONDecodeError:
            pass
        return JobEvent(type="log", message=line.rstrip())

    def _drain_worker(
        self,
        action: ActionDefinition,
        process: subprocess.Popen[str],
        lines: queue.Queue[str | None],
        events: list[JobEvent],
        on_event: EventCallback | None,
        timeout_seconds: float | None,
        control: RunControl | None,
    ) -> int:
        deadline = time.monotonic() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        stdout_done = False
        cancel_reported = False
        timeout_reported = False

        while True:
            try:
                line = lines.get(timeout=0.05)
            except queue.Empty:
                line = "__NO_LINE__"

            if line is None:
                stdout_done = True
            elif line != "__NO_LINE__":
                event = self._parse_event(line)
                events.append(event)
                _emit_event(event, on_event)

            if control is not None and control.cancel_requested and not cancel_reported:
                event = JobEvent(type="cancelled", message=f"已要求取消：{action.title}")
                events.append(event)
                _emit_event(event, on_event)
                _request_terminate(process)
                cancel_reported = True

            if deadline is not None and time.monotonic() >= deadline and not timeout_reported:
                event = JobEvent(
                    type="timeout",
                    message=f"執行逾時，已停止：{action.title}",
                    data={"timeout_seconds": timeout_seconds},
                )
                events.append(event)
                _emit_event(event, on_event)
                _terminate_process(process)
                timeout_reported = True

            return_code = process.poll()
            if return_code is not None and stdout_done:
                return process.wait()

    @staticmethod
    def _failure_event(
        action: ActionDefinition,
        return_code: int,
        events: list[JobEvent],
    ) -> JobEvent | None:
        if return_code == 0 or any(event.type in {"error", "cancelled", "timeout"} for event in events):
            return None

        tail = [event.message for event in events[-8:] if event.message]
        data: dict[str, object] = {"return_code": return_code}
        if tail:
            data["recent_output"] = "\n".join(tail)
        return JobEvent(
            type="error",
            message=f"worker 非正常結束：{action.title} (exit code {return_code})",
            data=data,
        )


def _emit_event(event: JobEvent, on_event: EventCallback | None) -> None:
    if on_event:
        on_event(event)


def _read_stdout_lines(stdout, lines: queue.Queue[str | None]) -> None:  # noqa: ANN001
    try:
        for line in stdout:
            lines.put(line)
    finally:
        lines.put(None)


def _request_terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        pass


def _terminate_process(process: subprocess.Popen[str], *, grace_seconds: float = 1.5) -> None:
    _request_terminate(process)
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        process.wait()
