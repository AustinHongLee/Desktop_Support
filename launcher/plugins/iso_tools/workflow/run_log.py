from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.workflow.context import json_safe
from launcher.plugins.iso_tools.workflow.policy import SideEffectPolicy, SideEffectRecord
from launcher.plugins.iso_tools.workflow.schema import WorkflowGraph, graph_content_hash


class WorkflowRunLogWriter:
    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        graph: WorkflowGraph,
        mode: str,
        policy: SideEffectPolicy,
        source_run_id: str | None = None,
    ) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.graph = graph
        self.mode = mode
        self.policy = policy
        self.source_run_id = source_run_id
        self.nodes: dict[str, dict[str, Any]] = {}
        self.issues: list[dict[str, Any]] = []
        self.inputs: dict[str, Any] = {}
        self._started_at = _now()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "artifacts").mkdir(exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.graph_path = self.run_dir / "graph.snapshot.json"
        self.graph_path.write_text(
            json.dumps(graph.to_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def start(self, *, inputs: dict[str, Any], topology: list[str]) -> None:
        self.inputs = json_safe(inputs)
        (self.run_dir / "inputs.json").write_text(
            json.dumps(self.inputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.append_event(
            "run_started",
            workflow_id=self.graph.workflow_id,
            graph_hash=graph_content_hash(self.graph),
            mode=self.mode,
            policy=self.policy.to_payload(),
            topology=topology,
        )

    def node_started(self, node_id: str, node_type: str) -> None:
        self.append_event("node_started", node_id=node_id, node_type=node_type)

    def record_side_effect(self, record: SideEffectRecord) -> None:
        self.append_event("side_effect_decision", **record.to_payload())

    def record_artifact(self, node_id: str, port: str, ref: dict[str, Any]) -> None:
        self.append_event("artifact_written", node_id=node_id, port=port, **json_safe(ref))

    def node_finished(
        self,
        *,
        node_id: str,
        status: str,
        started_at: str,
        ended_at: str,
        duration_ms: int,
        outputs: dict[str, Any],
        side_effects: list[dict[str, Any]],
        logs: list[dict[str, Any]] | None = None,
        error: dict[str, Any] | None = None,
        resolved_inputs_digest: dict[str, Any] | None = None,
    ) -> None:
        self.nodes[node_id] = {
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "resolved_inputs_digest": json_safe(resolved_inputs_digest or {}),
            "outputs": outputs,
            "side_effects": side_effects,
            "logs": logs or [],
            "error": error,
        }
        self.append_event(
            "node_finished",
            node_id=node_id,
            status=status,
            duration_ms=duration_ms,
            error=error,
        )

    def append_event(self, event: str, **payload: Any) -> None:
        event_payload = {"ts": _now(), "event": event, "run_id": self.run_id, **json_safe(payload)}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event_payload, ensure_ascii=False, sort_keys=True) + "\n")

    def finish(self, *, status: str, topology: list[str]) -> dict[str, Any]:
        ended_at = _now()
        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "mode": self.mode,
            "workflow_id": self.graph.workflow_id,
            "run_dir": str(self.run_dir),
            "graph_hash": graph_content_hash(self.graph),
            "status": status,
            "started_at": self._started_at,
            "ended_at": ended_at,
            "duration_ms": _duration_ms(self._started_at, ended_at),
            "policy": self.policy.to_payload(),
            "source_run_id": self.source_run_id,
            "topology": topology,
            "inputs": self.inputs,
            "workflow": self.graph.to_payload(),
            "nodes": self.nodes,
            "side_effect_summary": _side_effect_summary(self.nodes),
            "issues": self.issues,
        }
        _write_json_atomic(self.run_dir / "run_log.json", payload)
        self.append_event(
            "run_finished",
            status=status,
            duration_ms=payload["duration_ms"],
            side_effect_summary=payload["side_effect_summary"],
        )
        return payload


def _side_effect_summary(nodes: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    summary = {"executed": [], "blocked": [], "skipped": [], "simulated": []}
    for node_id, payload in nodes.items():
        for record in payload.get("side_effects") or []:
            item = {"node_id": node_id, "kind": record.get("kind"), "decision": record.get("decision")}
            decision = str(record.get("decision") or "")
            if decision == "executed":
                summary["executed"].append(item)
            elif decision.startswith("blocked"):
                summary["blocked"].append(item)
            elif decision in {"simulated"}:
                summary["simulated"].append(item)
            else:
                summary["skipped"].append(item)
    return summary


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _duration_ms(started_at: str, ended_at: str) -> int:
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
    except ValueError:
        return 0
    return max(0, int((end - start).total_seconds() * 1000))
