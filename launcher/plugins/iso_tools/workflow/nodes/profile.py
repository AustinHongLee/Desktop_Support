from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import NodeInstance, NodeSpec, PortSpec, ValidationIssue, WorkflowGraph


@register_node
class LoadProfileNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.load_profile",
        display_name="載入設定檔",
        description="Load the published ISO naming profile, or draft profile when requested.",
        inputs=(
            PortSpec("work_folder", "path", required=False),
            PortSpec("profile_folder", "path", required=False),
        ),
        outputs=(PortSpec("profile", "profile"),),
        params_schema={"prefer_draft": {"type": "bool", "default": False}},
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        if "work_folder" not in instance.inputs and "profile_folder" not in instance.inputs:
            return [_issue("iso.load_profile requires work_folder or profile_folder", instance.node_id)]
        return []

    def run(self, ctx: Any) -> dict[str, Any]:
        payload = iso_request.load_iso_profile(
            dict(ctx.inputs),
            prefer_draft=bool(ctx.params.get("prefer_draft")),
        )
        ctx.emit_event("iso_run_log", "ISO run log", "in-process read-only action", written=False)
        return {"profile": iso_request.profile_from_response(payload)}


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
