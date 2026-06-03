from __future__ import annotations

import json
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from launcher.core.context_model import LauncherContext
from launcher.core.shutdown_safety import (
    FileRelationship,
    JobMetadata,
    ProcessGuard,
    ProcessSnapshot,
    RuntimeProcessLock,
    ShutdownBlocker,
    ShutdownSafetyReport,
    apply_shutdown_policy,
    runtime_layout,
    scan_shutdown_blockers,
)


class ShutdownSafetyCoreTests(unittest.TestCase):
    def test_scan_combines_process_job_lock_temp_and_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = runtime_layout(root).ensure()
            temp_dir = layout.temp / "job-safe"
            temp_dir.mkdir(parents=True)
            input_file = root / "input.pdf"
            output_file = root / "output.pdf"
            input_file.write_text("in", encoding="utf-8")
            metadata = JobMetadata(
                job_id="job-safe",
                component="iso.pdf",
                process_role="Worker process",
                pid=101,
                parent_pid=50,
                command_summary=f"python worker --project-root {root}",
                input_files=(str(input_file),),
                output_files=(str(output_file),),
                temp_dirs=(str(temp_dir),),
                started_at="2026-06-02T10:00:00+08:00",
                safe_to_kill="Safe",
                kill_consequence=("最多重跑工作。",),
                cleanup_strategy="terminate worker",
                log_file=str(layout.logs / "job-safe.log"),
            )
            _write(layout.jobs / "job-safe.json", metadata.to_payload())
            lock = RuntimeProcessLock(
                job_id="job-safe",
                pid=101,
                parent_pid=50,
                process_name="python.exe",
                process_role="Worker process",
                command_summary=metadata.command_summary,
                started_at=metadata.started_at,
                safe_to_kill="Safe",
                lock_file=str(layout.running / "job-safe_101.json"),
            )
            _write(layout.running / "job-safe_101.json", lock.to_payload())
            _write(
                layout.relationships / "job-safe.json",
                {
                    "edges": [
                        FileRelationship(
                            relation="produces",
                            source=str(input_file),
                            target=str(output_file),
                            job_id="job-safe",
                            component="iso.pdf",
                        ).to_payload()
                    ]
                },
            )
            snapshot = (
                ProcessSnapshot(
                    pid=101,
                    process_name="python.exe",
                    parent_pid=50,
                    command_line=f'python -m launcher.workers.worker_host --project-root "{root}"',
                    executable_path="C:/Python/python.exe",
                    started_at="2026-06-02T10:00:00+08:00",
                ),
                ProcessSnapshot(pid=50, process_name="launcher.exe", command_line="launcher"),
            )

            report = scan_shutdown_blockers(project_root_path=root, process_snapshot=snapshot, scan_reason="test")

        self.assertEqual(len(report.blockers), 1)
        blocker = report.blockers[0]
        self.assertEqual(blocker.pid, 101)
        self.assertEqual(blocker.job_id, "job-safe")
        self.assertEqual(blocker.safe_to_kill, "Safe")
        self.assertEqual(blocker.lock_files, (str(layout.running / "job-safe_101.json"),))
        self.assertIn(str(temp_dir), blocker.temp_dirs)
        self.assertEqual(blocker.input_files, (str(input_file),))
        self.assertEqual(blocker.output_files, (str(output_file),))
        self.assertEqual(blocker.relationships[0].relation, "produces")
        self.assertIn("command line contains project root", blocker.reasons)

    def test_scan_does_not_report_current_app_process_as_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = runtime_layout(root).ensure()
            current_pid = os.getpid()
            metadata = JobMetadata(
                job_id=f"app-main-{current_pid}",
                component="launcher.app",
                process_role="App 主程序",
                pid=current_pid,
                parent_pid=1,
                command_summary=f"python -m launcher.app.main --project-root {root}",
                started_at="now",
                safe_to_kill="Dangerous",
            )
            _write(layout.jobs / f"app-main-{current_pid}.json", metadata.to_payload())
            _write(
                layout.running / f"app-main-{current_pid}_{current_pid}.json",
                RuntimeProcessLock(
                    job_id=f"app-main-{current_pid}",
                    pid=current_pid,
                    parent_pid=1,
                    process_name="python.exe",
                    process_role="App 主程序",
                    command_summary=metadata.command_summary,
                    started_at="now",
                    safe_to_kill="Dangerous",
                ).to_payload(),
            )
            snapshot = (
                ProcessSnapshot(
                    pid=current_pid,
                    process_name="python.exe",
                    parent_pid=1,
                    command_line=f"python -m launcher.app.main --project-root {root}",
                ),
            )

            report = scan_shutdown_blockers(project_root_path=root, process_snapshot=snapshot)

        self.assertEqual(report.blockers, ())

    def test_scan_does_not_report_app_main_lock_from_other_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = runtime_layout(root).ensure()
            metadata = JobMetadata(
                job_id="app-main-9001",
                component="launcher.app",
                process_role="App 主程序",
                pid=9001,
                parent_pid=1,
                command_summary=f"python -m launcher.app.main --project-root {root}",
                started_at="now",
                safe_to_kill="Dangerous",
            )
            _write(layout.jobs / "app-main-9001.json", metadata.to_payload())
            _write(
                layout.running / "app-main-9001_9001.json",
                RuntimeProcessLock(
                    job_id="app-main-9001",
                    pid=9001,
                    parent_pid=1,
                    process_name="python.exe",
                    process_role="App 主程序",
                    command_summary=metadata.command_summary,
                    started_at="now",
                    safe_to_kill="Dangerous",
                ).to_payload(),
            )
            snapshot = (
                ProcessSnapshot(
                    pid=9001,
                    process_name="python.exe",
                    parent_pid=1,
                    command_line=f"python -m launcher.app.main --project-root {root}",
                ),
            )

            report = scan_shutdown_blockers(project_root_path=root, process_snapshot=snapshot)

        self.assertEqual(report.blockers, ())

    def test_scan_does_not_report_app_main_command_without_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = (
                ProcessSnapshot(
                    pid=9002,
                    process_name="python.exe",
                    parent_pid=1,
                    command_line=f"python -m launcher.app.main --show-existing --project-root {root}",
                ),
            )

            report = scan_shutdown_blockers(project_root_path=root, process_snapshot=snapshot)

        self.assertEqual(report.blockers, ())

    def test_scan_does_not_report_shutdown_inspector_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = (
                ProcessSnapshot(
                    pid=9003,
                    process_name="python.exe",
                    parent_pid=1,
                    command_line=f"python -m launcher.app.shutdown_safety_inspector --print-json --project-root {root}",
                ),
            )

            report = scan_shutdown_blockers(project_root_path=root, process_snapshot=snapshot)

        self.assertEqual(report.blockers, ())

    def test_scan_classifies_safe_caution_dangerous_and_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layout = runtime_layout(root).ensure()
            for job_id, pid, level in (("safe-job", 201, "Safe"), ("danger-job", 203, "Dangerous")):
                metadata = JobMetadata(
                    job_id=job_id,
                    component="tests",
                    process_role="Worker process",
                    pid=pid,
                    parent_pid=1,
                    command_summary=f"python {root}",
                    started_at="now",
                    safe_to_kill=level,  # type: ignore[arg-type]
                )
                _write(layout.jobs / f"{job_id}.json", metadata.to_payload())
                _write(
                    layout.running / f"{job_id}_{pid}.json",
                    RuntimeProcessLock(
                        job_id=job_id,
                        pid=pid,
                        parent_pid=1,
                        process_name="python.exe",
                        process_role="Worker process",
                        command_summary=metadata.command_summary,
                        started_at="now",
                        safe_to_kill=level,  # type: ignore[arg-type]
                    ).to_payload(),
                )
            snapshot = (
                ProcessSnapshot(pid=201, process_name="python.exe", command_line=f"python --project-root {root}"),
                ProcessSnapshot(pid=202, process_name="ffmpeg.exe", command_line=f"ffmpeg -i {root}\\in.mp4 {root}\\out.mp4"),
                ProcessSnapshot(pid=203, process_name="python.exe", command_line=f"python --project-root {root}"),
                ProcessSnapshot(pid=204, process_name="node.exe", command_line=f"node {root}\\tool.js"),
            )

            report = scan_shutdown_blockers(project_root_path=root, process_snapshot=snapshot)

        levels = {blocker.pid: blocker.safe_to_kill for blocker in report.blockers}
        self.assertEqual(levels[201], "Safe")
        self.assertEqual(levels[202], "Caution")
        self.assertEqual(levels[203], "Dangerous")
        self.assertEqual(levels[204], "Unknown")

    def test_dry_run_does_not_stop_processes(self) -> None:
        report = ShutdownSafetyReport(
            project_root="C:/Project",
            scan_reason="test",
            created_at="now",
            blockers=(
                _blocker(301, safe_to_kill="Safe", command_line_contains_project_root=True),
            ),
        )

        with patch("launcher.core.shutdown_safety._taskkill") as taskkill:
            result = apply_shutdown_policy(report, kill_safe=True, dry_run=True)

        self.assertEqual(result.attempted_pids, (301,))
        self.assertEqual(result.stopped_pids, ())
        self.assertIn("dry-run", result.skipped[0])
        taskkill.assert_not_called()

    def test_force_stop_only_stops_project_command_lines(self) -> None:
        report = ShutdownSafetyReport(
            project_root="C:/Project",
            scan_reason="test",
            created_at="now",
            blockers=(
                _blocker(401, safe_to_kill="Caution", command_line_contains_project_root=True),
                _blocker(402, safe_to_kill="Caution", command_line_contains_project_root=False),
            ),
        )

        with patch("launcher.core.shutdown_safety._taskkill") as taskkill:
            result = apply_shutdown_policy(report, force_all_project_owned=True)

        taskkill.assert_called_once_with(401, force=True)
        self.assertEqual(result.stopped_pids, (401,))
        self.assertEqual(result.attempted_pids, (401, 402))
        self.assertIn("command line does not contain project root", result.skipped[0])

    def test_process_guard_writes_and_removes_runtime_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = LauncherContext(folder=root, source="test")
            guard = ProcessGuard.for_action(
                "test.action",
                "測試",
                context,
                command=["python", "-m", "launcher.workers.worker_host", "--project-root", str(root)],
                project_root_path=root,
            )
            process = _FakeProcess(pid=777)

            guard.record_started(process)
            layout = runtime_layout(root)
            running = list(layout.running.glob("*_777.json"))
            jobs = list(layout.jobs.glob("test-action-*.json"))

            self.assertEqual(len(running), 1)
            self.assertEqual(len(jobs), 1)
            payload = json.loads(jobs[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["pid"], 777)
            self.assertEqual(payload["process_role"], "Worker process")

            guard.mark_completed(return_code=0)

            self.assertFalse(running[0].exists())


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.stdin = None
        self.stdout = None
        self.stderr = None


def _blocker(pid: int, *, safe_to_kill: str, command_line_contains_project_root: bool) -> ShutdownBlocker:
    return ShutdownBlocker(
        id=f"process:{pid}",
        pid=pid,
        process_name="python.exe",
        parent_pid=1,
        command_summary="python --project-root C:/Project",
        command_line="python --project-root C:/Project",
        executable_path="C:/Python/python.exe",
        started_at="now",
        safe_to_kill=safe_to_kill,  # type: ignore[arg-type]
        project_owned=True,
        command_line_contains_project_root=command_line_contains_project_root,
    )


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
