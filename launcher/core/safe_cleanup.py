from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import ctypes
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from launcher.core.context_model import LauncherContext
from launcher.core.state_store import default_state_path

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only integration.
    winreg = None  # type: ignore[assignment]


SAFE_LAYER = "safe"
PROCESS_LAYER = "process"
REVIEW_LAYER = "review"
REGISTRY_LAYER = "registry"
BLOCKED_LAYER = "blocked"

FILE_KINDS = {"file", "folder", "associated_file", "associated_folder", "install_folder", "shortcut"}
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class OfficialUninstaller:
    id: str
    root_name: str
    registry_key: str
    display_name: str
    uninstall_command: str
    quiet_uninstall_command: str = ""
    install_location: str = ""
    display_icon: str = ""
    match_reason: str = ""
    confidence: float = 0.0

    @property
    def preferred_command(self) -> str:
        return self.quiet_uninstall_command or self.uninstall_command


@dataclass(frozen=True)
class CleanupPlanItem:
    id: str
    layer: str
    kind: str
    label: str
    action: str
    note: str
    checked_default: bool
    path: str = ""
    size_bytes: int = 0
    root_name: str = ""
    registry_key: str = ""
    registry_value_name: str = ""
    registry_value_data: str = ""
    process_id: int = 0
    process_name: str = ""
    process_path: str = ""
    can_close: bool = False

    @property
    def executable(self) -> bool:
        if self.layer == BLOCKED_LAYER:
            return False
        if self.layer == PROCESS_LAYER:
            return self.can_close and self.process_id > 0
        if self.layer == REGISTRY_LAYER:
            return self.root_name == "HKCU" and bool(self.registry_key)
        return bool(self.path)


@dataclass(frozen=True)
class CleanupPlan:
    targets: tuple[Path, ...]
    items: tuple[CleanupPlanItem, ...]
    created_at: float
    official_uninstallers: tuple[OfficialUninstaller, ...] = ()

    def count_by_layer(self, layer: str) -> int:
        return sum(1 for item in self.items if item.layer == layer)

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.items if item.kind in FILE_KINDS)


@dataclass(frozen=True)
class CleanupApplyResult:
    quarantine_dir: Path
    manifest_path: Path
    moved_count: int
    registry_deleted_count: int
    closed_process_count: int
    state_cleaned: bool
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuarantineSession:
    path: Path
    manifest_path: Path
    created_at: float
    targets: tuple[str, ...]
    moved_count: int
    restored_count: int
    size_bytes: int


@dataclass(frozen=True)
class QuarantineRestoreResult:
    restored_count: int
    errors: tuple[str, ...] = ()


def build_cleanup_plan(context: LauncherContext, *, state_path: Path | None = None) -> CleanupPlan:
    targets = _resolve_targets(context)
    items: list[CleanupPlanItem] = []
    seen_paths: set[str] = set()
    for path in targets:
        items.append(_target_item(path))
        seen_paths.add(_path_key(path))
    items.extend(_install_folder_items(targets, seen_paths))
    items.extend(_running_process_items(targets))
    items.extend(_associated_items(targets, seen_paths))
    items.extend(_shortcut_reference_items(targets, seen_paths))
    app_state = state_path or default_state_path()
    if _state_mentions_targets(app_state, targets):
        items.append(
            CleanupPlanItem(
                id="state:engineering_launcher",
                layer=SAFE_LAYER,
                kind="state_record",
                label="工程工具列近期紀錄",
                action="移除紀錄",
                note="只清除本工具列 state.json 內指向目標的 recent/context 紀錄，不碰檔案本體。",
                checked_default=True,
                path=str(app_state),
            )
        )
    uninstallers = tuple(_official_uninstallers(targets))
    items.extend(_registry_reference_items(targets))
    if not items:
        items.append(
            CleanupPlanItem(
                id="empty:no_target",
                layer=BLOCKED_LAYER,
                kind="empty",
                label="沒有可清除目標",
                action="無動作",
                note="目前 Context 沒有檔案或資料夾。請先右鍵選取目標，或把檔案拖到工具列。",
                checked_default=False,
            )
        )
    return CleanupPlan(targets=tuple(targets), items=tuple(items), created_at=time.time(), official_uninstallers=uninstallers)


def run_official_uninstaller(uninstaller: OfficialUninstaller) -> subprocess.Popen:
    command = uninstaller.preferred_command.strip()
    if not command:
        raise ValueError("官方解除安裝指令是空的。")
    return subprocess.Popen(command, shell=True)


def apply_cleanup_plan(
    plan: CleanupPlan,
    selected_item_ids: set[str],
    *,
    include_registry: bool = False,
    include_process_close: bool = False,
    quarantine_root: Path | None = None,
) -> CleanupApplyResult:
    session_dir = _session_quarantine_dir(quarantine_root)
    session_dir.mkdir(parents=True, exist_ok=True)
    moved: list[dict[str, Any]] = []
    errors: list[str] = []
    registry_deleted = 0
    closed_processes = 0
    state_cleaned = False
    selected = [item for item in plan.items if item.id in selected_item_ids and item.executable]
    for item in selected:
        try:
            if item.kind in FILE_KINDS:
                moved.append(_move_item_to_quarantine_record(item, session_dir))
            elif item.kind == "state_record":
                _clean_state_references(Path(item.path), plan.targets)
                state_cleaned = True
            elif item.kind == "registry_value" and include_registry:
                _delete_registry_value(item)
                registry_deleted += 1
            elif item.kind == "running_process" and include_process_close:
                _close_process(item.process_id)
                closed_processes += 1
        except Exception as exc:  # pragma: no cover - integration error path.
            errors.append(f"{item.label}: {exc}")
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "created_at": time.time(),
        "created_by": "EngineeringLauncher SafeCleanup",
        "targets": [str(path) for path in plan.targets],
        "moved": moved,
        "registry_deleted_count": registry_deleted,
        "closed_process_count": closed_processes,
        "state_cleaned": state_cleaned,
        "errors": errors,
    }
    manifest_path = session_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_restore_script(session_dir, moved)
    return CleanupApplyResult(
        quarantine_dir=session_dir,
        manifest_path=manifest_path,
        moved_count=len(moved),
        registry_deleted_count=registry_deleted,
        closed_process_count=closed_processes,
        state_cleaned=state_cleaned,
        errors=tuple(errors),
    )


def default_quarantine_root() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "EngineeringLauncher" / "SafeCleanupQuarantine"
    return Path.home() / ".engineering_launcher" / "SafeCleanupQuarantine"


def list_quarantine_sessions(root: Path | None = None) -> list[QuarantineSession]:
    quarantine_root = root or default_quarantine_root()
    if not quarantine_root.exists():
        return []
    sessions: list[QuarantineSession] = []
    for session_dir in sorted((path for path in quarantine_root.iterdir() if path.is_dir()), reverse=True):
        manifest_path = session_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = load_quarantine_manifest(session_dir)
        except Exception:
            continue
        moved = _manifest_moved_records(manifest)
        sessions.append(
            QuarantineSession(
                path=session_dir,
                manifest_path=manifest_path,
                created_at=float(manifest.get("created_at") or 0.0),
                targets=tuple(str(target) for target in manifest.get("targets", [])),
                moved_count=len(moved),
                restored_count=sum(1 for record in moved if record.get("restored_at")),
                size_bytes=sum(_record_size(record) for record in moved),
            )
        )
    return sessions


def load_quarantine_manifest(session_dir: Path) -> dict[str, Any]:
    manifest_path = session_dir / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def restore_quarantine_items(session_dir: Path, indices: set[int] | None = None) -> QuarantineRestoreResult:
    manifest = load_quarantine_manifest(session_dir)
    moved = _manifest_moved_records(manifest)
    selected = set(range(len(moved))) if indices is None else set(indices)
    restored = 0
    errors: list[str] = []
    for index, record in enumerate(moved):
        if index not in selected or record.get("restored_at"):
            continue
        destination_text = str(record.get("destination") or "")
        original_text = str(record.get("original_path") or record.get("item", {}).get("path") or "")
        destination = Path(destination_text) if destination_text else None
        original = Path(original_text) if original_text else None
        try:
            if destination is None:
                raise ValueError("manifest 缺少隔離位置")
            if original is None:
                raise ValueError("manifest 缺少原始路徑")
            if not destination.exists():
                raise FileNotFoundError(destination)
            if original.exists():
                raise FileExistsError(f"原位置已存在：{original}")
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(original))
            record["restored_at"] = time.time()
            record["restored_to"] = str(original)
            restored += 1
        except Exception as exc:
            label = original_text or destination_text or f"record {index + 1}"
            errors.append(f"{index + 1}. {label}: {exc}")
    manifest["moved"] = moved
    (session_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return QuarantineRestoreResult(restored_count=restored, errors=tuple(errors))


def delete_quarantine_session(session_dir: Path, *, root: Path | None = None) -> None:
    quarantine_root = (root or default_quarantine_root()).resolve(strict=False)
    target = session_dir.resolve(strict=False)
    if not _is_relative_to(target, quarantine_root):
        raise ValueError("只能刪除隔離區底下的 session。")
    if not (target / "manifest.json").exists():
        raise ValueError("找不到 manifest.json，拒絕刪除。")
    shutil.rmtree(target)


def _resolve_targets(context: LauncherContext) -> list[Path]:
    if context.files:
        return [path for path in context.files if str(path).strip()]
    if context.folder is not None:
        return [context.folder]
    return []


def _target_item(path: Path) -> CleanupPlanItem:
    exists = path.exists()
    protected, reason = _is_protected_path(path)
    is_dir = path.is_dir()
    if not exists:
        layer = BLOCKED_LAYER
        note = "目標不存在，不能清除。"
    elif protected:
        layer = BLOCKED_LAYER
        note = f"位於系統保護範圍：{reason}。第一版只列出，不執行。"
    elif is_dir:
        layer = REVIEW_LAYER
        note = "資料夾可能包含大量資料；必須人工確認才會移到隔離區。"
    else:
        layer = SAFE_LAYER
        note = "一般檔案，預設移到隔離區，可從 manifest 追蹤原位置。"
    return CleanupPlanItem(
        id=f"target:{_path_key(path)}",
        layer=layer,
        kind="folder" if is_dir else "file",
        label=path.name or str(path),
        action="移到隔離區" if exists and not protected else "只列出",
        note=note,
        checked_default=layer == SAFE_LAYER,
        path=str(path),
        size_bytes=_safe_size(path),
    )


def _associated_items(targets: list[Path], seen_paths: set[str]) -> list[CleanupPlanItem]:
    items: list[CleanupPlanItem] = []
    for target in targets:
        parent = target.parent
        if not parent.exists() or not parent.is_dir():
            continue
        stem = target.stem if target.is_file() else target.name
        if not stem:
            continue
        try:
            children = sorted(parent.iterdir(), key=lambda item: item.name.casefold())[:2000]
        except OSError:
            continue
        for child in children:
            key = _path_key(child)
            if key in seen_paths or not _looks_associated(stem, child.name):
                continue
            protected, reason = _is_protected_path(child)
            layer = BLOCKED_LAYER if protected else REVIEW_LAYER
            items.append(
                CleanupPlanItem(
                    id=f"associated:{key}",
                    layer=layer,
                    kind="associated_folder" if child.is_dir() else "associated_file",
                    label=child.name,
                    action="移到隔離區" if not protected else "只列出",
                    note=(
                        f"疑似同名衍生檔/資料夾，來源：{target.name}。"
                        if not protected
                        else f"疑似相關，但位於系統保護範圍：{reason}。"
                    ),
                    checked_default=False,
                    path=str(child),
                    size_bytes=_safe_size(child),
                )
            )
            seen_paths.add(key)
    return items


def _install_folder_items(targets: list[Path], seen_paths: set[str]) -> list[CleanupPlanItem]:
    items: list[CleanupPlanItem] = []
    for target in targets:
        if not target.suffix.casefold() == ".exe" or not target.parent.exists():
            continue
        folder = _probable_install_folder(target)
        if folder is None:
            continue
        key = _path_key(folder)
        if key in seen_paths:
            continue
        protected, reason = _is_protected_path(folder)
        items.append(
            CleanupPlanItem(
                id=f"install_folder:{key}",
                layer=BLOCKED_LAYER if protected else REVIEW_LAYER,
                kind="install_folder",
                label=folder.name,
                action="移到隔離區" if not protected else "只列出",
                note=(
                    f"目標是此資料夾內的程式：{target.name}。若要清除整個應用，通常需要檢查安裝根目錄。"
                    if not protected
                    else f"疑似安裝根目錄，但位於系統保護範圍：{reason}。"
                ),
                checked_default=False,
                path=str(folder),
                size_bytes=_safe_size(folder),
            )
        )
        seen_paths.add(key)
    return items


def _shortcut_reference_items(targets: list[Path], seen_paths: set[str]) -> list[CleanupPlanItem]:
    target_keys = {_path_key(path) for path in targets}
    target_stems = {path.stem.casefold() for path in targets if path.stem}
    if not target_keys and not target_stems:
        return []
    items: list[CleanupPlanItem] = []
    for folder in _shortcut_scan_folders():
        if not folder.exists():
            continue
        try:
            shortcuts = list(folder.rglob("*.lnk"))[:1500]
        except OSError:
            continue
        for shortcut in shortcuts:
            key = _path_key(shortcut)
            if key in seen_paths:
                continue
            shortcut_name = shortcut.stem.casefold()
            name_matched = shortcut_name in target_stems or any(stem in shortcut_name for stem in target_stems)
            target_path = _shortcut_target(shortcut) if name_matched else None
            target_matched = _path_key(target_path) in target_keys if target_path else False
            if not target_matched and not name_matched:
                continue
            note = f"捷徑指向目標：{target_path}" if target_matched else "捷徑名稱疑似對應目標；需人工確認。"
            items.append(
                CleanupPlanItem(
                    id=f"shortcut:{key}",
                    layer=REVIEW_LAYER,
                    kind="shortcut",
                    label=shortcut.name,
                    action="移到隔離區",
                    note=note,
                    checked_default=False,
                    path=str(shortcut),
                    size_bytes=_safe_size(shortcut),
                )
            )
            seen_paths.add(key)
            if len(items) >= 40:
                return items
    return items


def _running_process_items(targets: list[Path]) -> list[CleanupPlanItem]:
    if sys.platform != "win32":
        return []
    process_by_pid: dict[int, _RunningProcess] = {}
    for process in _restart_manager_processes([path for path in targets if path.is_file() and path.exists()]):
        process_by_pid[process.pid] = process
    for process in _matching_running_processes(targets):
        existing = process_by_pid.get(process.pid)
        if existing is None:
            process_by_pid[process.pid] = process
        elif not existing.path and process.path:
            process_by_pid[process.pid] = process
    items: list[CleanupPlanItem] = []
    for process in sorted(process_by_pid.values(), key=lambda item: (item.name.casefold(), item.pid)):
        can_close, close_reason = _can_close_process(process)
        note = process.reason
        if not can_close:
            note = f"{note}；不建議直接關閉：{close_reason}"
        else:
            note = f"{note}；可嘗試正常關閉，失敗時請手動關閉。"
        items.append(
            CleanupPlanItem(
                id=f"process:{process.pid}",
                layer=PROCESS_LAYER,
                kind="running_process",
                label=f"{process.name} (PID {process.pid})",
                action="嘗試關閉程序" if can_close else "只列出",
                note=note,
                checked_default=False,
                process_id=process.pid,
                process_name=process.name,
                process_path=str(process.path or ""),
                can_close=can_close,
            )
        )
    return items


def _matching_running_processes(targets: list[Path]) -> list["_RunningProcess"]:
    exact_files = {_path_key(path) for path in targets if path.is_file() or path.suffix}
    roots = [path for path in targets if path.exists() and path.is_dir()]
    roots.extend(folder for target in targets if (folder := _probable_install_folder(target)) is not None)
    root_keys = {_path_key(root) for root in roots}
    matches: list[_RunningProcess] = []
    for process in _iter_process_image_paths():
        path = process.path
        if path is None:
            continue
        process_key = _path_key(path)
        if process_key in exact_files:
            matches.append(process.with_reason("程序執行檔就是目前目標，檔案通常會被 Windows 鎖住。"))
            continue
        for root_key in root_keys:
            if process_key.startswith(root_key + "\\"):
                matches.append(process.with_reason("程序執行檔位於目標資料夾或疑似安裝資料夾內。"))
                break
    return matches


def _registry_reference_items(targets: list[Path]) -> list[CleanupPlanItem]:
    if winreg is None or sys.platform != "win32":
        return []
    needles = _registry_needles(targets)
    if not needles:
        return []
    items: list[CleanupPlanItem] = []
    roots = (
        ("HKCU", winreg.HKEY_CURRENT_USER, _registry_scan_bases("HKCU")),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE, _registry_scan_bases("HKLM")),
    )
    for root_name, root_handle, bases in roots:
        for base in bases:
            items.extend(_scan_registry_base(root_name, root_handle, base, needles, limit=max(0, 40 - len(items))))
            if len(items) >= 40:
                return items
    return items


def _official_uninstallers(targets: list[Path]) -> list[OfficialUninstaller]:
    if winreg is None or sys.platform != "win32":
        return []
    if not targets or not _should_scan_uninstallers(targets):
        return []
    uninstallers: list[OfficialUninstaller] = []
    roots = (
        ("HKCU", winreg.HKEY_CURRENT_USER, _uninstall_registry_bases("HKCU")),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE, _uninstall_registry_bases("HKLM")),
    )
    seen: set[str] = set()
    for root_name, root_handle, bases in roots:
        for key_path, values in _iter_uninstall_entries(root_handle, bases):
            uninstall_command = values.get("UninstallString", "")
            quiet_command = values.get("QuietUninstallString", "")
            if not uninstall_command and not quiet_command:
                continue
            score, reasons = _uninstaller_match_score(values, targets)
            if score < 3:
                continue
            unique = f"{root_name}\\{key_path}".casefold()
            if unique in seen:
                continue
            seen.add(unique)
            uninstallers.append(
                OfficialUninstaller(
                    id=f"uninstaller:{root_name}:{key_path}",
                    root_name=root_name,
                    registry_key=key_path,
                    display_name=values.get("DisplayName", "") or key_path.rsplit("\\", 1)[-1],
                    uninstall_command=uninstall_command,
                    quiet_uninstall_command=quiet_command,
                    install_location=values.get("InstallLocation", ""),
                    display_icon=values.get("DisplayIcon", ""),
                    match_reason="；".join(reasons),
                    confidence=min(1.0, score / 8),
                )
            )
    return sorted(uninstallers, key=lambda item: item.confidence, reverse=True)


def _should_scan_uninstallers(targets: list[Path]) -> bool:
    for target in targets:
        if target.suffix.casefold() in {".exe", ".msi"}:
            return True
        if target.exists() and target.is_dir():
            return True
        if _probable_install_folder(target) is not None:
            return True
    return False


def _iter_uninstall_entries(root_handle: object, bases: tuple[str, ...]):
    for base in bases:
        try:
            with winreg.OpenKey(root_handle, base, 0, winreg.KEY_READ | _registry_view_flag()) as key:
                subkeys = _enum_subkeys(key)
        except OSError:
            continue
        for subkey_name in subkeys:
            key_path = rf"{base}\{subkey_name}"
            try:
                with winreg.OpenKey(root_handle, key_path, 0, winreg.KEY_READ | _registry_view_flag()) as subkey:
                    values = {name: str(data) for name, data in _enum_values(subkey) if isinstance(data, str) and str(data).strip()}
            except OSError:
                continue
            if values:
                yield key_path, values


def _uninstaller_match_score(values: dict[str, str], targets: list[Path]) -> tuple[int, list[str]]:
    weighted_fields = {
        "InstallLocation": 4,
        "DisplayIcon": 4,
        "UninstallString": 3,
        "QuietUninstallString": 3,
        "DisplayName": 1,
    }
    score = 0
    reasons: list[str] = []
    for target in targets:
        target_text = str(target.resolve(strict=False)).casefold()
        target_name = target.name.casefold()
        target_stem = target.stem.casefold()
        install_folder = _probable_install_folder(target)
        folder_text = str(install_folder.resolve(strict=False)).casefold() if install_folder else ""
        for field, weight in weighted_fields.items():
            value = values.get(field, "")
            text = value.casefold()
            if target_text and target_text in text:
                score += weight
                reasons.append(f"{field} 指向目標路徑")
                continue
            if folder_text and folder_text in text:
                score += max(2, weight - 1)
                reasons.append(f"{field} 指向疑似安裝資料夾")
                continue
            if field == "DisplayName" and target_stem and len(target_stem) >= 3 and target_stem in text:
                score += 1
                reasons.append("DisplayName 與目標名稱相近")
            elif field in {"DisplayIcon", "UninstallString", "QuietUninstallString"} and target_name and target_name in text:
                score += 2
                reasons.append(f"{field} 含目標檔名")
    return score, _dedupe_preserve_order(reasons)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _scan_registry_base(
    root_name: str,
    root_handle: object,
    base: str,
    needles: tuple[str, ...],
    *,
    limit: int,
) -> list[CleanupPlanItem]:
    if limit <= 0:
        return []
    matches: list[CleanupPlanItem] = []
    for key_path, value_name, value_data in _iter_registry_values(root_handle, base, max_depth=5):
        text = value_data.casefold()
        if any(needle in text for needle in needles):
            value_label = "(Default)" if value_name == "" else value_name
            layer = REGISTRY_LAYER if root_name == "HKCU" else BLOCKED_LAYER
            key_label = key_path.rsplit("\\", 1)[-1]
            matches.append(
                CleanupPlanItem(
                    id=f"registry:{root_name}:{key_path}:{value_name}",
                    layer=layer,
                    kind="registry_value",
                    label=f"{root_name}\\{key_label}\\{value_label}",
                    action="刪除登錄值" if root_name == "HKCU" else "只列出",
                    note=(
                        "HKCU 登錄值含有目標路徑/名稱；需勾選高風險確認才會刪除。"
                        if root_name == "HKCU"
                        else "系統層 HKLM 登錄值只列出，不由第一版自動刪除。"
                    ),
                    checked_default=False,
                    root_name=root_name,
                    registry_key=key_path,
                    registry_value_name=value_name,
                    registry_value_data=value_data,
                )
            )
            if len(matches) >= limit:
                break
    return matches


def _iter_registry_values(root_handle: object, base: str, *, max_depth: int):
    try:
        with winreg.OpenKey(root_handle, base, 0, winreg.KEY_READ | _registry_view_flag()) as key:
            for value_name, value_data in _enum_values(key):
                if isinstance(value_data, str) and value_data:
                    yield base, value_name, value_data
            if max_depth <= 0:
                return
            for subkey_name in _enum_subkeys(key):
                yield from _iter_registry_values(root_handle, rf"{base}\{subkey_name}", max_depth=max_depth - 1)
    except OSError:
        return


def _delete_registry_value(item: CleanupPlanItem) -> None:
    if winreg is None or item.root_name != "HKCU":
        raise ValueError("只允許刪除 HKCU 登錄值。")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, item.registry_key, 0, winreg.KEY_SET_VALUE | _registry_view_flag()) as key:
        winreg.DeleteValue(key, item.registry_value_name)


def _registry_scan_bases(root_name: str) -> tuple[str, ...]:
    if root_name == "HKCU":
        return (
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU",
            r"Software\Classes\Applications",
            r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
            r"Software\Microsoft\Windows\CurrentVersion\App Paths",
        )
    return (
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\Microsoft\Windows\CurrentVersion\App Paths",
    )


def _uninstall_registry_bases(root_name: str) -> tuple[str, ...]:
    if root_name == "HKCU":
        return (r"Software\Microsoft\Windows\CurrentVersion\Uninstall",)
    return (
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )


def _registry_needles(targets: list[Path]) -> tuple[str, ...]:
    values: set[str] = set()
    for path in targets:
        text = str(path).casefold()
        if text:
            values.add(text)
        if path.name:
            values.add(path.name.casefold())
    return tuple(sorted(values, key=len, reverse=True))


def _probable_install_folder(target: Path) -> Path | None:
    parent = target.parent
    local_app_data = _env_path("LOCALAPPDATA")
    if local_app_data and _is_relative_to(parent, local_app_data / "Programs"):
        try:
            relative = parent.relative_to(local_app_data / "Programs")
        except ValueError:
            return parent
        return (local_app_data / "Programs" / relative.parts[0]) if relative.parts else parent
    if parent.name.casefold() in {target.stem.casefold(), "app", "bin"}:
        return parent
    return None


def _shortcut_scan_folders() -> tuple[Path, ...]:
    folders: list[Path] = []
    app_data = _env_path("APPDATA")
    program_data = _env_path("ProgramData")
    user_profile = _env_path("USERPROFILE")
    public = _env_path("PUBLIC")
    if app_data:
        folders.append(app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if program_data:
        folders.append(program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if user_profile:
        folders.append(user_profile / "Desktop")
    if public:
        folders.append(public / "Desktop")
    return tuple(folders)


def _shortcut_target(shortcut: Path) -> Path | None:
    try:
        import win32com.client  # type: ignore[import-not-found]

        shell = win32com.client.Dispatch("WScript.Shell")
        target = str(shell.CreateShortcut(str(shortcut)).TargetPath or "").strip()
        return Path(target) if target else None
    except Exception:
        return None


def _restart_manager_processes(files: list[Path]) -> list["_RunningProcess"]:
    if not files or sys.platform != "win32":
        return []
    try:
        return _restart_manager_processes_ctypes(files)
    except Exception:
        return []


def _restart_manager_processes_ctypes(files: list[Path]) -> list["_RunningProcess"]:
    rstrtmgr = ctypes.WinDLL("rstrtmgr")
    session = ctypes.c_uint()
    session_key = ctypes.create_unicode_buffer(str(uuid.uuid4()))
    if rstrtmgr.RmStartSession(ctypes.byref(session), 0, session_key) != 0:
        return []
    try:
        file_array = (ctypes.c_wchar_p * len(files))(*(str(path) for path in files))
        if rstrtmgr.RmRegisterResources(session, len(files), file_array, 0, None, 0, None) != 0:
            return []
        needed = ctypes.c_uint(0)
        count = ctypes.c_uint(0)
        reboot_reasons = ctypes.c_uint(0)
        result = rstrtmgr.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reboot_reasons))
        if result != 234 or needed.value == 0:  # ERROR_MORE_DATA
            return []
        process_array = (_RM_PROCESS_INFO * needed.value)()
        count = ctypes.c_uint(needed.value)
        result = rstrtmgr.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), process_array, ctypes.byref(reboot_reasons))
        if result != 0:
            return []
        processes: list[_RunningProcess] = []
        for index in range(count.value):
            info = process_array[index]
            pid = int(info.Process.dwProcessId)
            path = _process_image_path(pid)
            name = str(info.strAppName).strip() or (path.name if path else f"PID {pid}")
            processes.append(
                _RunningProcess(
                    pid=pid,
                    name=name,
                    path=path,
                    reason="Windows 回報此程序可能正在使用目標檔案。",
                    app_type=int(info.ApplicationType),
                    restartable=bool(info.bRestartable),
                )
            )
        return processes
    finally:
        rstrtmgr.RmEndSession(session)


def _iter_process_image_paths() -> list["_RunningProcess"]:
    if sys.platform != "win32":
        return []
    process_ids = _enum_process_ids()
    processes: list[_RunningProcess] = []
    for pid in process_ids:
        if pid <= 0:
            continue
        path = _process_image_path(pid)
        if path is None:
            continue
        processes.append(_RunningProcess(pid=pid, name=path.name, path=path, reason=""))
    return processes


def _enum_process_ids() -> list[int]:
    psapi = ctypes.WinDLL("Psapi.dll")
    DWORD = ctypes.c_ulong
    array_size = 4096
    while True:
        process_ids = (DWORD * array_size)()
        bytes_returned = DWORD()
        if not psapi.EnumProcesses(process_ids, ctypes.sizeof(process_ids), ctypes.byref(bytes_returned)):
            return []
        count = bytes_returned.value // ctypes.sizeof(DWORD)
        if count < array_size:
            return [int(process_ids[index]) for index in range(count)]
        array_size *= 2


def _process_image_path(pid: int) -> Path | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return None
    try:
        buffer_size = ctypes.c_uint(32768)
        buffer = ctypes.create_unicode_buffer(buffer_size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(buffer_size)):
            return None
        return Path(buffer.value)
    finally:
        kernel32.CloseHandle(handle)


def _can_close_process(process: "_RunningProcess") -> tuple[bool, str]:
    if process.pid == os.getpid():
        return False, "這是目前工具本身"
    if process.app_type in {3, 4, 1000}:  # service, Explorer, critical
        return False, "系統/服務/Explorer 類型"
    if process.path is not None:
        protected, reason = _is_protected_path(process.path)
        if protected:
            return False, f"程序位於系統保護範圍：{reason}"
    return True, ""


def _close_process(pid: int) -> None:
    if pid <= 0:
        raise ValueError("PID 不正確。")
    completed = subprocess.run(
        ["taskkill.exe", "/PID", str(pid), "/T"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "taskkill failed").strip()
        raise RuntimeError(message)
    _wait_for_process_exit(pid)


def _wait_for_process_exit(pid: int, *, timeout_seconds: float = 5.0) -> None:
    if sys.platform != "win32":
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel32.OpenProcess(0x00100000, False, int(pid))  # SYNCHRONIZE
    if not process:
        return
    try:
        result = kernel32.WaitForSingleObject(process, int(timeout_seconds * 1000))
        if result == 0x00000102:  # WAIT_TIMEOUT
            raise TimeoutError(f"PID {pid} 尚未釋放，請手動關閉後再重試。")
    finally:
        kernel32.CloseHandle(process)


@dataclass(frozen=True)
class _RunningProcess:
    pid: int
    name: str
    path: Path | None
    reason: str
    app_type: int = 0
    restartable: bool = False

    def with_reason(self, reason: str) -> "_RunningProcess":
        return _RunningProcess(
            pid=self.pid,
            name=self.name,
            path=self.path,
            reason=reason,
            app_type=self.app_type,
            restartable=self.restartable,
        )


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong),
    ]


class _RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", ctypes.c_ulong),
        ("ProcessStartTime", _FILETIME),
    ]


class _RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", _RM_UNIQUE_PROCESS),
        ("strAppName", ctypes.c_wchar * 256),
        ("strServiceShortName", ctypes.c_wchar * 64),
        ("ApplicationType", ctypes.c_uint),
        ("AppStatus", ctypes.c_ulong),
        ("TSSessionId", ctypes.c_ulong),
        ("bRestartable", ctypes.c_int),
    ]


def _state_mentions_targets(state_path: Path, targets: list[Path]) -> bool:
    if not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return _contains_target(data, tuple(str(path).casefold() for path in targets))


def _clean_state_references(state_path: Path, targets: tuple[Path, ...]) -> None:
    if not state_path.exists():
        return
    data = json.loads(state_path.read_text(encoding="utf-8"))
    target_keys = tuple(str(path).casefold() for path in targets)
    backup = state_path.with_name(f"{state_path.stem}.safe_cleanup_backup.json")
    backup.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    cleaned = dict(data) if isinstance(data, dict) else {}
    for list_key in ("recent_files", "recent_folders"):
        values = cleaned.get(list_key, [])
        if isinstance(values, list):
            cleaned[list_key] = [value for value in values if not _contains_target(value, target_keys)]
    contexts = cleaned.get("recent_contexts", [])
    if isinstance(contexts, list):
        cleaned["recent_contexts"] = [item for item in contexts if not _contains_target(item, target_keys)]
    temporary = state_path.with_suffix(".safe_cleanup_tmp")
    temporary.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, state_path)


def _contains_target(value: Any, target_keys: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(_contains_target(item, target_keys) for item in value.values())
    if isinstance(value, list):
        return any(_contains_target(item, target_keys) for item in value)
    return isinstance(value, str) and any(target in value.casefold() for target in target_keys)


def _move_to_quarantine(source: Path, session_dir: Path) -> Path:
    if not source.exists():
        raise FileNotFoundError(source)
    protected, reason = _is_protected_path(source)
    if protected:
        raise PermissionError(f"系統保護路徑不可隔離：{reason}")
    destination = session_dir / _safe_quarantine_name(source)
    index = 2
    while destination.exists():
        destination = session_dir / f"{_safe_quarantine_name(source)}.{index}"
        index += 1
    return Path(shutil.move(str(source), str(destination)))


def _move_item_to_quarantine_record(item: CleanupPlanItem, session_dir: Path) -> dict[str, Any]:
    source = Path(item.path)
    metadata = _path_metadata(source)
    moved_at = time.time()
    destination = _move_to_quarantine(source, session_dir)
    return {
        "item": asdict(item),
        "original_path": str(source),
        "destination": str(destination),
        "original_size_bytes": metadata["size_bytes"],
        "original_mtime": metadata["mtime"],
        "original_sha256": metadata["sha256"],
        "moved_at": moved_at,
    }


def _path_metadata(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        size = stat.st_size if path.is_file() else _safe_size(path)
        mtime = stat.st_mtime
    except OSError:
        size = 0
        mtime = None
    return {
        "size_bytes": size,
        "mtime": mtime,
        "sha256": _sha256_file(path) if path.is_file() else "",
    }


def _sha256_file(path: Path, *, limit_bytes: int = 1024 * 1024 * 512) -> str:
    try:
        if path.stat().st_size > limit_bytes:
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _write_restore_script(session_dir: Path, moved: list[dict[str, Any]]) -> None:
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "# Generated by Engineering Launcher SafeCleanup.",
        "",
    ]
    for record in moved:
        destination = str(record.get("destination") or "")
        original = str(record.get("original_path") or record.get("item", {}).get("path") or "")
        if not destination or not original:
            continue
        lines.extend(
            [
                f"$source = '{_ps_escape(destination)}'",
                f"$target = '{_ps_escape(original)}'",
                "New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $target) | Out-Null",
                "Move-Item -LiteralPath $source -Destination $target",
                "",
            ]
        )
    (session_dir / "Restore.ps1").write_text("\n".join(lines), encoding="utf-8")


def _ps_escape(value: str) -> str:
    return value.replace("'", "''")


def _manifest_moved_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    moved = manifest.get("moved", [])
    return [record for record in moved if isinstance(record, dict)] if isinstance(moved, list) else []


def _record_size(record: dict[str, Any]) -> int:
    try:
        return int(record.get("original_size_bytes") or record.get("item", {}).get("size_bytes") or 0)
    except (TypeError, ValueError):
        return 0


def _session_quarantine_dir(root: Path | None = None) -> Path:
    timestamp = f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    return (root or default_quarantine_root()) / timestamp


def _safe_quarantine_name(path: Path) -> str:
    digest = hashlib.sha1(str(path.resolve(strict=False)).casefold().encode("utf-8", errors="ignore")).hexdigest()[:8]
    name = _sanitize_filename(path.name or "item")
    return f"{digest}__{name}"


def _sanitize_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return cleaned[:180] or "item"


def _safe_size(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        if path.is_dir():
            total = 0
            scanned = 0
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                total += child.stat().st_size
                scanned += 1
                if scanned >= 500:
                    break
            return total
    except OSError:
        return 0
    return 0


def _looks_associated(stem: str, name: str) -> bool:
    candidate = Path(name).stem
    if candidate == stem:
        return True
    lowered = candidate.casefold()
    needle = stem.casefold()
    return any(lowered.startswith(f"{needle}{sep}") for sep in ("_", "-", " ", ".", "(", "["))


def _is_protected_path(path: Path) -> tuple[bool, str]:
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError:
        resolved = path.absolute()
    protected_roots = [item for item in (_env_path("SystemRoot"), _env_path("WINDIR")) if item]
    protected_roots.extend(
        item
        for item in (
            _env_path("ProgramFiles"),
            _env_path("ProgramFiles(x86)"),
            _env_path("ProgramData"),
        )
        if item
    )
    for root in protected_roots:
        if _is_relative_to(resolved, root):
            return True, str(root)
    if resolved.anchor and resolved == Path(resolved.anchor):
        return True, "磁碟根目錄"
    return False, ""


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).resolve(strict=False) if value else None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False)).casefold()


def _registry_view_flag() -> int:
    return getattr(winreg, "KEY_WOW64_64KEY", 0)


def _enum_subkeys(key: object) -> list[str]:
    names: list[str] = []
    index = 0
    while True:
        try:
            names.append(str(winreg.EnumKey(key, index)))
        except OSError:
            return names
        index += 1


def _enum_values(key: object) -> list[tuple[str, object]]:
    values: list[tuple[str, object]] = []
    index = 0
    while True:
        try:
            name, data, _value_type = winreg.EnumValue(key, index)
            values.append((str(name), data))
        except OSError:
            return values
        index += 1
