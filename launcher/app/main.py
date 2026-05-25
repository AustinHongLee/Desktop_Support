from __future__ import annotations

import argparse
import hashlib
import sys

from launcher.core.context_inbox import ContextInbox
from launcher.core.paths import project_root
from launcher.app.self_test import run_self_test
from launcher.windows.single_instance import SingleInstanceGuard

INSTANCE_MUTEX_VERSION = "v2"


def _run_pyqt(*, start_hidden: bool = False) -> int:
    from PyQt6.QtWidgets import QApplication

    from launcher.app.bootstrap import LauncherBootstrap

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dock, _tray = LauncherBootstrap().create()
    if not start_hidden:
        dock.show()

    return app.exec()


def _run_tk() -> int:
    from launcher.app.tk_main import main as tk_main

    return tk_main()


def _run_context_menu_manager() -> int:
    from PyQt6.QtWidgets import QApplication

    from launcher.ui.explorer_context_menu_dialog import ExplorerContextMenuDialog

    app = QApplication(sys.argv)
    dialog = ExplorerContextMenuDialog()
    dialog.show()
    return app.exec()


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args.context_menu_manager:
        return _run_context_menu_manager()
    if args.self_test:
        return run_self_test()

    submitted_context = False
    if args.set_context:
        ContextInbox().submit(args.set_context, source=args.context_source)
        submitted_context = True

    guard = SingleInstanceGuard(_instance_mutex_name())
    if guard.already_running:
        if args.show_existing and not submitted_context:
            ContextInbox().submit_show()
        print("Engineering Launcher is already running.")
        return 0

    try:
        return _run_pyqt(start_hidden=args.start_hidden)
    except ModuleNotFoundError as exc:
        if exc.name != "PyQt6":
            raise
        print("PyQt6 is not installed; starting built-in Tk test launcher.")
        return _run_tk()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--context-menu-manager", action="store_true", help="open the Explorer right-click registry manager")
    parser.add_argument("--start-hidden", action="store_true", help="start in the system tray without showing the dock")
    parser.add_argument("--show-existing", action="store_true", help="show the existing launcher instance when one is already running")
    parser.add_argument("--set-context", nargs="+", default=[])
    parser.add_argument("--context-source", default="explorer.menu")
    return parser.parse_args(argv)


def _instance_mutex_name() -> str:
    identity = str(project_root().resolve()).casefold()
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
    return f"Local\\EngineeringLauncher_{INSTANCE_MUTEX_VERSION}_{digest}"


if __name__ == "__main__":
    raise SystemExit(main())
