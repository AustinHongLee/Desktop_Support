from __future__ import annotations

from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import MAY_WRITE_PAGE_PDFS
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


@register_node
class SplitPdfNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.split_pdf",
        display_name="拆頁 PDF",
        description="Resolve page PDFs and explicitly split a combine PDF when needed.",
        inputs=(
            PortSpec("combine_pdf", "path", required=False),
            PortSpec("work_folder", "path", required=False),
            PortSpec("page_folder", "path", required=False),
        ),
        outputs=(
            PortSpec("page_folder", "path"),
            PortSpec("pages", "json"),
            PortSpec("pdf_count", "number"),
            PortSpec("source_kind", "text"),
        ),
        params_schema={"force": {"type": "bool", "default": False}},
        side_effects=(MAY_WRITE_PAGE_PDFS,),
    )

    def run(self, ctx: Any) -> dict[str, Any]:
        prediction = iso_request.predict_split_pdf(ctx.inputs)
        if not prediction.get("would_write"):
            ctx.record_side_effect(MAY_WRITE_PAGE_PDFS, "skipped_not_needed", prediction)
            payload = iso_request.split_iso_pdf(dict(ctx.inputs))
            return _split_outputs(payload)

        decision = ctx.request_side_effect(MAY_WRITE_PAGE_PDFS, prediction)
        if decision != "executed":
            return {
                "page_folder": prediction.get("page_folder") or "",
                "pages": [],
                "pdf_count": 0,
                "source_kind": prediction.get("source_kind") or "combine_pdf",
                "decision": decision,
            }

        payload = iso_request.split_iso_pdf(dict(ctx.inputs))
        return _split_outputs(payload)


def _split_outputs(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source") or {}
    return {
        "page_folder": source.get("page_folder") or "",
        "pages": payload.get("pages") or [],
        "pdf_count": source.get("pdf_count") or 0,
        "source_kind": source.get("kind") or "",
    }
