from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.workflow.adapters import iso_request
from launcher.plugins.iso_tools.workflow.errors import WorkflowCancelledError
from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
from launcher.plugins.iso_tools.workflow.policy import SPAWNS_WORKER, WRITES_ISO_RUN_LOG, WRITES_JOB_FILES
from launcher.plugins.iso_tools.workflow.registry import register_node
from launcher.plugins.iso_tools.workflow.schema import NodeInstance, NodeSpec, PortSpec, ValidationIssue, WorkflowGraph


TERMINAL_STATES = {"completed", "failed", "cancelled"}


@register_node
class BatchDetectSerialsNode(WorkflowNode):
    spec = NodeSpec(
        node_type="iso.batch_detect_serials",
        display_name="批次判讀流水號",
        description="Run the existing ISO batch worker and poll job progress.",
        inputs=(
            PortSpec("page_folder", "path"),
            PortSpec("work_folder", "path", required=False),
            PortSpec("iso_list", "path", required=False),
            PortSpec("sheet_name", "text", required=False),
            PortSpec("serial_col", "number", required=False),
            PortSpec("line_col", "number", required=False),
            PortSpec("pattern", "text", required=False),
            PortSpec("detect_serials", "bool", required=False),
            PortSpec("confidence_threshold", "number", required=False),
            PortSpec("serial_region", "json", required=False),
            PortSpec("drawing_region", "json", required=False),
        ),
        outputs=(
            PortSpec("rows", "rows"),
            PortSpec("result", "plan"),
            PortSpec("job", "json"),
            PortSpec("iso_run_log", "json"),
        ),
        params_schema={
            "wait_for_completion": {"type": "bool", "default": True},
            "poll_interval_ms": {"type": "number", "default": 500},
            "timeout_s": {"type": "number", "default": 900},
        },
        side_effects=(WRITES_JOB_FILES, WRITES_ISO_RUN_LOG, SPAWNS_WORKER),
    )

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if "page_folder" not in instance.inputs or instance.inputs.get("page_folder") in (None, ""):
            issues.append(_issue("iso.batch_detect_serials requires page_folder; combine_pdf fallback is forbidden", instance.node_id))
        if "combine_pdf" in instance.inputs:
            issues.append(_issue("iso.batch_detect_serials must not accept combine_pdf input", instance.node_id))
        return issues

    def run(self, ctx: Any) -> dict[str, Any]:
        job_id = _job_id(ctx.workflow.run_id, ctx.node_id)
        detail = {"job_id": job_id, "page_folder": ctx.inputs.get("page_folder")}
        decisions = [
            ctx.request_side_effect(WRITES_JOB_FILES, detail),
            ctx.request_side_effect(SPAWNS_WORKER, {"job_id": job_id, "command": "python -m launcher.app.tauri_iso_worker"}),
            ctx.request_side_effect(WRITES_ISO_RUN_LOG, {"job_id": job_id, "writer": "launcher.app.tauri_iso_worker"}),
        ]
        if any(decision != "executed" for decision in decisions):
            return {
                "rows": [],
                "result": {},
                "job": {"job_id": job_id, "state": "skipped", "decisions": decisions},
                "iso_run_log": {},
            }

        _ensure_repo_root_for_worker()
        job = iso_request.start_batch_detect({**ctx.inputs, "combine_pdf": "", "job_id": job_id})
        _emit_job_progress(ctx, job)
        if not bool(ctx.params.get("wait_for_completion")):
            return _outputs(job)

        job = _poll_until_terminal(
            ctx,
            job_id,
            poll_interval_ms=float(ctx.params.get("poll_interval_ms") or 500),
            timeout_s=float(ctx.params.get("timeout_s") or 900),
        )
        state = str(job.get("state") or "")
        if state == "completed":
            return _outputs(job)
        if state == "failed":
            raise RuntimeError(str(job.get("error") or "batch_detect failed"))
        raise RuntimeError(f"batch_detect {state or 'did not complete'}")


def _poll_until_terminal(ctx: Any, job_id: str, *, poll_interval_ms: float, timeout_s: float) -> dict[str, Any]:
    started = time.monotonic()
    interval_s = max(0.001, poll_interval_ms / 1000)
    while True:
        if ctx.should_stop():
            cancelled = iso_request.cancel_iso_job(job_id)
            _emit_job_progress(ctx, cancelled)
            raise WorkflowCancelledError("workflow cancelled")
        job = iso_request.iso_job_status(job_id)
        _emit_job_progress(ctx, job)
        if str(job.get("state") or "") in TERMINAL_STATES:
            return job
        if time.monotonic() - started >= timeout_s:
            cancelled = iso_request.cancel_iso_job(job_id)
            _emit_job_progress(ctx, cancelled)
            raise RuntimeError(f"batch_detect timeout after {timeout_s:g}s")
        time.sleep(interval_s)


def _outputs(job: dict[str, Any]) -> dict[str, Any]:
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    rows = job.get("rows") or result.get("rows") or []
    return {
        "rows": rows,
        "result": result,
        "job": job,
        "iso_run_log": job.get("run_log") or {},
    }


def _emit_job_progress(ctx: Any, job: dict[str, Any]) -> None:
    progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
    ctx.emit_progress(
        done=int(progress.get("done") or 0),
        total=int(progress.get("total") or 0),
        percent=int(progress.get("percent") or 0),
        message=str(job.get("state") or ""),
    )


def _job_id(run_id: str, node_id: str) -> str:
    return f"{run_id}-{node_id}"


def _ensure_repo_root_for_worker() -> None:
    if not Path("launcher/app/tauri_iso_worker.py").exists():
        raise RuntimeError("iso.batch_detect_serials must run from the repository root so the worker module can be imported")


def _issue(message: str, node_id: str) -> ValidationIssue:
    return ValidationIssue(severity="error", code="WF015", message=message, node_id=node_id)
