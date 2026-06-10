from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from launcher.plugins.iso_tools.workflow.schema import NodeInstance, NodeSpec, ValidationIssue, WorkflowGraph


@dataclass
class NodeRunResult:
    node_id: str
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    logs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    side_effects: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    duration_ms: int = 0


class WorkflowNode(ABC):
    spec: ClassVar[NodeSpec]

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        return []

    @abstractmethod
    def run(self, ctx: Any) -> dict[str, Any]:
        raise NotImplementedError
