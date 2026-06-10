from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import RENAMES_FILES
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import (
    NodeInstance,
    NodeSpec,
    PortSpec,
    ValidationIssue,
    WorkflowGraph,
    parse_node_output_ref,
    parse_workflow_input_ref,
)


@register_node
class ApplyRenameNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.apply_rename",
        display_name="套用更名",
        description="驗證或套用 ISO PDF 更名列；預設 dry run 只預覽，不會更名。",
        inputs=(
            PortSpec("rows", "rows"),
            PortSpec("work_folder", "path", required=False),
        ),
        outputs=(
            PortSpec("result", "json"),
            PortSpec("rows", "rows"),
            PortSpec("renamed_count", "number"),
            PortSpec("dry_run", "bool"),
            PortSpec("decision", "text"),
        ),
        params_schema={
            "dry_run": {"type": "bool", "default": True},
            "only_ready": {"type": "bool", "default": True},
        },
        side_effects=(RENAMES_FILES,),
        guarded=True,
        requires_confirm_default=True,
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        rows_input = instance.inputs.get("rows")
        if parse_node_output_ref(rows_input) is None and parse_workflow_input_ref(rows_input) is None:
            return [_issue("iso.apply_rename rows must come from a workflow input or upstream node output", instance.node_id)]
        return []

    def run(self, ctx: Any) -> dict[str, Any]:
        rows = ctx.inputs.get("rows") or []
        dry_run = bool(ctx.params.get("dry_run", True))
        only_ready = bool(ctx.params.get("only_ready", True))
        detail = {
            "dry_run": dry_run,
            "only_ready": only_ready,
            "row_count": _row_count(rows),
            "selected_count": _selected_count(rows, only_ready=only_ready),
        }

        if dry_run:
            ctx.record_side_effect(RENAMES_FILES, "simulated", detail)
            result = iso_request.apply_iso_plan(
                {**ctx.inputs, "rows": rows},
                dry_run=True,
                only_ready=only_ready,
            )
            return _outputs(result, dry_run=True, decision="simulated")

        decision = ctx.request_side_effect(RENAMES_FILES, detail)
        if decision != "executed":
            ctx.mark_blocked(decision)
            result = {
                "schema_version": 1,
                "action": "apply",
                "dry_run": False,
                "renamed_count": 0,
                "rows": [],
                "message": "更名被 workflow side-effect policy 阻擋。",
            }
            return _outputs(result, dry_run=False, decision=decision)

        result = iso_request.apply_iso_plan(
            {**ctx.inputs, "rows": rows},
            dry_run=False,
            only_ready=only_ready,
        )
        return _outputs(result, dry_run=False, decision=decision)


def _outputs(result: dict[str, Any], *, dry_run: bool, decision: str) -> dict[str, Any]:
    return {
        "result": result,
        "rows": result.get("rows") or [],
        "renamed_count": result.get("renamed_count") or 0,
        "dry_run": dry_run,
        "decision": decision,
    }


def _row_count(rows: Any) -> int:
    return len(rows) if isinstance(rows, list) else 0


def _selected_count(rows: Any, *, only_ready: bool) -> int:
    if not isinstance(rows, list):
        return 0
    count = 0
    for row in rows:
        if not isinstance(row, dict) or not row.get("selected"):
            continue
        if only_ready and row.get("status") != "ready":
            continue
        count += 1
    return count


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
