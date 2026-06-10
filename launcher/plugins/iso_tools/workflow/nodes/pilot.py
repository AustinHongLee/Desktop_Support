from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import (
    NodeInstance,
    NodeSpec,
    PortSpec,
    ValidationIssue,
    WorkflowGraph,
    parse_node_output_ref,
)


@register_node
class PilotReportNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.pilot_report",
        display_name="Pilot 檢查",
        description="Build the Pilot P01-P15 report from existing rows. Fallback plan building is forbidden.",
        inputs=(
            PortSpec("rows", "rows"),
            PortSpec("plan", "plan", required=False),
            PortSpec("job", "json", required=False),
            PortSpec("work_folder", "path", required=False),
            PortSpec("confidence_threshold", "number", required=False),
        ),
        outputs=(
            PortSpec("pilot_results", "json"),
            PortSpec("pilot_summary", "json"),
        ),
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        if parse_node_output_ref(instance.inputs.get("rows")) is None:
            return [_issue("iso.pilot_report rows must be connected from an upstream node output", instance.node_id)]
        return []

    def run(self, ctx: Any) -> dict[str, Any]:
        payload = iso_request.pilot_report(dict(ctx.inputs))
        ctx.emit_event("iso_run_log", "ISO run log", "in-process read-only action", written=False)
        return {
            "pilot_results": payload.get("items") or [],
            "pilot_summary": payload.get("summary") or {},
        }


@register_node
class RoiDistributionNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.roi_distribution",
        display_name="ROI 信心分布",
        description="Summarize row confidence buckets from existing rows. Fallback plan building is forbidden.",
        inputs=(
            PortSpec("rows", "rows"),
            PortSpec("confidence_threshold", "number", required=False),
        ),
        outputs=(PortSpec("distribution", "json"),),
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        if parse_node_output_ref(instance.inputs.get("rows")) is None:
            return [_issue("iso.roi_distribution rows must be connected from an upstream node output", instance.node_id)]
        return []

    def run(self, ctx: Any) -> dict[str, Any]:
        payload = iso_request.roi_distribution(dict(ctx.inputs))
        ctx.emit_event("iso_run_log", "ISO run log", "in-process read-only action", written=False)
        return {"distribution": payload}


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
