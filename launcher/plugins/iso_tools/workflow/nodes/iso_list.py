from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import NodeSpec, PortSpec


@register_node
class LoadIsoTableNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.load_iso_table",
        display_name="載入 ISO List",
        description="Load ISO table headers and sample records using existing ISO list parsing logic.",
        inputs=(
            PortSpec("iso_list", "path", required=False),
            PortSpec("work_folder", "path", required=False),
            PortSpec("sheet_name", "text", required=False),
            PortSpec("serial_col", "number", required=False),
            PortSpec("line_col", "number", required=False),
        ),
        outputs=(
            PortSpec("iso_source", "json"),
            PortSpec("sample_records", "json"),
            PortSpec("record_count", "number"),
        ),
    )

    def run(self, ctx: Any) -> dict[str, Any]:
        payload = iso_request.load_iso_table(dict(ctx.inputs))
        source = payload.get("source") or {}
        ctx.emit_event("iso_run_log", "ISO run log", "in-process read-only action", written=False)
        return {
            "iso_source": source,
            "sample_records": payload.get("sample_records") or [],
            "record_count": source.get("record_count") or 0,
        }
