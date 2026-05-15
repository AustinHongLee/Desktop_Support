from __future__ import annotations

import argparse
import sys

from launcher.core.context_inbox import ContextInbox
from launcher.app.self_test import run_self_test
from launcher.windows.single_instance import SingleInstanceGuard


def _run_pyqt() -> int:
    from PyQt6.QtWidgets import QApplication

    from launcher.app.bootstrap import LauncherBootstrap

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dock, _tray = LauncherBootstrap().create()
    dock.show()

    return app.exec()


def _run_tk() -> int:
    from launcher.app.tk_main import main as tk_main

    return tk_main()


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args.self_test:
        return run_self_test()

    if args.set_context:
        ContextInbox().submit(args.set_context, source=args.context_source)

    guard = SingleInstanceGuard("Local\\EngineeringLauncher")
    if guard.already_running:
        print("Engineering Launcher is already running.")
        return 0

    try:
        return _run_pyqt()
    except ModuleNotFoundError as exc:
        if exc.name != "PyQt6":
            raise
        print("PyQt6 is not installed; starting built-in Tk test launcher.")
        return _run_tk()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--set-context", nargs="+", default=[])
    parser.add_argument("--context-source", default="explorer.menu")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
