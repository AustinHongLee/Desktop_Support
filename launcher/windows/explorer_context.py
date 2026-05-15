from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from launcher.core.context_model import LauncherContext


def get_active_explorer_context() -> LauncherContext | None:
    """Return the most relevant File Explorer folder and selection.

    We prefer the foreground Explorer window. If the launcher itself became
    foreground because the user clicked it, we fall back to the topmost Explorer
    window in Z-order.
    """

    try:
        import pythoncom
        import win32com.client
        import win32con
        import win32gui
    except ImportError:
        return None

    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        try:
            windows = list(shell.Windows())
        except Exception:
            return None
        explorer_windows = [_ExplorerWindow.from_com(window) for window in windows]
        explorer_windows = [window for window in explorer_windows if window is not None]
        if not explorer_windows:
            return None

        by_hwnd = {window.hwnd: window for window in explorer_windows}
        foreground = win32gui.GetForegroundWindow()
        root_foreground = win32gui.GetAncestor(foreground, win32con.GA_ROOT)
        if root_foreground in by_hwnd:
            return by_hwnd[root_foreground].to_context(source="explorer.foreground")
        if foreground in by_hwnd:
            return by_hwnd[foreground].to_context(source="explorer.foreground")

        topmost = _topmost_explorer(by_hwnd, win32gui)
        if topmost is not None:
            return topmost.to_context(source="explorer.topmost")
        return explorer_windows[0].to_context(source="explorer")
    finally:
        pythoncom.CoUninitialize()


def get_open_explorer_contexts() -> list[LauncherContext]:
    """Return contexts for currently open File Explorer windows in Z-order."""

    try:
        import pythoncom
        import win32com.client
        import win32gui
    except ImportError:
        return []

    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        try:
            windows = list(shell.Windows())
        except Exception:
            return []
        explorer_windows = [_ExplorerWindow.from_com(window) for window in windows]
        explorer_windows = [window for window in explorer_windows if window is not None]
        if not explorer_windows:
            return []

        by_hwnd = {window.hwnd: window for window in explorer_windows}
        ordered_windows = _ordered_explorer_windows(by_hwnd, win32gui)
        seen = {window.hwnd for window in ordered_windows}
        ordered_windows.extend(window for window in explorer_windows if window.hwnd not in seen)
        return [window.to_context(source="explorer.window") for window in ordered_windows]
    finally:
        pythoncom.CoUninitialize()


class _ExplorerWindow:
    def __init__(self, hwnd: int, folder: Path | None, files: tuple[Path, ...]) -> None:
        self.hwnd = hwnd
        self.folder = folder
        self.files = files

    @classmethod
    def from_com(cls, window: Any) -> "_ExplorerWindow | None":
        try:
            hwnd = int(window.HWND)
            document = window.Document
            folder = _document_folder(document) or _location_folder(window)
            if folder is None:
                return None
            files = _selected_files(document)
            return cls(hwnd=hwnd, folder=folder, files=files)
        except Exception:
            return None

    def to_context(self, *, source: str) -> LauncherContext:
        return LauncherContext(folder=self.folder, files=self.files, source=source)


def _document_folder(document: Any) -> Path | None:
    try:
        path = document.Folder.Self.Path
    except Exception:
        return None
    if not path:
        return None
    return Path(path)


def _location_folder(window: Any) -> Path | None:
    try:
        location_url = str(window.LocationURL)
    except Exception:
        return None
    parsed = urlparse(location_url)
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path)
    if path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return Path(path.replace("/", "\\"))


def _selected_files(document: Any) -> tuple[Path, ...]:
    try:
        selected = document.SelectedItems()
        return tuple(Path(selected.Item(index).Path) for index in range(selected.Count))
    except Exception:
        return ()


def _topmost_explorer(
    by_hwnd: dict[int, _ExplorerWindow],
    win32gui: Any,
) -> _ExplorerWindow | None:
    windows = _ordered_explorer_windows(by_hwnd, win32gui)
    return windows[0] if windows else None


def _ordered_explorer_windows(
    by_hwnd: dict[int, _ExplorerWindow],
    win32gui: Any,
) -> list[_ExplorerWindow]:
    windows: list[_ExplorerWindow] = []
    hwnd = win32gui.GetTopWindow(None)
    while hwnd:
        if hwnd in by_hwnd and win32gui.IsWindowVisible(hwnd):
            windows.append(by_hwnd[hwnd])
        hwnd = win32gui.GetWindow(hwnd, 2)
    return windows
