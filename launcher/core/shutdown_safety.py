from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from launcher.core.context_model import LauncherContext
from launcher.core.paths import project_root

SafeToKill = Literal["Safe", "Caution", "Dangerous", "Unknown"]
ShutdownAction = Literal[
    "Wait",
    "Graceful stop",
    "Force stop",
    "Open log",
    "Open related folder",
    "Inspect dependency graph",
    "Ignore once",
    "Cancel shutdown / close",
]

SAFE_TO_KILL_LEVELS: tuple[SafeToKill, ...] = ("Safe", "Caution", "Dangerous", "Unknown")
PROCESS_TOOL_NAMES = {"python.exe", "pythonw.exe", "ffmpeg.exe", "node.exe"}
REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RuntimeLayout:
    project_root: Path
    runtime: Path
    running: Path
    jobs: Path
    logs: Path
    relationships: Path
    temp: Path

    def ensure(self) -> "RuntimeLayout":
        for folder in (self.runtime, self.running, self.jobs, self.logs, self.relationships, self.temp):
            folder.mkdir(parents=True, exist_ok=True)
        return self


@dataclass(frozen=True)
class FileRelationship:
    relation: str
    source: str
    target: str
    job_id: str = ""
    component: str = ""
    note: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "source": self.source,
            "target": self.target,
            "job_id": self.job_id,
            "component": self.component,
            "note": self.note,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FileRelationship":
        return cls(
            relation=str(payload.get("relation") or payload.get("type") or "depends_on"),
            source=str(payload.get("source") or payload.get("from") or ""),
            target=str(payload.get("target") or payload.get("to") or ""),
            job_id=str(payload.get("job_id") or ""),
            component=str(payload.get("component") or ""),
            note=str(payload.get("note") or payload.get("reason") or ""),
        )


@dataclass(frozen=True)
class JobMetadata:
    job_id: str
    component: str
    process_role: str
    pid: int
    parent_pid: int
    command_summary: str
    input_files: tuple[str, ...] = ()
    output_files: tuple[str, ...] = ()
    temp_dirs: tuple[str, ...] = ()
    started_at: str = ""
    safe_to_kill: SafeToKill = "Unknown"
    kill_consequence: tuple[str, ...] = ()
    cleanup_strategy: str = ""
    status: str = "running"
    lock_file: str = ""
    log_file: str = ""
    finished_at: str = ""
    return_code: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "job_id": self.job_id,
            "component": self.component,
            "process_role": self.process_role,
            "pid": self.pid,
            "parent_pid": self.parent_pid,
            "command_summary": self.command_summary,
            "input_files": list(self.input_files),
            "output_files": list(self.output_files),
            "temp_dirs": list(self.temp_dirs),
            "started_at": self.started_at,
            "safe_to_kill": self.safe_to_kill,
            "kill_consequence": list(self.kill_consequence),
            "cleanup_strategy": self.cleanup_strategy,
            "status": self.status,
            "lock_file": self.lock_file,
            "log_file": self.log_file,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "JobMetadata":
        return cls(
            job_id=str(payload.get("job_id") or ""),
            component=str(payload.get("component") or ""),
            process_role=str(payload.get("process_role") or payload.get("role") or ""),
            pid=_safe_int(payload.get("pid")),
            parent_pid=_safe_int(payload.get("parent_pid")),
            command_summary=str(payload.get("command_summary") or payload.get("command") or ""),
            input_files=_string_tuple(payload.get("input_files")),
            output_files=_string_tuple(payload.get("output_files")),
            temp_dirs=_string_tuple(payload.get("temp_dirs")),
            started_at=str(payload.get("started_at") or ""),
            safe_to_kill=_safe_level(payload.get("safe_to_kill")),
            kill_consequence=_string_tuple(payload.get("kill_consequence")),
            cleanup_strategy=str(payload.get("cleanup_strategy") or ""),
            status=str(payload.get("status") or "running"),
            lock_file=str(payload.get("lock_file") or ""),
            log_file=str(payload.get("log_file") or ""),
            finished_at=str(payload.get("finished_at") or ""),
            return_code=None if payload.get("return_code") in (None, "") else _safe_int(payload.get("return_code")),
        )


@dataclass(frozen=True)
class RuntimeProcessLock:
    job_id: str
    pid: int
    parent_pid: int
    process_name: str
    process_role: str
    command_summary: str
    started_at: str
    safe_to_kill: SafeToKill
    lock_file: str = ""
    log_file: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "job_id": self.job_id,
            "pid": self.pid,
            "parent_pid": self.parent_pid,
            "process_name": self.process_name,
            "process_role": self.process_role,
            "command_summary": self.command_summary,
            "started_at": self.started_at,
            "safe_to_kill": self.safe_to_kill,
            "lock_file": self.lock_file,
            "log_file": self.log_file,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, lock_file: Path | None = None) -> "RuntimeProcessLock":
        return cls(
            job_id=str(payload.get("job_id") or ""),
            pid=_safe_int(payload.get("pid")),
            parent_pid=_safe_int(payload.get("parent_pid")),
            process_name=str(payload.get("process_name") or payload.get("name") or ""),
            process_role=str(payload.get("process_role") or payload.get("role") or ""),
            command_summary=str(payload.get("command_summary") or ""),
            started_at=str(payload.get("started_at") or ""),
            safe_to_kill=_safe_level(payload.get("safe_to_kill")),
            lock_file=str(payload.get("lock_file") or lock_file or ""),
            log_file=str(payload.get("log_file") or ""),
        )


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    process_name: str
    parent_pid: int = 0
    command_line: str = ""
    executable_path: str = ""
    started_at: str = ""

    @property
    def command_summary(self) -> str:
        return _compact(self.command_line or self.executable_path or self.process_name, 220)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ProcessSnapshot":
        return cls(
            pid=_safe_int(payload.get("ProcessId") or payload.get("pid")),
            process_name=str(payload.get("Name") or payload.get("process_name") or payload.get("name") or ""),
            parent_pid=_safe_int(payload.get("ParentProcessId") or payload.get("parent_pid")),
            command_line=str(payload.get("CommandLine") or payload.get("command_line") or ""),
            executable_path=str(payload.get("ExecutablePath") or payload.get("executable_path") or ""),
            started_at=str(payload.get("CreationDate") or payload.get("started_at") or ""),
        )


@dataclass(frozen=True)
class ShutdownBlocker:
    id: str
    pid: int
    process_name: str
    parent_pid: int
    command_summary: str
    command_line: str
    executable_path: str
    started_at: str
    job_id: str = ""
    component: str = ""
    process_role: str = "Unknown but project-owned"
    safe_to_kill: SafeToKill = "Unknown"
    reasons: tuple[str, ...] = ()
    lock_files: tuple[str, ...] = ()
    temp_dirs: tuple[str, ...] = ()
    input_files: tuple[str, ...] = ()
    output_files: tuple[str, ...] = ()
    log_files: tuple[str, ...] = ()
    relationships: tuple[FileRelationship, ...] = ()
    child_pids: tuple[int, ...] = ()
    parent_process: str = ""
    kill_consequence: tuple[str, ...] = ()
    suggested_actions: tuple[ShutdownAction, ...] = ()
    project_owned: bool = True
    command_line_contains_project_root: bool = False
    can_automatically_stop: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "pid": self.pid,
            "process_name": self.process_name,
            "parent_pid": self.parent_pid,
            "command_summary": self.command_summary,
            "command_line": self.command_line,
            "executable_path": self.executable_path,
            "started_at": self.started_at,
            "job_id": self.job_id,
            "component": self.component,
            "process_role": self.process_role,
            "safe_to_kill": self.safe_to_kill,
            "reasons": list(self.reasons),
            "lock_files": list(self.lock_files),
            "temp_dirs": list(self.temp_dirs),
            "input_files": list(self.input_files),
            "output_files": list(self.output_files),
            "log_files": list(self.log_files),
            "relationships": [relationship.to_payload() for relationship in self.relationships],
            "child_pids": list(self.child_pids),
            "parent_process": self.parent_process,
            "kill_consequence": list(self.kill_consequence),
            "suggested_actions": list(self.suggested_actions),
            "project_owned": self.project_owned,
            "command_line_contains_project_root": self.command_line_contains_project_root,
            "can_automatically_stop": self.can_automatically_stop,
        }

    @property
    def is_killable(self) -> bool:
        return self.pid > 0 and self.pid != os.getpid() and self.project_owned and self.command_line_contains_project_root

    @property
    def dependency_graph_text(self) -> str:
        lines: list[str] = []
        if self.job_id:
            lines.append(f"job:{self.job_id} ({self.component or self.process_role})")
        for path in self.input_files:
            lines.append(f"  input  -> {path}")
        for path in self.temp_dirs:
            lines.append(f"  temp   -> {path}")
        for path in self.output_files:
            lines.append(f"  output <- {path}")
        for relationship in self.relationships:
            note = f" ({relationship.note})" if relationship.note else ""
            lines.append(f"  {relationship.source} -[{relationship.relation}]-> {relationship.target}{note}")
        if self.parent_pid:
            lines.append(f"parent PID: {self.parent_pid} {self.parent_process}".rstrip())
        if self.child_pids:
            lines.append(f"children: {', '.join(str(pid) for pid in self.child_pids)}")
        return "\n".join(lines) or "沒有可用的 dependency graph；只知道它屬於本專案 runtime。"


@dataclass(frozen=True)
class ShutdownSafetyReport:
    project_root: str
    scan_reason: str
    created_at: str
    blockers: tuple[ShutdownBlocker, ...]
    stale_locks_removed: tuple[str, ...] = ()
    report_path: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "project_root": self.project_root,
            "scan_reason": self.scan_reason,
            "created_at": self.created_at,
            "blocker_count": len(self.blockers),
            "blockers": [blocker.to_payload() for blocker in self.blockers],
            "stale_locks_removed": list(self.stale_locks_removed),
            "report_path": self.report_path,
        }

    @property
    def safe_count(self) -> int:
        return sum(1 for blocker in self.blockers if blocker.safe_to_kill == "Safe")

    @property
    def caution_count(self) -> int:
        return sum(1 for blocker in self.blockers if blocker.safe_to_kill == "Caution")

    @property
    def dangerous_count(self) -> int:
        return sum(1 for blocker in self.blockers if blocker.safe_to_kill == "Dangerous")

    @property
    def unknown_count(self) -> int:
        return sum(1 for blocker in self.blockers if blocker.safe_to_kill == "Unknown")


@dataclass(frozen=True)
class ShutdownActionResult:
    attempted_pids: tuple[int, ...] = ()
    stopped_pids: tuple[int, ...] = ()
    skipped: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


class ProcessGuard:
    """Records project-owned subprocesses so shutdown inspection has provenance."""

    def __init__(self, metadata: JobMetadata, *, project_root_path: Path | None = None) -> None:
        self.project_root = _root(project_root_path)
        self.layout = runtime_layout(self.project_root).ensure()
        self.metadata = metadata
        self.lock_path: Path | None = None

    @classmethod
    def for_action(
        cls,
        action_id: str,
        title: str,
        context: LauncherContext,
        *,
        command: list[str],
        project_root_path: Path | None = None,
    ) -> "ProcessGuard":
        layout = runtime_layout(project_root_path).ensure()
        job_id = _new_job_id(action_id)
        temp_dir = layout.temp / job_id
        log_file = layout.logs / f"{job_id}.log"
        metadata = JobMetadata(
            job_id=job_id,
            component=action_id,
            process_role="Worker process",
            pid=0,
            parent_pid=os.getpid(),
            command_summary=_compact_command(command),
            input_files=tuple(str(path) for path in context.files) or ((str(context.folder),) if context.folder else ()),
            output_files=(),
            temp_dirs=(str(temp_dir),),
            started_at=_now_iso(),
            safe_to_kill="Safe",
            kill_consequence=(
                "未完成 job 會標記 interrupted。",
                "目前 worker 可重新執行；最多需要重跑工作。",
                "stdin/stdout/stderr pipe 會在清理時關閉。",
            ),
            cleanup_strategy="close pipes, terminate worker, then taskkill /T if the tree does not exit",
            status="starting",
            log_file=str(log_file),
        )
        return cls(metadata, project_root_path=project_root_path)

    def record_started(self, process: subprocess.Popen[Any]) -> None:
        pid = _safe_int(getattr(process, "pid", 0))
        if pid <= 0:
            return
        lock_path = self.layout.running / f"{self.metadata.job_id}_{pid}.json"
        process_name = Path(self.metadata.command_summary.split(" ", 1)[0]).name or "process"
        self.metadata = replace(
            self.metadata,
            pid=pid,
            parent_pid=os.getpid(),
            status="running",
            lock_file=str(lock_path),
        )
        runtime_lock = RuntimeProcessLock(
            job_id=self.metadata.job_id,
            pid=pid,
            parent_pid=os.getpid(),
            process_name=process_name,
            process_role=self.metadata.process_role,
            command_summary=self.metadata.command_summary,
            started_at=self.metadata.started_at,
            safe_to_kill=self.metadata.safe_to_kill,
            lock_file=str(lock_path),
            log_file=self.metadata.log_file,
        )
        self.lock_path = lock_path
        _write_json(lock_path, runtime_lock.to_payload())
        _write_json(self.layout.jobs / f"{self.metadata.job_id}.json", self.metadata.to_payload())
        _append_safety_log(self.layout, f"started job={self.metadata.job_id} pid={pid} role={self.metadata.process_role}")

    def record_relationships(self, relationships: list[FileRelationship]) -> None:
        if not relationships:
            return
        path = self.layout.relationships / f"{self.metadata.job_id}.json"
        _write_json(path, {"schema_version": REPORT_SCHEMA_VERSION, "edges": [edge.to_payload() for edge in relationships]})

    def mark_completed(self, *, return_code: int = 0) -> None:
        self._mark_finished("completed" if return_code == 0 else "failed", return_code=return_code)

    def mark_failed(self, *, return_code: int | None = None, reason: str = "") -> None:
        self._mark_finished("failed", return_code=return_code, reason=reason)

    def mark_interrupted(self, *, return_code: int | None = None, reason: str = "") -> None:
        self._mark_finished("interrupted", return_code=return_code, reason=reason)

    def cleanup_pipes(self, process: subprocess.Popen[Any]) -> None:
        for stream_name in ("stdin", "stdout", "stderr"):
            stream = getattr(process, stream_name, None)
            if stream is None:
                continue
            try:
                if not getattr(stream, "closed", False):
                    stream.close()
            except Exception:
                pass

    def terminate_process_tree(self, process: subprocess.Popen[Any], *, grace_seconds: float = 1.5) -> None:
        self.cleanup_pipes(process)
        _request_terminate(process)
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        pid = _safe_int(getattr(process, "pid", 0))
        if sys.platform == "win32" and pid > 0:
            _taskkill(pid, force=False)
            try:
                process.wait(timeout=2.0)
                return
            except subprocess.TimeoutExpired:
                _taskkill(pid, force=True)
                process.wait()
                return
        try:
            process.kill()
        except OSError:
            pass
        process.wait()

    def _mark_finished(self, status: str, *, return_code: int | None = None, reason: str = "") -> None:
        self.metadata = replace(
            self.metadata,
            status=status,
            finished_at=_now_iso(),
            return_code=return_code,
        )
        _write_json(self.layout.jobs / f"{self.metadata.job_id}.json", self.metadata.to_payload())
        if self.lock_path and self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass
        detail = f" reason={reason}" if reason else ""
        _append_safety_log(self.layout, f"{status} job={self.metadata.job_id} pid={self.metadata.pid}{detail}")


def runtime_layout(project_root_path: Path | str | None = None) -> RuntimeLayout:
    root = _root(project_root_path)
    runtime = root / ".runtime"
    return RuntimeLayout(
        project_root=root,
        runtime=runtime,
        running=runtime / "running",
        jobs=runtime / "jobs",
        logs=runtime / "logs",
        relationships=runtime / "relationships",
        temp=runtime / "temp",
    )


def register_current_app_process(*, project_root_path: Path | str | None = None) -> JobMetadata:
    root = _root(project_root_path)
    layout = runtime_layout(root).ensure()
    job_id = f"app-main-{os.getpid()}"
    lock_path = layout.running / f"{job_id}_{os.getpid()}.json"
    metadata = JobMetadata(
        job_id=job_id,
        component="launcher.app",
        process_role="App 主程序",
        pid=os.getpid(),
        parent_pid=_parent_pid(),
        command_summary=_compact_command([sys.executable, *sys.argv, "--project-root", str(root)]),
        input_files=(),
        output_files=(),
        temp_dirs=(),
        started_at=_now_iso(),
        safe_to_kill="Dangerous",
        kill_consequence=(
            "這是目前 UI 主程序；不會由 Inspector 自動結束。",
            "關閉 app 前會先處理 worker / ffmpeg / temp job。",
        ),
        cleanup_strategy="prompt user and let QApplication quit normally",
        status="running",
        lock_file=str(lock_path),
        log_file=str(layout.logs / "safety.log"),
    )
    runtime_lock = RuntimeProcessLock(
        job_id=job_id,
        pid=os.getpid(),
        parent_pid=metadata.parent_pid,
        process_name=Path(sys.executable).name,
        process_role=metadata.process_role,
        command_summary=metadata.command_summary,
        started_at=metadata.started_at,
        safe_to_kill=metadata.safe_to_kill,
        lock_file=str(lock_path),
        log_file=metadata.log_file,
    )
    _write_json(lock_path, runtime_lock.to_payload())
    _write_json(layout.jobs / f"{job_id}.json", metadata.to_payload())
    _append_safety_log(layout, f"registered app main pid={os.getpid()}")
    return metadata


def unregister_current_app_process(*, project_root_path: Path | str | None = None) -> None:
    layout = runtime_layout(project_root_path).ensure()
    prefix = f"app-main-{os.getpid()}_"
    for lock_file in layout.running.glob(f"{prefix}*.json"):
        try:
            lock_file.unlink()
        except OSError:
            pass
    job_file = layout.jobs / f"app-main-{os.getpid()}.json"
    if job_file.exists():
        try:
            payload = json.loads(job_file.read_text(encoding="utf-8"))
            metadata = JobMetadata.from_payload(payload)
            _write_json(job_file, replace(metadata, status="completed", finished_at=_now_iso()).to_payload())
        except Exception:
            pass


def scan_shutdown_blockers(
    *,
    project_root_path: Path | str | None = None,
    process_snapshot: tuple[ProcessSnapshot, ...] | list[ProcessSnapshot] | None = None,
    scan_reason: str = "manual",
) -> ShutdownSafetyReport:
    root = _root(project_root_path)
    layout = runtime_layout(root).ensure()
    processes = tuple(process_snapshot) if process_snapshot is not None else tuple(_windows_process_snapshot(root))
    process_by_pid = {process.pid: process for process in processes if process.pid > 0}
    children_by_parent = _children_by_parent(processes)
    locks, stale_locks = _load_runtime_locks(layout, process_by_pid)
    jobs = _load_jobs(layout)
    relationships = _load_relationships(layout)
    blockers: list[ShutdownBlocker] = []
    root_token = _path_token(root)
    current_pid = os.getpid()

    for process in processes:
        if process.pid <= 0:
            continue
        if process.pid == current_pid:
            continue
        command_line_contains_root = _contains_project_root(process, root_token)
        lock = locks.get(process.pid)
        if not command_line_contains_root and lock is None:
            continue
        metadata = _metadata_for_process(process.pid, lock, jobs)
        blocker = _build_blocker(
            process,
            root=root,
            root_token=root_token,
            lock=lock,
            metadata=metadata,
            relationships=relationships,
            process_by_pid=process_by_pid,
            children_by_parent=children_by_parent,
        )
        blockers.append(blocker)

    blockers.sort(key=lambda item: (_safe_sort_key(item.safe_to_kill), item.process_role.casefold(), item.pid))
    report = ShutdownSafetyReport(
        project_root=str(root),
        scan_reason=scan_reason,
        created_at=_now_iso(),
        blockers=tuple(blockers),
        stale_locks_removed=tuple(stale_locks),
    )
    _append_safety_log(layout, f"scan reason={scan_reason} blockers={len(blockers)} stale_locks={len(stale_locks)}")
    return report


def write_report(report: ShutdownSafetyReport, *, project_root_path: Path | str | None = None) -> Path:
    layout = runtime_layout(project_root_path or report.project_root).ensure()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = layout.logs / f"shutdown_safety_report_{stamp}.json"
    report_with_path = replace(report, report_path=str(path))
    _write_json(path, report_with_path.to_payload())
    return path


def apply_shutdown_policy(
    report: ShutdownSafetyReport,
    *,
    kill_safe: bool = False,
    force_all_project_owned: bool = False,
    dry_run: bool = False,
    project_root_path: Path | str | None = None,
) -> ShutdownActionResult:
    attempted: list[int] = []
    stopped: list[int] = []
    skipped: list[str] = []
    errors: list[str] = []

    for blocker in report.blockers:
        should_stop = (kill_safe and blocker.safe_to_kill == "Safe") or force_all_project_owned
        if not should_stop:
            continue
        attempted.append(blocker.pid)
        if not blocker.is_killable:
            skipped.append(f"PID {blocker.pid}: command line does not contain project root or is current process")
            continue
        if dry_run:
            skipped.append(f"PID {blocker.pid}: dry-run")
            continue
        try:
            stop_blocker(blocker, force=force_all_project_owned, project_root_path=project_root_path or report.project_root)
            stopped.append(blocker.pid)
        except Exception as exc:
            errors.append(f"PID {blocker.pid}: {exc}")
    return ShutdownActionResult(tuple(attempted), tuple(stopped), tuple(skipped), tuple(errors), dry_run=dry_run)


def stop_blocker(blocker: ShutdownBlocker, *, force: bool = False, project_root_path: Path | str | None = None) -> None:
    if not blocker.is_killable:
        raise RuntimeError("拒絕停止：PID 不是可驗證的本專案 command line，或是目前程序。")
    layout = runtime_layout(project_root_path).ensure()
    _taskkill(blocker.pid, force=force)
    _mark_job_interrupted(layout, blocker.job_id, return_code=None, reason="shutdown safety stop")
    for lock_file in blocker.lock_files:
        path = Path(lock_file)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
    _append_safety_log(layout, f"{'force' if force else 'graceful'} stop pid={blocker.pid} job={blocker.job_id}")


def report_to_table(report: ShutdownSafetyReport) -> str:
    rows = [
        ["PID", "ProcessName", "SafeToKill", "Role", "Job", "Reason"],
    ]
    for blocker in report.blockers:
        reason = "; ".join(blocker.reasons[:2])
        rows.append(
            [
                str(blocker.pid),
                blocker.process_name,
                blocker.safe_to_kill,
                blocker.process_role,
                blocker.job_id,
                _compact(reason, 76),
            ]
        )
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    lines: list[str] = []
    for index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[column]) for column, value in enumerate(row)))
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect project-owned shutdown blockers.")
    parser.add_argument("--dry-run", action="store_true", help="print blockers without stopping processes")
    parser.add_argument("--kill-safe", action="store_true", help="gracefully stop Safe blockers only")
    parser.add_argument("--kill-all-project-owned", action="store_true", help="force stop every killable project-owned blocker")
    parser.add_argument("--json-report", action="store_true", help="print the JSON report path")
    parser.add_argument("--mock-shutdown-event", action="store_true", help="scan as if Windows requested shutdown")
    args = parser.parse_args(argv)

    reason = "mock.shutdown" if args.mock_shutdown_event else "manual.cli"
    report = scan_shutdown_blockers(scan_reason=reason)
    report_path = write_report(report)
    print(report_to_table(report))
    print(f"\nJSON report: {report_path}")
    if args.dry_run:
        return 0
    result = apply_shutdown_policy(
        report,
        kill_safe=args.kill_safe,
        force_all_project_owned=args.kill_all_project_owned,
        dry_run=False,
    )
    if args.kill_safe or args.kill_all_project_owned:
        print(f"Attempted: {len(result.attempted_pids)}  Stopped: {len(result.stopped_pids)}  Skipped: {len(result.skipped)}")
        for line in result.skipped:
            print(f"SKIP {line}")
        for line in result.errors:
            print(f"ERROR {line}", file=sys.stderr)
        return 0 if result.ok else 2
    if args.json_report:
        print(report_path)
    return 0


def _build_blocker(
    process: ProcessSnapshot,
    *,
    root: Path,
    root_token: str,
    lock: RuntimeProcessLock | None,
    metadata: JobMetadata | None,
    relationships: tuple[FileRelationship, ...],
    process_by_pid: dict[int, ProcessSnapshot],
    children_by_parent: dict[int, list[ProcessSnapshot]],
) -> ShutdownBlocker:
    command_contains_root = _contains_project_root(process, root_token)
    role = _infer_role(process, metadata)
    safe_to_kill = _classify_safe_to_kill(process, metadata)
    related_relationships = _matching_relationships(metadata, relationships)
    lock_files = (lock.lock_file,) if lock and lock.lock_file else ()
    input_files = metadata.input_files if metadata else ()
    output_files = metadata.output_files if metadata else ()
    temp_dirs = _metadata_temp_dirs(metadata, root)
    log_files = tuple(path for path in ((metadata.log_file if metadata else ""), (lock.log_file if lock else "")) if path)
    reasons = _reasons(process, root, command_contains_root, lock, metadata, temp_dirs, output_files)
    parent = process_by_pid.get(process.parent_pid)
    child_pids = tuple(child.pid for child in _descendants(process.pid, children_by_parent))
    consequences = _consequences(safe_to_kill, metadata, output_files, temp_dirs)
    actions = _suggested_actions(safe_to_kill)
    can_auto = safe_to_kill == "Safe" and command_contains_root and process.pid != os.getpid()
    return ShutdownBlocker(
        id=f"process:{process.pid}",
        pid=process.pid,
        process_name=process.process_name or Path(process.executable_path).name or "process",
        parent_pid=process.parent_pid,
        command_summary=(metadata.command_summary if metadata and metadata.command_summary else process.command_summary),
        command_line=process.command_line,
        executable_path=process.executable_path,
        started_at=metadata.started_at if metadata and metadata.started_at else process.started_at,
        job_id=metadata.job_id if metadata else (lock.job_id if lock else ""),
        component=metadata.component if metadata else "",
        process_role=role,
        safe_to_kill=safe_to_kill,
        reasons=reasons,
        lock_files=lock_files,
        temp_dirs=temp_dirs,
        input_files=input_files,
        output_files=output_files,
        log_files=_dedupe(log_files),
        relationships=related_relationships,
        child_pids=child_pids,
        parent_process=f"{parent.process_name} (PID {parent.pid})" if parent else "",
        kill_consequence=consequences,
        suggested_actions=actions,
        project_owned=True,
        command_line_contains_project_root=command_contains_root,
        can_automatically_stop=can_auto,
    )


def _classify_safe_to_kill(process: ProcessSnapshot, metadata: JobMetadata | None) -> SafeToKill:
    if metadata is not None and metadata.safe_to_kill in SAFE_TO_KILL_LEVELS:
        return metadata.safe_to_kill
    command = (process.command_line or process.executable_path or process.process_name).casefold()
    name = process.process_name.casefold()
    if "sqlite" in command or ".db" in command or ".sqlite" in command:
        return "Dangerous"
    if "ffmpeg" in name or "ffmpeg" in command:
        return "Caution"
    if any(token in command for token in ("download", "model", "cache", "output")):
        return "Caution"
    return "Unknown"


def _infer_role(process: ProcessSnapshot, metadata: JobMetadata | None) -> str:
    if metadata is not None and metadata.process_role:
        return metadata.process_role
    command = (process.command_line or "").casefold()
    name = process.process_name.casefold()
    if process.pid == os.getpid():
        return "App 主程序"
    if "worker_host" in command:
        return "Worker process"
    if "ffmpeg" in name or "ffmpeg" in command:
        return "ffmpeg encoder"
    if "model" in command or "onnx" in command or "rapidocr" in command:
        return "Python model runner"
    if "watch" in command or "watcher" in command:
        return "File watcher"
    if "download" in command:
        return "Background downloader"
    if "node.exe" in name:
        return "Worker process"
    if "python" in name:
        return "Python model runner"
    return "Unknown but project-owned"


def _suggested_actions(level: SafeToKill) -> tuple[ShutdownAction, ...]:
    actions: list[ShutdownAction] = ["Wait", "Open log", "Open related folder", "Inspect dependency graph", "Ignore once"]
    if level == "Safe":
        actions.insert(1, "Graceful stop")
        actions.insert(2, "Force stop")
    elif level == "Caution":
        actions.insert(1, "Graceful stop")
        actions.insert(2, "Force stop")
    elif level in {"Dangerous", "Unknown"}:
        actions.append("Cancel shutdown / close")
    return tuple(actions)


def _reasons(
    process: ProcessSnapshot,
    root: Path,
    command_contains_root: bool,
    lock: RuntimeProcessLock | None,
    metadata: JobMetadata | None,
    temp_dirs: tuple[str, ...],
    output_files: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if command_contains_root:
        reasons.append("command line contains project root")
    if lock is not None:
        reasons.append("active .runtime running lock")
    if metadata is not None:
        reasons.append(f"job metadata status={metadata.status}")
    if temp_dirs:
        reasons.append("temp output directory still exists")
    if output_files and metadata is not None and metadata.status not in {"completed", "failed"}:
        reasons.append("temp output incomplete or job still running")
    if "worker_host" in (process.command_line or "").casefold():
        reasons.append("stdout pipe may still be active")
    if process.pid == os.getpid():
        reasons.append("this is the current app process; it is listed but never auto-killed")
    if not reasons:
        reasons.append(f"project-owned process under {root}")
    return tuple(reasons)


def _consequences(
    level: SafeToKill,
    metadata: JobMetadata | None,
    output_files: tuple[str, ...],
    temp_dirs: tuple[str, ...],
) -> tuple[str, ...]:
    if metadata is not None and metadata.kill_consequence:
        return metadata.kill_consequence
    if level == "Safe":
        return (
            "最多需要重跑目前工作。",
            "未完成 job 會標記 failed/interrupted。",
            "不會處理不屬於本專案的程序。",
        )
    if level == "Caution":
        details = [
            "目前輸出檔可能不完整。",
            "cache 或暫存資料可能需要重建。",
            "下次啟動會重新掃描或重跑。",
        ]
        if temp_dirs:
            details.append("暫存檔可能會被刪除或留下等待清理。")
        if output_files:
            details.append("已列出的 output file 需要人工確認完整性。")
        return tuple(details)
    if level == "Dangerous":
        return (
            "不要自動關閉；可能正在寫重要檔案或資料庫。",
            "需要使用者確認後才可 force stop。",
        )
    return (
        "資訊不足，只列出不自動處理。",
        "不會傷害 Windows 系統，因為停止策略只允許本專案 command line / process tree。",
    )


def _windows_process_snapshot(root: Path) -> tuple[ProcessSnapshot, ...]:
    if sys.platform != "win32":
        return (
            ProcessSnapshot(
                pid=os.getpid(),
                process_name=Path(sys.executable).name,
                parent_pid=_parent_pid(),
                command_line=_compact_command([sys.executable, *sys.argv, "--project-root", str(root)]),
                executable_path=sys.executable,
                started_at="",
            ),
        )
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe") or "powershell.exe"
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,"
        "@{Name='CreationDate';Expression={if ($_.CreationDate) {$_.CreationDate.ToString('o')} else {''}}} | "
        "ConvertTo-Json -Compress -Depth 3"
    )
    completed = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=8,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return ()
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return ()
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return ()
    return tuple(ProcessSnapshot.from_payload(item) for item in payload if isinstance(item, dict))


def _load_runtime_locks(layout: RuntimeLayout, process_by_pid: dict[int, ProcessSnapshot]) -> tuple[dict[int, RuntimeProcessLock], list[str]]:
    locks: dict[int, RuntimeProcessLock] = {}
    stale: list[str] = []
    for lock_file in layout.running.glob("*.json"):
        try:
            payload = json.loads(lock_file.read_text(encoding="utf-8"))
            lock = RuntimeProcessLock.from_payload(payload, lock_file=lock_file)
        except Exception:
            continue
        if lock.pid <= 0 or lock.pid not in process_by_pid:
            stale.append(str(lock_file))
            try:
                lock_file.unlink()
            except OSError:
                pass
            continue
        locks[lock.pid] = lock
    return locks, stale


def _load_jobs(layout: RuntimeLayout) -> dict[str, JobMetadata]:
    jobs: dict[str, JobMetadata] = {}
    for path in layout.jobs.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            metadata = JobMetadata.from_payload(payload)
        except Exception:
            continue
        if metadata.job_id:
            jobs[metadata.job_id] = metadata
    return jobs


def _load_relationships(layout: RuntimeLayout) -> tuple[FileRelationship, ...]:
    relationships: list[FileRelationship] = []
    for path in layout.relationships.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries: Any
        if isinstance(payload, dict):
            entries = payload.get("edges") or payload.get("relationships") or []
        else:
            entries = payload
        if not isinstance(entries, list):
            continue
        for item in entries:
            if isinstance(item, dict):
                relationship = FileRelationship.from_payload(item)
                if relationship.source or relationship.target:
                    relationships.append(relationship)
    return tuple(relationships)


def _matching_relationships(metadata: JobMetadata | None, relationships: tuple[FileRelationship, ...]) -> tuple[FileRelationship, ...]:
    if metadata is None:
        return ()
    file_tokens = {_path_token(Path(path)) for path in (*metadata.input_files, *metadata.output_files, *metadata.temp_dirs) if path}
    selected: list[FileRelationship] = []
    for relationship in relationships:
        if relationship.job_id and relationship.job_id == metadata.job_id:
            selected.append(relationship)
            continue
        source = _path_token(Path(relationship.source)) if relationship.source else ""
        target = _path_token(Path(relationship.target)) if relationship.target else ""
        if source in file_tokens or target in file_tokens:
            selected.append(relationship)
    return tuple(selected)


def _metadata_for_process(pid: int, lock: RuntimeProcessLock | None, jobs: dict[str, JobMetadata]) -> JobMetadata | None:
    if lock is not None and lock.job_id in jobs:
        return jobs[lock.job_id]
    for metadata in jobs.values():
        if metadata.pid == pid:
            return metadata
    return None


def _metadata_temp_dirs(metadata: JobMetadata | None, root: Path) -> tuple[str, ...]:
    if metadata is None:
        return ()
    values = list(metadata.temp_dirs)
    layout = runtime_layout(root)
    job_temp = layout.temp / metadata.job_id if metadata.job_id else None
    if job_temp is not None and job_temp.exists():
        values.append(str(job_temp))
    return _dedupe(tuple(values))


def _mark_job_interrupted(layout: RuntimeLayout, job_id: str, *, return_code: int | None, reason: str) -> None:
    if not job_id:
        return
    path = layout.jobs / f"{job_id}.json"
    if not path.exists():
        return
    try:
        metadata = JobMetadata.from_payload(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return
    _write_json(path, replace(metadata, status="interrupted", finished_at=_now_iso(), return_code=return_code).to_payload())
    _append_safety_log(layout, f"job interrupted job={job_id} reason={reason}")


def _children_by_parent(processes: tuple[ProcessSnapshot, ...]) -> dict[int, list[ProcessSnapshot]]:
    children: dict[int, list[ProcessSnapshot]] = {}
    for process in processes:
        if process.parent_pid <= 0:
            continue
        children.setdefault(process.parent_pid, []).append(process)
    return children


def _descendants(pid: int, children_by_parent: dict[int, list[ProcessSnapshot]]) -> list[ProcessSnapshot]:
    found: list[ProcessSnapshot] = []
    pending: queue.SimpleQueue[ProcessSnapshot] = queue.SimpleQueue()
    for child in children_by_parent.get(pid, []):
        pending.put(child)
    while not pending.empty():
        child = pending.get()
        found.append(child)
        for grandchild in children_by_parent.get(child.pid, []):
            pending.put(grandchild)
    return found


def _contains_project_root(process: ProcessSnapshot, root_token: str) -> bool:
    haystacks = [
        _pathish_token(process.command_line),
        _pathish_token(process.executable_path),
    ]
    return any(root_token and root_token in haystack for haystack in haystacks)


def _path_token(path: Path) -> str:
    return _pathish_token(str(path.expanduser().resolve(strict=False)))


def _pathish_token(value: str) -> str:
    return str(value or "").replace("/", "\\").casefold()


def _root(project_root_path: Path | str | None) -> Path:
    return Path(project_root_path) if project_root_path is not None else project_root()


def _safe_level(value: object) -> SafeToKill:
    text = str(value or "Unknown")
    return text if text in SAFE_TO_KILL_LEVELS else "Unknown"  # type: ignore[return-value]


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, Path)):
        text = str(value)
        return (text,) if text else ()
    if isinstance(value, list | tuple | set):
        return tuple(str(item) for item in value if str(item))
    return (str(value),)


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            result.append(value)
            seen.add(key)
    return tuple(result)


def _safe_sort_key(level: SafeToKill) -> int:
    return {"Dangerous": 0, "Unknown": 1, "Caution": 2, "Safe": 3}.get(level, 9)


def _new_job_id(action_id: str) -> str:
    safe_action = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in action_id).strip("-") or "job"
    return f"{safe_action}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _compact(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


def _compact_command(command: list[str] | tuple[str, ...]) -> str:
    return _compact(" ".join(str(part) for part in command), 260)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _append_safety_log(layout: RuntimeLayout, message: str) -> None:
    layout.logs.mkdir(parents=True, exist_ok=True)
    line = f"{_now_iso()} {message}\n"
    with (layout.logs / "safety.log").open("a", encoding="utf-8") as stream:
        stream.write(line)


def _request_terminate(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        pass


def _taskkill(pid: int, *, force: bool) -> None:
    if pid <= 0:
        raise ValueError("PID must be positive")
    if sys.platform != "win32":
        os.kill(pid, 9 if force else 15)
        return
    command = ["taskkill.exe", "/PID", str(pid), "/T"]
    if force:
        command.append("/F")
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "taskkill failed").strip()
        raise RuntimeError(message)


def _parent_pid() -> int:
    if hasattr(os, "getppid"):
        try:
            return os.getppid()
        except OSError:
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
