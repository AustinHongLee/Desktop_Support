from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from launcher.core.context_model import LauncherContext


def default_inbox_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "EngineeringLauncher" / "context_request.json"
    return Path.home() / ".engineering_launcher" / "context_request.json"


class ContextInbox:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_inbox_path()

    def submit(self, paths: list[str | Path], *, source: str = "explorer.menu") -> str:
        context = _context_from_shell_paths(paths, source=source)
        request_id = uuid.uuid4().hex
        payload = {
            "id": request_id,
            "created_at": time.time(),
            "context": context.to_payload(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f".{request_id}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)
        return request_id

    def take(self) -> LauncherContext | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            context = LauncherContext.from_payload(payload["context"])
        except Exception:
            context = None
        try:
            self.path.unlink()
        except OSError:
            pass
        return context


def _context_from_shell_paths(paths: list[str | Path], *, source: str) -> LauncherContext:
    resolved = [Path(path) for path in paths if str(path).strip()]
    if len(resolved) == 1 and resolved[0].is_dir():
        return LauncherContext(folder=resolved[0], source=source)
    return LauncherContext.from_paths(resolved, source=source)
