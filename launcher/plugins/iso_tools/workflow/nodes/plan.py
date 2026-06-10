from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import NodeInstance, NodeSpec, PortSpec, ValidationIssue, WorkflowGraph


@register_node
class BuildPlanNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.build_plan",
        display_name="建立命名計畫",
        description="Build rows and pilot checks from an existing page folder. OCR is locked off in this node.",
        inputs=(
            PortSpec("page_folder", "path"),
            PortSpec("work_folder", "path", required=False),
            PortSpec("iso_list", "path", required=False),
            PortSpec("sheet_name", "text", required=False),
            PortSpec("serial_col", "number", required=False),
            PortSpec("line_col", "number", required=False),
            PortSpec("pattern", "text", required=False),
            PortSpec("confidence_threshold", "number", required=False),
            PortSpec("serial_region", "json", required=False),
            PortSpec("drawing_region", "json", required=False),
        ),
        outputs=(
            PortSpec("plan", "plan"),
            PortSpec("rows", "rows"),
            PortSpec("summary", "json"),
            PortSpec("issues", "json"),
            PortSpec("pilot_results", "json"),
        ),
        params_schema={
            "as_rename_plan": {"type": "bool", "default": False},
            "detect_serials": {"type": "bool", "default": False},
        },
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if "page_folder" not in instance.inputs or instance.inputs.get("page_folder") in (None, ""):
            issues.append(_issue("iso.build_plan requires page_folder; combine_pdf fallback is forbidden", instance.node_id))
        if "combine_pdf" in instance.inputs:
            issues.append(_issue("iso.build_plan must not accept combine_pdf input", instance.node_id))
        if bool(instance.params.get("detect_serials")):
            issues.append(_issue("iso.build_plan params.detect_serials must stay false; use iso.batch_detect_serials later", instance.node_id))
        return issues

    def run(self, ctx: Any) -> dict[str, Any]:
        payload = {
            **ctx.inputs,
            "combine_pdf": "",
            "detect_serials": False,
        }
        plan = iso_request.build_iso_plan(
            payload,
            as_rename_plan=bool(ctx.params.get("as_rename_plan")),
        )
        ctx.emit_event("iso_run_log", "ISO run log", "in-process read-only action", written=False)
        return {
            "plan": plan,
            "rows": plan.get("rows") or [],
            "summary": plan.get("summary") or {},
            "issues": plan.get("issues") or [],
            "pilot_results": plan.get("pilot_results") or [],
        }


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
