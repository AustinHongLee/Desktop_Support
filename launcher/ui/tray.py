from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon, QWidget


class LauncherTray:
    def __init__(self, dock: QWidget) -> None:
        self._dock = dock
        icon = dock.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("Engineering Launcher")

        menu = QMenu()
        show_action = QAction("Show")
        show_action.triggered.connect(self._dock.show)
        palette_action = QAction("Command Palette")
        palette_action.triggered.connect(getattr(self._dock, "open_palette"))
        quit_action = QAction("Quit")
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_action)
        menu.addAction(palette_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._dock.show()
            self._dock.raise_()
            self._dock.activateWindow()

