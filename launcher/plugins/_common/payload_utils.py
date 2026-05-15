from __future__ import annotations

from pathlib import Path
from typing import Any


def files(payload: dict[str, Any]) -> list[Path]:
    return [Path(path) for path in payload["context"].get("files", [])]


def folder(payload: dict[str, Any]) -> Path:
    value = payload["context"].get("folder")
    if not value:
        raise ValueError("此指令需要 context 資料夾")
    return Path(value)


def filter_ext(paths: list[Path], *exts: str) -> list[Path]:
    allowed = {ext.lower() for ext in exts}
    return [path for path in paths if path.suffix.lower() in allowed]
