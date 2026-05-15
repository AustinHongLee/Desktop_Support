from __future__ import annotations

import importlib
import json
import sys
import traceback
from collections.abc import Iterable
from typing import Any


def emit(event_type: str, message: str = "", **data: Any) -> None:
    payload = {"type": event_type, "message": message, **data}
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        action = payload["action"]
        command = action["command"]
        module_name = command["module"]
        entry_name = command["entry"]
        if not module_name or not entry_name:
            raise ValueError("python_module command requires module and entry")

        emit("started", f"Running {action['title']}")
        module = importlib.import_module(module_name)
        entry = getattr(module, entry_name)
        result = entry(payload)
        for event in _events_from_result(result):
            print(json.dumps(event, ensure_ascii=False), flush=True)
        emit("completed", f"Finished {action['title']}")
        return 0
    except Exception as exc:
        emit("error", str(exc), traceback=traceback.format_exc())
        return 1


def _events_from_result(result: Any) -> Iterable[dict[str, Any]]:
    if result is None:
        return []
    if isinstance(result, dict):
        return [result]
    if isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
        return result
    return [{"type": "message", "message": str(result)}]


if __name__ == "__main__":
    raise SystemExit(main())

