from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from collections import deque
from pathlib import Path

from launcher.core.context_model import LauncherContext
from launcher.core.safe_cleanup import (
    ScanCancelToken,
    _RunningProcess,
    _can_close_process,
    _close_process,
    _matching_running_processes,
    _restart_manager_processes,
    _wait_for_process_exit,
)

FOLDER_RM_FILE_LIMIT = 200
FOLDER_RM_MAX_DEPTH = 1


@dataclass(frozen=True)
class LockingProcess:
    pid: int
    name: str
    path: Path | None
    reason: str
    can_close: bool
    close_block_reason: str = ""
    app_type: int = 0
    restartable: bool = False
    locked_paths: tuple[Path, ...] = ()

    @property
    def path_text(self) -> str:
        return str(self.path) if self.path else ""

    @property
    def locked_paths_text(self) -> str:
        if not self.locked_paths:
            return ""
        shown = [str(path) for path in self.locked_paths[:3]]
        remaining = len(self.locked_paths) - len(shown)
        if remaining > 0:
            shown.append(f"另 {remaining} 個")
        return "；".join(shown)


@dataclass(frozen=True)
class FileLockReport:
    targets: tuple[Path, ...]
    processes: tuple[LockingProcess, ...]
    scanned_resource_count: int = 0

    @property
    def can_close_count(self) -> int:
        return sum(1 for process in self.processes if process.can_close)


@dataclass
class _ProcessAccumulator:
    process: _RunningProcess
    locked_paths: set[Path]


def targets_from_context(context: LauncherContext) -> tuple[Path, ...]:
    if context.files:
        return tuple(path for path in context.files if str(path).strip())
    if context.folder is not None:
        return (context.folder,)
    return ()


def find_locking_processes(
    targets: tuple[Path, ...] | list[Path],
    cancel_token: ScanCancelToken | None = None,
) -> FileLockReport:
    token = cancel_token or ScanCancelToken()
    target_list = [Path(target) for target in targets if str(target).strip()]
    by_pid: dict[int, _ProcessAccumulator] = {}

    restart_manager_files = _restart_manager_resource_files(target_list, token)
    for file_path in restart_manager_files:
        if token.cancelled():
            _raise_cancelled()
        for process in _restart_manager_processes([file_path]):
            if token.cancelled():
                _raise_cancelled()
            _merge_process(by_pid, process, locked_path=file_path)

    for process in _matching_running_processes(target_list, token):
        if token.cancelled():
            _raise_cancelled()
        _merge_process(by_pid, process)

    locking = [_to_locking_process(entry.process, entry.locked_paths) for entry in by_pid.values()]
    locking.sort(key=lambda item: (not item.can_close, item.name.casefold(), item.pid))
    return FileLockReport(targets=tuple(target_list), processes=tuple(locking), scanned_resource_count=len(restart_manager_files))


def close_locking_process(pid: int, *, force: bool = False) -> None:
    if force:
        _force_close_process(pid)
        return
    _close_process(pid)


def _merge_process(
    processes: dict[int, _ProcessAccumulator],
    process: _RunningProcess,
    *,
    locked_path: Path | None = None,
) -> None:
    current = processes.get(process.pid)
    if current is None:
        current = _ProcessAccumulator(process=process, locked_paths=set())
        processes[process.pid] = current
    elif (not current.process.path and process.path) or (not current.process.reason and process.reason):
        current.process = process.with_reason(current.process.reason or process.reason)
    if locked_path is not None:
        current.locked_paths.add(locked_path)


def _to_locking_process(process: _RunningProcess, locked_paths: set[Path]) -> LockingProcess:
    can_close, block_reason = _can_close_process(process)
    reason = process.reason or "程序路徑與目標相符。"
    locked_paths_tuple = tuple(sorted(locked_paths, key=lambda path: str(path).casefold()))
    return LockingProcess(
        pid=process.pid,
        name=process.name,
        path=process.path,
        reason=reason,
        can_close=can_close,
        close_block_reason=block_reason,
        app_type=process.app_type,
        restartable=process.restartable,
        locked_paths=locked_paths_tuple,
    )


def _restart_manager_resource_files(targets: list[Path], cancel_token: ScanCancelToken) -> tuple[Path, ...]:
    resources: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = _resource_key(path)
        if key in seen:
            return
        seen.add(key)
        resources.append(path)

    for target in targets:
        if cancel_token.cancelled():
            _raise_cancelled()
        try:
            if target.exists() and target.is_file():
                add(target)
            elif target.exists() and target.is_dir():
                remaining = max(0, FOLDER_RM_FILE_LIMIT - len(resources))
                for file_path in _folder_restart_manager_files(target, limit=remaining, max_depth=FOLDER_RM_MAX_DEPTH, cancel_token=cancel_token):
                    add(file_path)
                    if len(resources) >= FOLDER_RM_FILE_LIMIT:
                        return tuple(resources)
        except OSError:
            continue
    return tuple(resources)


def _folder_restart_manager_files(
    root: Path,
    *,
    limit: int,
    max_depth: int,
    cancel_token: ScanCancelToken,
) -> tuple[Path, ...]:
    if limit <= 0:
        return ()
    files: list[Path] = []
    folders: deque[tuple[Path, int]] = deque([(root, 0)])
    while folders and len(files) < limit:
        if cancel_token.cancelled():
            _raise_cancelled()
        folder, depth = folders.popleft()
        try:
            children = sorted(folder.iterdir(), key=lambda path: path.name.casefold())
        except OSError:
            continue
        for child in children:
            if cancel_token.cancelled():
                _raise_cancelled()
            try:
                if child.is_file():
                    files.append(child)
                    if len(files) >= limit:
                        break
                elif depth < max_depth and child.is_dir():
                    folders.append((child, depth + 1))
            except OSError:
                continue
    return tuple(files)


def _resource_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False)).casefold()


def _force_close_process(pid: int) -> None:
    if pid <= 0:
        raise ValueError("PID 不正確。")
    if sys.platform != "win32":
        raise RuntimeError("目前只支援 Windows 結束程序。")
    completed = subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "taskkill failed").strip()
        raise RuntimeError(message)
    _wait_for_process_exit(pid)


def _raise_cancelled() -> None:
    from launcher.core.safe_cleanup import ScanCancelled

    raise ScanCancelled("file lock scan cancelled")
