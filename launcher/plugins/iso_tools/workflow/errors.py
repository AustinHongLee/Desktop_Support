from __future__ import annotations

from dataclasses import dataclass


class WorkflowError(Exception):
    """Base class for workflow engine failures."""


@dataclass(frozen=True)
class WorkflowIssue:
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


class GraphValidationError(WorkflowError):
    def __init__(self, issues: list[WorkflowIssue]):
        self.issues = issues
        super().__init__("workflow graph validation failed")


class NodeExecutionError(WorkflowError):
    def __init__(self, node_id: str, message: str):
        self.node_id = node_id
        super().__init__(message)


class SideEffectBlockedError(WorkflowError):
    def __init__(self, node_id: str, kind: str, decision: str):
        self.node_id = node_id
        self.kind = kind
        self.decision = decision
        super().__init__(f"side effect blocked: {node_id}:{kind}:{decision}")


class ReplayViolationError(WorkflowError):
    pass


class WorkflowCancelledError(WorkflowError):
    pass


class SideEffectAccountingError(WorkflowError):
    pass


class UndeclaredSideEffectError(WorkflowError):
    def __init__(self, node_id: str, kind: str):
        self.node_id = node_id
        self.kind = kind
        super().__init__(f"node {node_id} requested undeclared side effect: {kind}")
