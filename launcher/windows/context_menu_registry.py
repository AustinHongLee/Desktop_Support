from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from launcher.core.paths import project_root

try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only integration.
    winreg = None  # type: ignore[assignment]


VERB_NAME = "EngineeringLauncherSetContext"
VERB_TITLE = "送到工程工具列"
CUSTOM_VERB_PREFIX = "EngineeringLauncherCustom"


@dataclass(frozen=True)
class ContextMenuTarget:
    label: str
    base_subkey: str
    argument_token: str


@dataclass(frozen=True)
class ContextMenuTargetStatus:
    target: ContextMenuTarget
    installed: bool
    command: str = ""
    expected_command: str = ""
    matches_expected: bool = False
    error: str = ""


@dataclass(frozen=True)
class ExplorerContextMenuStatus:
    pythonw: Path
    pythonw_exists: bool
    targets: tuple[ContextMenuTargetStatus, ...]

    @property
    def installed(self) -> bool:
        return bool(self.targets) and all(target.installed and target.matches_expected for target in self.targets)

    @property
    def any_installed(self) -> bool:
        return any(target.installed for target in self.targets)

    @property
    def needs_update(self) -> bool:
        return any(target.installed and not target.matches_expected for target in self.targets)

    @property
    def summary(self) -> str:
        if self.installed:
            return "已安裝，設定正確"
        if self.needs_update:
            return "已安裝，但需要更新"
        if self.any_installed:
            return "部分安裝"
        return "尚未安裝"


@dataclass(frozen=True)
class ContextMenuLocation:
    label: str
    subkey: str
    kind: str


@dataclass(frozen=True)
class ContextMenuEntry:
    id: str
    label: str
    key_name: str
    root_name: str
    root_handle: object
    location: ContextMenuLocation
    key_path: str
    kind: str
    enabled: bool
    editable: bool
    command: str = ""
    icon: str = ""
    details: str = ""
    disabled_reason: str = ""
    error: str = ""


@dataclass(frozen=True)
class ContextMenuCreateRequest:
    label: str
    target: ContextMenuTarget
    command: str
    icon: str = ""
    key_name: str = ""
    shift_only: bool = False


CONTEXT_MENU_TARGETS = (
    ContextMenuTarget("檔案", r"Software\Classes\*\shell", "%1"),
    ContextMenuTarget("資料夾", r"Software\Classes\Directory\shell", "%1"),
    ContextMenuTarget("資料夾空白處", r"Software\Classes\Directory\Background\shell", "%V"),
    ContextMenuTarget("磁碟機", r"Software\Classes\Drive\shell", "%1"),
)

CUSTOM_CONTEXT_MENU_TARGETS = (
    ContextMenuTarget("檔案", r"Software\Classes\*\shell", "%1"),
    ContextMenuTarget("資料夾", r"Software\Classes\Directory\shell", "%1"),
    ContextMenuTarget("資料夾空白處", r"Software\Classes\Directory\Background\shell", "%V"),
    ContextMenuTarget("桌面空白處", r"Software\Classes\DesktopBackground\Shell", "%V"),
    ContextMenuTarget("磁碟機", r"Software\Classes\Drive\shell", "%1"),
)

INVENTORY_LOCATIONS = (
    ContextMenuLocation("檔案", r"Software\Classes\*\shell", "shell"),
    ContextMenuLocation("檔案 COM", r"Software\Classes\*\shellex\ContextMenuHandlers", "shellex"),
    ContextMenuLocation("所有檔案物件", r"Software\Classes\AllFilesystemObjects\shell", "shell"),
    ContextMenuLocation("所有檔案物件 COM", r"Software\Classes\AllFilesystemObjects\shellex\ContextMenuHandlers", "shellex"),
    ContextMenuLocation("資料夾", r"Software\Classes\Directory\shell", "shell"),
    ContextMenuLocation("資料夾 COM", r"Software\Classes\Directory\shellex\ContextMenuHandlers", "shellex"),
    ContextMenuLocation("資料夾空白處", r"Software\Classes\Directory\Background\shell", "shell"),
    ContextMenuLocation("資料夾空白處 COM", r"Software\Classes\Directory\Background\shellex\ContextMenuHandlers", "shellex"),
    ContextMenuLocation("桌面空白處", r"Software\Classes\DesktopBackground\Shell", "shell"),
    ContextMenuLocation("Folder", r"Software\Classes\Folder\shell", "shell"),
    ContextMenuLocation("Folder COM", r"Software\Classes\Folder\shellex\ContextMenuHandlers", "shellex"),
    ContextMenuLocation("磁碟機", r"Software\Classes\Drive\shell", "shell"),
    ContextMenuLocation("磁碟機 COM", r"Software\Classes\Drive\shellex\ContextMenuHandlers", "shellex"),
)


def expected_context_menu_command(pythonw: Path, argument_token: str) -> str:
    return f'"{pythonw}" -m launcher.app.main --show-existing --context-source explorer.menu --set-context "{argument_token}"'


def expected_iso_workbench_command(pythonw: Path, argument_token: str) -> str:
    return (
        f'"{pythonw}" -m launcher.app.main --show-existing --context-source explorer.menu '
        f'--open-iso-workbench --set-context "{argument_token}"'
    )


def default_pythonw_path(root: Path | None = None) -> Path:
    return (root or project_root()) / ".venv" / "Scripts" / "pythonw.exe"


def context_menu_status(root: Path | None = None) -> ExplorerContextMenuStatus:
    _require_winreg()
    pythonw = default_pythonw_path(root)
    statuses = tuple(_target_status(target, pythonw) for target in CONTEXT_MENU_TARGETS)
    return ExplorerContextMenuStatus(pythonw=pythonw, pythonw_exists=pythonw.exists(), targets=statuses)


def install_context_menu(root: Path | None = None) -> ExplorerContextMenuStatus:
    _require_winreg()
    pythonw = default_pythonw_path(root)
    if not pythonw.exists():
        raise FileNotFoundError(f"找不到 pythonw.exe：{pythonw}")
    for target in CONTEXT_MENU_TARGETS:
        _install_target(target, pythonw)
    return context_menu_status(root)


def uninstall_context_menu() -> ExplorerContextMenuStatus:
    _require_winreg()
    for target in CONTEXT_MENU_TARGETS:
        _delete_tree(_verb_subkey(target))
    return context_menu_status()


def list_context_menu_entries() -> list[ContextMenuEntry]:
    _require_winreg()
    entries: list[ContextMenuEntry] = []
    for root_name, root_handle in _inventory_roots():
        for location in INVENTORY_LOCATIONS:
            entries.extend(_entries_for_location(root_name, root_handle, location))
    return sorted(entries, key=lambda entry: (entry.location.label, entry.root_name, entry.label.casefold(), entry.key_name.casefold()))


def set_context_menu_entry_enabled(entry: ContextMenuEntry, enabled: bool) -> None:
    _require_winreg()
    if entry.kind != "shell":
        raise ValueError("COM shell extension 目前只列出，不直接停用。")
    access = winreg.KEY_SET_VALUE | _registry_view_flag()
    with winreg.OpenKey(entry.root_handle, entry.key_path, 0, access) as key:
        if enabled:
            try:
                winreg.DeleteValue(key, "LegacyDisable")
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, "LegacyDisable", 0, winreg.REG_SZ, "")


def create_context_menu_entry(request: ContextMenuCreateRequest) -> ContextMenuEntry:
    _require_winreg()
    label = request.label.strip()
    command = request.command.strip()
    if not label:
        raise ValueError("右鍵項目名稱不可空白。")
    if not command:
        raise ValueError("右鍵項目指令不可空白。")
    target = _known_custom_target(request.target)
    key_name = request.key_name.strip() or _available_custom_key_name(target.base_subkey, label)
    key_path = rf"{target.base_subkey}\{key_name}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, label)
        winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        if request.icon.strip():
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, request.icon.strip())
        if request.shift_only:
            winreg.SetValueEx(key, "Extended", 0, winreg.REG_SZ, "")
        else:
            try:
                winreg.DeleteValue(key, "Extended")
            except FileNotFoundError:
                pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{key_path}\command") as command_key:
        winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, command)
    location = ContextMenuLocation(target.label, target.base_subkey, "shell")
    return _entry_from_key("HKCU", winreg.HKEY_CURRENT_USER, location, key_name)


def delete_context_menu_entry(entry: ContextMenuEntry) -> None:
    _require_winreg()
    if entry.kind != "shell":
        raise ValueError("COM shell extension 目前只列出，不直接刪除。")
    if entry.root_name != "HKCU":
        raise ValueError("目前只允許刪除目前使用者 HKCU 的右鍵項目。")
    if not is_launcher_managed_entry(entry):
        raise ValueError("這不是工程工具列建立的項目；為避免誤刪系統右鍵，請先用停用。")
    _delete_tree(entry.key_path)


def is_launcher_managed_entry(entry: ContextMenuEntry) -> bool:
    return entry.root_name == "HKCU" and entry.kind == "shell" and (
        entry.key_name == VERB_NAME or entry.key_name.startswith(f"{CUSTOM_VERB_PREFIX}_")
    )


def power_shell_here_command(target: ContextMenuTarget) -> str:
    token = target.argument_token
    if token == "%1" and target.label == "檔案":
        location_expr = f"(Split-Path -LiteralPath '{token}')"
    else:
        location_expr = f"'{token}'"
    return f'powershell.exe -NoExit -Command "Set-Location -LiteralPath {location_expr}"'


def open_with_program_command(program_path: str, argument_token: str) -> str:
    program = program_path.strip().strip('"')
    if not program:
        raise ValueError("請先選擇或輸入要啟動的程式。")
    return f'"{program}" "{argument_token}"'


def run_script_command(script_path: str, argument_token: str) -> str:
    script = script_path.strip().strip('"')
    if not script:
        raise ValueError("請先選擇或輸入要執行的腳本。")
    suffix = Path(script).suffix.casefold()
    if suffix == ".ps1":
        return f'powershell.exe -ExecutionPolicy Bypass -File "{script}" "{argument_token}"'
    if suffix == ".py":
        return f'python.exe "{script}" "{argument_token}"'
    return f'"{script}" "{argument_token}"'


def status_lines(status: ExplorerContextMenuStatus) -> list[str]:
    lines = [
        f"狀態：{status.summary}",
        f"Pythonw：{status.pythonw}",
        f"Pythonw 存在：{'是' if status.pythonw_exists else '否'}",
        "",
    ]
    for target in status.targets:
        if not target.installed:
            result = "未安裝"
        elif target.matches_expected:
            result = "正確"
        else:
            result = "需更新"
        lines.append(f"{target.target.label}：{result}")
        if target.error:
            lines.append(f"  {target.error}")
        elif target.installed and target.command:
            lines.append(f"  {target.command}")
    return lines


def entry_detail_lines(entry: ContextMenuEntry) -> list[str]:
    return [
        f"名稱：{entry.label}",
        f"狀態：{'啟用' if entry.enabled else '停用'}",
        f"位置：{entry.location.label}",
        f"類型：{entry.kind}",
        f"來源：{entry.root_name}",
        f"Key：{entry.key_path}",
        f"可管理：{'是' if entry.editable else '否'}",
        f"原因：{entry.disabled_reason}" if entry.disabled_reason else "",
        f"Icon：{entry.icon}" if entry.icon else "",
        f"Command / CLSID：{entry.command or entry.details}",
        f"錯誤：{entry.error}" if entry.error else "",
    ]


def _target_status(target: ContextMenuTarget, pythonw: Path) -> ContextMenuTargetStatus:
    expected = expected_context_menu_command(pythonw, target.argument_token)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _verb_subkey(target)) as verb_key:
            try:
                mui_verb = winreg.QueryValueEx(verb_key, "MUIVerb")[0]
            except FileNotFoundError:
                mui_verb = ""
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _command_subkey(target)) as command_key:
            command = winreg.QueryValueEx(command_key, "")[0]
        matches = mui_verb == VERB_TITLE and str(command) == expected
        return ContextMenuTargetStatus(target, True, str(command), expected, matches)
    except FileNotFoundError:
        return ContextMenuTargetStatus(target, False, expected_command=expected)
    except OSError as exc:
        return ContextMenuTargetStatus(target, False, expected_command=expected, error=str(exc))


def _entries_for_location(root_name: str, root_handle: object, location: ContextMenuLocation) -> list[ContextMenuEntry]:
    try:
        with winreg.OpenKey(root_handle, location.subkey, 0, winreg.KEY_READ | _registry_view_flag()) as base_key:
            names = _enum_subkeys(base_key)
    except FileNotFoundError:
        return []
    except OSError as exc:
        return [
            ContextMenuEntry(
                id=_entry_id(root_name, location.subkey, location.kind),
                label=f"{location.label} 讀取失敗",
                key_name="",
                root_name=root_name,
                root_handle=root_handle,
                location=location,
                key_path=location.subkey,
                kind=location.kind,
                enabled=False,
                editable=False,
                error=str(exc),
            )
        ]
    return [_entry_from_key(root_name, root_handle, location, name) for name in names]


def _entry_from_key(root_name: str, root_handle: object, location: ContextMenuLocation, key_name: str) -> ContextMenuEntry:
    key_path = rf"{location.subkey}\{key_name}"
    try:
        with winreg.OpenKey(root_handle, key_path, 0, winreg.KEY_READ | _registry_view_flag()) as key:
            default = _query_string(key, "")
            mui_verb = _query_string(key, "MUIVerb")
            icon = _query_string(key, "Icon")
            legacy_disabled = _has_value(key, "LegacyDisable")
            extended = _has_value(key, "Extended")
        command = ""
        details = default
        if location.kind == "shell":
            command = _query_default(root_handle, rf"{key_path}\command")
            label = _display_label(key_name, mui_verb, default)
            editable = True
            disabled_reason = "可能需要系統管理員權限" if root_name == "HKLM" else ""
            enabled = not legacy_disabled
            if extended and enabled:
                details = "只有 Shift + 右鍵時顯示"
        else:
            label = _display_label(key_name, default, "")
            editable = False
            disabled_reason = "COM shell extension 目前只列出，不直接停用。"
            enabled = True
        return ContextMenuEntry(
            id=_entry_id(root_name, key_path, location.kind),
            label=label,
            key_name=key_name,
            root_name=root_name,
            root_handle=root_handle,
            location=location,
            key_path=key_path,
            kind=location.kind,
            enabled=enabled,
            editable=editable,
            command=command,
            icon=icon,
            details=details,
            disabled_reason=disabled_reason,
        )
    except OSError as exc:
        return ContextMenuEntry(
            id=_entry_id(root_name, key_path, location.kind),
            label=key_name,
            key_name=key_name,
            root_name=root_name,
            root_handle=root_handle,
            location=location,
            key_path=key_path,
            kind=location.kind,
            enabled=False,
            editable=False,
            error=str(exc),
        )


def _install_target(target: ContextMenuTarget, pythonw: Path) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _verb_subkey(target)) as verb_key:
        winreg.SetValueEx(verb_key, "MUIVerb", 0, winreg.REG_SZ, VERB_TITLE)
        winreg.SetValueEx(verb_key, "Icon", 0, winreg.REG_SZ, str(pythonw))
        winreg.SetValueEx(verb_key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _command_subkey(target)) as command_key:
        winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, expected_context_menu_command(pythonw, target.argument_token))


def _inventory_roots() -> tuple[tuple[str, object], ...]:
    return (
        ("HKCU", winreg.HKEY_CURRENT_USER),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE),
    )


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


def _query_string(key: object, value_name: str) -> str:
    try:
        value = winreg.QueryValueEx(key, value_name)[0]
    except FileNotFoundError:
        return ""
    return str(value) if value is not None else ""


def _query_default(root_handle: object, subkey: str) -> str:
    try:
        with winreg.OpenKey(root_handle, subkey, 0, winreg.KEY_READ | _registry_view_flag()) as key:
            return _query_string(key, "")
    except OSError:
        return ""


def _has_value(key: object, value_name: str) -> bool:
    try:
        winreg.QueryValueEx(key, value_name)
        return True
    except FileNotFoundError:
        return False


def _display_label(key_name: str, preferred: str, fallback: str) -> str:
    value = preferred or fallback or key_name
    return value.replace("&", "").strip() or key_name


def _known_custom_target(target: ContextMenuTarget) -> ContextMenuTarget:
    for known in CUSTOM_CONTEXT_MENU_TARGETS:
        if known.label == target.label and known.base_subkey.casefold() == target.base_subkey.casefold():
            return known
    raise ValueError(f"不支援的右鍵位置：{target.label}")


def _available_custom_key_name(base_subkey: str, label: str) -> str:
    base_name = _safe_custom_key_name(label)
    candidate = base_name
    index = 2
    while _subkey_exists(winreg.HKEY_CURRENT_USER, rf"{base_subkey}\{candidate}"):
        candidate = f"{base_name}_{index}"
        index += 1
    return candidate


def _safe_custom_key_name(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", label.strip())
    safe = safe.strip("_") or "Action"
    return f"{CUSTOM_VERB_PREFIX}_{safe[:48]}"


def _subkey_exists(root_handle: object, subkey: str) -> bool:
    try:
        with winreg.OpenKey(root_handle, subkey, 0, winreg.KEY_READ | _registry_view_flag()):
            return True
    except FileNotFoundError:
        return False


def _entry_id(root_name: str, key_path: str, kind: str) -> str:
    return f"{root_name}|{kind}|{key_path}"


def _delete_tree(subkey: str) -> None:
    try:
        winreg.DeleteTree(winreg.HKEY_CURRENT_USER, subkey)
    except FileNotFoundError:
        return


def _verb_subkey(target: ContextMenuTarget) -> str:
    return rf"{target.base_subkey}\{VERB_NAME}"


def _command_subkey(target: ContextMenuTarget) -> str:
    return rf"{_verb_subkey(target)}\command"


def _require_winreg() -> None:
    if winreg is None or sys.platform != "win32":
        raise RuntimeError("Explorer 右鍵選單管理只支援 Windows。")


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    action = args[0] if args else "status"
    if action == "install":
        status = install_context_menu()
    elif action == "uninstall":
        status = uninstall_context_menu()
    elif action == "status":
        status = context_menu_status()
    else:
        raise SystemExit(f"Unknown action: {action}")
    print("\n".join(status_lines(status)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
