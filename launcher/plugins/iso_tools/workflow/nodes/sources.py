from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import NodeSpec, PortSpec


@register_node
class DiscoverSourcesNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.discover_sources",
        display_name="探索來源",
        description="Read existing folder/profile hints and suggest combine PDF, page folder, and ISO list candidates.",
        inputs=(PortSpec("work_folder", "path"),),
        outputs=(
            PortSpec("profile", "profile"),
            PortSpec("candidates", "json"),
            PortSpec("folder", "path"),
        ),
    )

    def run(self, ctx: Any) -> dict[str, Any]:
        payload = iso_request.discover_sources({"work_folder": ctx.inputs.get("work_folder")})
        ctx.emit_event("iso_run_log", "ISO run log", "in-process read-only action", written=False)
        return {
            "profile": iso_request.profile_from_response(payload),
            "candidates": iso_request.source_candidates_from_response(payload),
            "folder": payload.get("folder") or "",
        }
