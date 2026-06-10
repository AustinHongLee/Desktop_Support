from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.workflow import WORKFLOW_SCHEMA_VERSION


NODE_REF_RE = re.compile(r"^\$nodes\.([A-Za-z0-9_.-]+)\.outputs\.([A-Za-z0-9_.-]+)$")
WORKFLOW_INPUT_REF_RE = re.compile(r"^\$workflow\.inputs\.([A-Za-z0-9_.-]+)$")


@dataclass(frozen=True)
class PortSpec:
    name: str
    type: str
    required: bool = True
    description: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "description": self.description,
        }


@dataclass(frozen=True)
class NodeSpec:
    node_type: str
    display_name: str
    description: str
    inputs: tuple[PortSpec, ...]
    outputs: tuple[PortSpec, ...]
    params_schema: dict[str, Any] = field(default_factory=dict)
    side_effects: tuple[str, ...] = ()
    guarded: bool = False
    requires_confirm_default: bool = False

    def input_names(self) -> set[str]:
        return {port.name for port in self.inputs}

    def output_names(self) -> set[str]:
        return {port.name for port in self.outputs}

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_type": self.node_type,
            "display_name": self.display_name,
            "description": self.description,
            "inputs": [port.to_payload() for port in self.inputs],
            "outputs": [port.to_payload() for port in self.outputs],
            "params_schema": self.params_schema,
            "side_effects": list(self.side_effects),
            "guarded": self.guarded,
            "requires_confirm_default": self.requires_confirm_default,
        }


@dataclass
class NodeInstance:
    node_id: str
    node_type: str
    display_name: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    requires_confirm: bool | None = None
    side_effects: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "display_name": self.display_name,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "params": self.params,
            "enabled": self.enabled,
            "side_effects": list(self.side_effects),
        }
        if self.requires_confirm is not None:
            payload["requires_confirm"] = self.requires_confirm
        return payload


@dataclass(frozen=True, order=True)
class EdgeSpec:
    from_node: str
    from_output: str
    to_node: str
    to_input: str

    def to_payload(self) -> dict[str, str]:
        return {
            "from_node": self.from_node,
            "from_output": self.from_output,
            "to_node": self.to_node,
            "to_input": self.to_input,
        }

    def label(self) -> str:
        return f"{self.from_node}.{self.from_output}->{self.to_node}.{self.to_input}"


@dataclass
class WorkflowGraph:
    schema_version: int
    workflow_id: str
    display_name: str
    description: str
    inputs: dict[str, Any]
    nodes: list[NodeInstance]
    edges: list[EdgeSpec]
    metadata: dict[str, Any] = field(default_factory=dict)

    def node_map(self) -> dict[str, NodeInstance]:
        return {node.node_id: node for node in self.nodes}

    def to_payload(self, *, include_metadata: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "display_name": self.display_name,
            "description": self.description,
            "inputs": self.inputs,
            "nodes": [node.to_payload() for node in self.nodes],
            "edges": [edge.to_payload() for edge in self.edges],
        }
        if include_metadata and self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    node_id: str = ""
    edge: str = ""

    def to_payload(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "node_id": self.node_id,
            "edge": self.edge,
        }


def load_workflow(path: Path) -> WorkflowGraph:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_graph(payload)


def save_workflow(graph: WorkflowGraph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph.to_payload(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def normalize_graph(raw: dict[str, Any]) -> WorkflowGraph:
    nodes = [_node_from_payload(item) for item in raw.get("nodes") or []]
    inferred_edges = _infer_edges(nodes)
    declared_edges = [_edge_from_payload(item) for item in raw.get("edges") or []]
    metadata = dict(raw.get("metadata") or {})
    if declared_edges:
        metadata["_inferred_edges"] = [edge.to_payload() for edge in inferred_edges]
        metadata["_declared_edges"] = [edge.to_payload() for edge in declared_edges]
        edges = declared_edges
    else:
        edges = inferred_edges
    return WorkflowGraph(
        schema_version=int(raw.get("schema_version", WORKFLOW_SCHEMA_VERSION)),
        workflow_id=str(raw.get("workflow_id") or ""),
        display_name=str(raw.get("display_name") or ""),
        description=str(raw.get("description") or ""),
        inputs=dict(raw.get("inputs") or {}),
        nodes=nodes,
        edges=edges,
        metadata=metadata,
    )


def graph_content_hash(graph: WorkflowGraph) -> str:
    payload = graph.to_payload(include_metadata=False)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_node_output_ref(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    match = NODE_REF_RE.match(value)
    if not match:
        return None
    return match.group(1), match.group(2)


def parse_workflow_input_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = WORKFLOW_INPUT_REF_RE.match(value)
    return match.group(1) if match else None


def is_ref(value: Any) -> bool:
    return parse_node_output_ref(value) is not None or parse_workflow_input_ref(value) is not None


def _node_from_payload(payload: dict[str, Any]) -> NodeInstance:
    return NodeInstance(
        node_id=str(payload.get("node_id") or ""),
        node_type=str(payload.get("node_type") or ""),
        display_name=str(payload.get("display_name") or ""),
        inputs=dict(payload.get("inputs") or {}),
        outputs={str(k): str(v) for k, v in dict(payload.get("outputs") or {}).items()},
        params=dict(payload.get("params") or {}),
        enabled=bool(payload.get("enabled", True)),
        requires_confirm=payload.get("requires_confirm") if "requires_confirm" in payload else None,
        side_effects=tuple(str(item) for item in payload.get("side_effects") or ()),
    )


def _edge_from_payload(payload: dict[str, Any]) -> EdgeSpec:
    return EdgeSpec(
        from_node=str(payload.get("from_node") or ""),
        from_output=str(payload.get("from_output") or ""),
        to_node=str(payload.get("to_node") or ""),
        to_input=str(payload.get("to_input") or ""),
    )


def _infer_edges(nodes: list[NodeInstance]) -> list[EdgeSpec]:
    edges: set[EdgeSpec] = set()
    for node in nodes:
        for input_name, value in node.inputs.items():
            parsed = parse_node_output_ref(value)
            if parsed is None:
                continue
            from_node, from_output = parsed
            edges.add(EdgeSpec(from_node, from_output, node.node_id, str(input_name)))
    return sorted(edges)
