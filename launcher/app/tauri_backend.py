from __future__ import annotations

import os
import sys
from pathlib import Path

from launcher.core.shutdown_safety import run_cli

PROJECT_ROOT_ENV = "DESKTOP_SUPPORT_PROJECT_ROOT"


def main() -> int:
    argv = list(sys.argv[1:]) or ["--print-json"]
    if "--project-root" not in argv:
        root = os.environ.get(PROJECT_ROOT_ENV)
        if root:
            argv.extend(["--project-root", str(Path(root).resolve(strict=False))])
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
