from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import WRITES_CSV, WRITES_DEBUG_BUNDLE
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
class ExportPlanCsvNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.export_plan_csv",
        display_name="匯出命名草稿 CSV",
        description="Export existing rows to the backend CSV format.",
        inputs=(
            PortSpec("rows", "rows"),
            PortSpec("work_folder", "path", required=False),
        ),
        outputs=(
            PortSpec("export_path", "path"),
            PortSpec("row_count", "number"),
            PortSpec("selected_count", "number"),
        ),
        params_schema={"export_path": {"type": "text", "default": ""}},
        side_effects=(WRITES_CSV,),
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        if parse_node_output_ref(instance.inputs.get("rows")) is None:
            return [_issue("iso.export_plan_csv rows must be connected from an upstream node output", instance.node_id)]
        return []

    def run(self, ctx: Any) -> dict[str, Any]:
        export_path = str(ctx.params.get("export_path") or "")
        detail = {
            "export_path": export_path or "<backend_default>",
            "row_count": len(ctx.inputs.get("rows") or []),
        }
        decision = ctx.request_side_effect(WRITES_CSV, detail)
        if decision != "executed":
            return {
                "export_path": export_path,
                "row_count": len(ctx.inputs.get("rows") or []),
                "selected_count": _selected_count(ctx.inputs.get("rows") or []),
                "decision": decision,
            }

        payload = iso_request.export_plan_csv({**ctx.inputs, "export_path": export_path})
        return {
            "export_path": payload.get("export_path") or "",
            "row_count": payload.get("row_count") or 0,
            "selected_count": payload.get("selected_count") or 0,
        }


@register_node
class ExportDebugBundleNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.export_debug_bundle",
        display_name="匯出問題包",
        description="Export a sanitized ISO run diagnostic bundle.",
        inputs=(PortSpec("run_id", "text"),),
        outputs=(PortSpec("bundle_path", "path"),),
        params_schema={"export_path": {"type": "text", "default": ""}},
        side_effects=(WRITES_DEBUG_BUNDLE,),
    )

    def run(self, ctx: Any) -> dict[str, Any]:
        export_path = str(ctx.params.get("export_path") or "")
        detail = {"run_id": ctx.inputs.get("run_id"), "export_path": export_path or "<backend_default>"}
        decision = ctx.request_side_effect(WRITES_DEBUG_BUNDLE, detail)
        if decision != "executed":
            return {"bundle_path": export_path, "decision": decision}

        payload = iso_request.export_debug_bundle({"run_id": ctx.inputs.get("run_id"), "export_path": export_path})
        return {
            "bundle_path": payload.get("export_path") or "",
            "included_files": payload.get("included_files") or [],
        }


def _selected_count(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if isinstance(row, dict) and row.get("selected"))


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
