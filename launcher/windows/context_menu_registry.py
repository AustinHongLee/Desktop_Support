from __future__ import annotations

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


CONTEXT_MENU_TARGETS = (
    ContextMenuTarget("檔案", r"Software\Classes\*\shell", "%1"),
    ContextMenuTarget("資料夾", r"Software\Classes\Directory\shell", "%1"),
    ContextMenuTarget("資料夾空白處", r"Software\Classes\Directory\Background\shell", "%V"),
    ContextMenuTarget("磁碟機", r"Software\Classes\Drive\shell", "%1"),
)


def expected_context_menu_command(pythonw: Path, argument_token: str) -> str:
    return f'"{pythonw}" -m launcher.app.main --show-existing --context-source explorer.menu --set-context "{argument_token}"'


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


def _install_target(target: ContextMenuTarget, pythonw: Path) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _verb_subkey(target)) as verb_key:
        winreg.SetValueEx(verb_key, "MUIVerb", 0, winreg.REG_SZ, VERB_TITLE)
        winreg.SetValueEx(verb_key, "Icon", 0, winreg.REG_SZ, str(pythonw))
        winreg.SetValueEx(verb_key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _command_subkey(target)) as command_key:
        winreg.SetValueEx(command_key, "", 0, winreg.REG_SZ, expected_context_menu_command(pythonw, target.argument_token))


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
