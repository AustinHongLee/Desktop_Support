from __future__ import annotations

import sys

from launcher.core.shutdown_safety import run_cli


def main() -> int:
    if len(sys.argv) == 1:
        from PyQt6.QtWidgets import QApplication

        from launcher.ui.shutdown_safety_dialog import ShutdownSafetyDialog

        app = QApplication.instance() or QApplication(sys.argv)
        dialog = ShutdownSafetyDialog(scan_reason="manual.gui")
        dialog.exec()
        return 0
    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
