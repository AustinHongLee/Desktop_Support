from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from launcher.plugins.iso_tools.workflow.policy import SideEffectGate, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.schema import WorkflowGraph


def json_safe(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]
    return value


class ArtifactStore:
    def __init__(self, run_dir: Path, on_artifact: Any | None = None) -> None:
        self.run_dir = run_dir
        self.artifact_dir = run_dir / "artifacts"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._on_artifact = on_artifact

    def write_json(self, node_id: str, port: str, payload: Any) -> dict[str, Any]:
        safe_node = _safe_name(node_id)
        safe_port = _safe_name(port)
        path = self.artifact_dir / f"{safe_node}.{safe_port}.json"
        text = json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
        data = path.read_bytes()
        ref = {
            "artifact_ref": str(path.relative_to(self.run_dir)).replace("\\", "/"),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        if self._on_artifact is not None:
            self._on_artifact(node_id, port, ref)
        return ref

    def read_json(self, ref: str) -> Any:
        path = self.run_dir / ref
        return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class WorkflowContext:
    run_id: str
    run_dir: Path
    graph: WorkflowGraph
    workflow_inputs: dict[str, Any]
    policy: SideEffectPolicy
    log: Any
    artifacts: ArtifactStore
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    should_cancel: Callable[[], bool] | None = None


class NodeExecutionContext:
    def __init__(
        self,
        *,
        workflow: WorkflowContext,
        node_id: str,
        inputs: dict[str, Any],
        params: dict[str, Any],
        gate: SideEffectGate,
    ) -> None:
        self.workflow = workflow
        self.node_id = node_id
        self.inputs = inputs
        self.params = params
        self._gate = gate
        self.blocked_reason = ""
        self.logs: list[dict[str, Any]] = []

    def request_side_effect(self, kind: str, detail: dict[str, Any] | None = None) -> str:
        return self._gate.request(kind, detail or {})

    def record_side_effect(self, kind: str, decision: str, detail: dict[str, Any] | None = None) -> None:
        self._gate.record(kind, decision, detail or {})

    def emit_event(self, code: str, title: str, detail: str = "", **payload: Any) -> None:
        event = {"code": code, "title": title, "detail": detail, **payload}
        self.logs.append(event)
        self.workflow.log.append_event("node_event", node_id=self.node_id, **json_safe(event))

    def emit_progress(self, *, done: int, total: int, percent: int, message: str = "") -> None:
        self.workflow.log.append_event(
            "node_progress",
            node_id=self.node_id,
            done=done,
            total=total,
            percent=percent,
            message=message,
        )

    def write_artifact(self, port: str, payload: Any) -> dict[str, Any]:
        return self.workflow.artifacts.write_json(self.node_id, port, payload)

    def mark_blocked(self, reason: str) -> None:
        self.blocked_reason = reason

    def should_stop(self) -> bool:
        if self.workflow.should_cancel is None:
            return False
        return bool(self.workflow.should_cancel())


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in value) or "artifact"
