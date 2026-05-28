from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon, QWidget


class LauncherTray:
    def __init__(self, dock: QWidget) -> None:
        self._dock = dock
        icon = dock.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("工程工具列")

        menu = QMenu()
        show_action = QAction("顯示工具列")
        show_action.triggered.connect(self._show_dock)
        hide_action = QAction("隱藏工具列")
        hide_action.triggered.connect(self._dock.hide)
        palette_action = QAction("開啟指令面板")
        palette_action.triggered.connect(getattr(self._dock, "open_palette"))
        iso_action = QAction("開啟 ISO PDF 命名")
        iso_action.triggered.connect(getattr(self._dock, "open_iso_workbench"))
        lock_action = QAction("開啟檔案佔用檢查器")
        lock_action.triggered.connect(getattr(self._dock, "open_file_lock_checker"))
        quit_action = QAction("結束工程工具列")
        quit_action.triggered.connect(self._quit)
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(palette_action)
        menu.addAction(iso_action)
        menu.addAction(lock_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_dock()

    def _show_dock(self) -> None:
        self._dock.show()
        self._dock.raise_()
        self._dock.activateWindow()

    def _quit(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.quit()
