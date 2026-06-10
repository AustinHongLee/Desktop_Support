from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import WRITES_PROFILE
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


@register_node
class SaveDraftProfileNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.save_draft_profile",
        display_name="儲存草稿設定",
        description="只把 ISO 命名設定寫入草稿槽，不發布也不回復版本。",
        inputs=(
            PortSpec("profile", "profile"),
            PortSpec("work_folder", "path"),
            PortSpec("profile_folder", "path", required=False),
        ),
        outputs=(
            PortSpec("profile", "profile"),
            PortSpec("folder", "path"),
            PortSpec("saved", "bool"),
            PortSpec("decision", "text"),
        ),
        side_effects=(WRITES_PROFILE,),
        guarded=True,
        requires_confirm_default=True,
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        profile_input = instance.inputs.get("profile")
        if parse_node_output_ref(profile_input) is None and parse_workflow_input_ref(profile_input) is None:
            return [_issue("iso.save_draft_profile profile must come from a workflow input or upstream node output", instance.node_id)]
        return []

    def run(self, ctx: Any) -> dict[str, Any]:
        profile = dict(ctx.inputs.get("profile") or {})
        detail = {
            "work_folder": ctx.inputs.get("work_folder") or "",
            "profile_folder": ctx.inputs.get("profile_folder") or "",
            "pattern": profile.get("pattern") or "",
            "confidence_threshold": profile.get("confidence_threshold"),
        }
        decision = ctx.request_side_effect(WRITES_PROFILE, detail)
        if decision != "executed":
            ctx.mark_blocked(decision)
            return {
                "profile": profile,
                "folder": ctx.inputs.get("profile_folder") or ctx.inputs.get("work_folder") or "",
                "saved": False,
                "decision": decision,
            }

        payload = iso_request.save_iso_draft_profile(dict(ctx.inputs))
        return {
            "profile": iso_request.profile_from_response(payload),
            "folder": payload.get("folder") or "",
            "saved": True,
            "decision": decision,
        }


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
