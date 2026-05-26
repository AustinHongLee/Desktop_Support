from __future__ import annotations

import json
import os
import shutil
import sys
import time
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
REVIEW_LAYER = "review"
REGISTRY_LAYER = "registry"
BLOCKED_LAYER = "blocked"

FILE_KINDS = {"file", "folder", "associated_file", "associated_folder"}


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

    @property
    def executable(self) -> bool:
        if self.layer == BLOCKED_LAYER:
            return False
        if self.layer == REGISTRY_LAYER:
            return self.root_name == "HKCU" and bool(self.registry_key)
        return bool(self.path)


@dataclass(frozen=True)
class CleanupPlan:
    targets: tuple[Path, ...]
    items: tuple[CleanupPlanItem, ...]
    created_at: float

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
    state_cleaned: bool
    errors: tuple[str, ...] = ()


def build_cleanup_plan(context: LauncherContext, *, state_path: Path | None = None) -> CleanupPlan:
    targets = _resolve_targets(context)
    items: list[CleanupPlanItem] = []
    seen_paths: set[str] = set()
    for path in targets:
        items.append(_target_item(path))
        seen_paths.add(_path_key(path))
    items.extend(_associated_items(targets, seen_paths))
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
    return CleanupPlan(targets=tuple(targets), items=tuple(items), created_at=time.time())


def apply_cleanup_plan(
    plan: CleanupPlan,
    selected_item_ids: set[str],
    *,
    include_registry: bool = False,
    quarantine_root: Path | None = None,
) -> CleanupApplyResult:
    session_dir = _session_quarantine_dir(quarantine_root)
    session_dir.mkdir(parents=True, exist_ok=True)
    moved: list[dict[str, Any]] = []
    errors: list[str] = []
    registry_deleted = 0
    state_cleaned = False
    selected = [item for item in plan.items if item.id in selected_item_ids and item.executable]
    for item in selected:
        try:
            if item.kind in FILE_KINDS:
                destination = _move_to_quarantine(Path(item.path), session_dir)
                moved.append({"item": asdict(item), "destination": str(destination)})
            elif item.kind == "state_record":
                _clean_state_references(Path(item.path), plan.targets)
                state_cleaned = True
            elif item.kind == "registry_value" and include_registry:
                _delete_registry_value(item)
                registry_deleted += 1
        except Exception as exc:  # pragma: no cover - integration error path.
            errors.append(f"{item.label}: {exc}")
    manifest = {
        "created_at": time.time(),
        "targets": [str(path) for path in plan.targets],
        "moved": moved,
        "registry_deleted_count": registry_deleted,
        "state_cleaned": state_cleaned,
        "errors": errors,
    }
    manifest_path = session_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return CleanupApplyResult(
        quarantine_dir=session_dir,
        manifest_path=manifest_path,
        moved_count=len(moved),
        registry_deleted_count=registry_deleted,
        state_cleaned=state_cleaned,
        errors=tuple(errors),
    )


def default_quarantine_root() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "EngineeringLauncher" / "SafeCleanupQuarantine"
    return Path.home() / ".engineering_launcher" / "SafeCleanupQuarantine"


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
    for key_path, value_name, value_data in _iter_registry_values(root_handle, base, max_depth=3):
        text = value_data.casefold()
        if any(needle in text for needle in needles):
            value_label = "(Default)" if value_name == "" else value_name
            layer = REGISTRY_LAYER if root_name == "HKCU" else BLOCKED_LAYER
            matches.append(
                CleanupPlanItem(
                    id=f"registry:{root_name}:{key_path}:{value_name}",
                    layer=layer,
                    kind="registry_value",
                    label=f"{root_name}\\{value_label}",
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


def _registry_needles(targets: list[Path]) -> tuple[str, ...]:
    values: set[str] = set()
    for path in targets:
        text = str(path).casefold()
        if text:
            values.add(text)
        if path.name:
            values.add(path.name.casefold())
    return tuple(sorted(values, key=len, reverse=True))


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


def _session_quarantine_dir(root: Path | None = None) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return (root or default_quarantine_root()) / timestamp


def _safe_quarantine_name(path: Path) -> str:
    drive = path.drive.replace(":", "") or "path"
    parts = [drive, *path.parts[-4:]]
    return "__".join(part.strip("\\/") for part in parts if part)


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
