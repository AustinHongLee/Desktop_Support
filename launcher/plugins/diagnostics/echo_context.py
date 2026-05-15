from __future__ import annotations

import time
from typing import Any


def echo_context(payload: dict[str, Any]) -> list[dict[str, Any]]:
    context = payload["context"]
    files = context.get("files") or []
    folder = context.get("folder") or "(none)"
    return [
        {"type": "message", "message": f"Context 來源：{context.get('source')}"},
        {"type": "message", "message": f"資料夾：{folder}"},
        {"type": "message", "message": f"檔案數：{len(files)}"},
    ]


def wait_30_seconds(payload: dict[str, Any]) -> list[dict[str, Any]]:  # noqa: ARG001
    time.sleep(30)
    return [{"type": "message", "message": "等待完成"}]
