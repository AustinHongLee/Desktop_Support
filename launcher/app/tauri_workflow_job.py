from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    _job_dir,
    _normalize_request,
    _now,
    _read_json,
    _workflow_graph_from_request,
    _workflow_node_id_required,
    _workflow_policy_from_request,
    _workflow_run_dir_required,
    _workflow_run_root,
    _write_json,
)
from launcher.plugins.iso_tools.workflow.executor import replay_workflow, run_from_node, run_single_node, run_workflow


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("missing workflow job directory", file=sys.stderr)
        return 2
    job_dir = Path(argv[0])
    try:
        run_job(job_dir)
        return 0
    except Exception as exc:
        try:
            _fail_job(job_dir, exc)
        except Exception:
            pass
        print(str(exc), file=sys.stderr)
        return 1


def run_job(job_dir: Path) -> dict[str, Any]:
    request_payload = _read_json(job_dir / "request.json")
    shadow_payload = dict(request_payload.get("shadow") or {}) if isinstance(request_payload.get("shadow"), dict) else None
    request = IsoWorkflowRequest(**_normalize_request(request_payload))
    job = _read_json(job_dir / "job.json")
    job.update({"state": "running", "updated_at": _now(), "error": ""})
    _write_json(job_dir / "job.json", job)

    mode = request.workflow_mode or "run"
    policy = _workflow_policy_from_request(request)
    callback = _progress_callback(job_dir)
    should_cancel = lambda: (job_dir / "cancel.json").exists()

    if request.action == "workflow_run_node":
        result = run_single_node(
            _workflow_run_dir_required(request),
            _workflow_node_id_required(request),
            run_root=_workflow_run_root(),
            policy=policy,
            should_cancel=should_cancel,
            on_update=callback,
        )
    elif request.action == "workflow_run_from":
        result = run_from_node(
            _workflow_run_dir_required(request),
            _workflow_node_id_required(request),
            inputs=request.workflow_inputs or {},
            run_root=_workflow_run_root(),
            policy=policy,
            should_cancel=should_cancel,
            on_update=callback,
        )
    elif mode == "replay":
        result = replay_workflow(
            _workflow_run_dir_required(request),
            run_root=_workflow_run_root(),
            policy=policy,
            should_cancel=should_cancel,
            on_update=callback,
        )
    else:
        result = run_workflow(
            _workflow_graph_from_request(request),
            inputs=request.workflow_inputs or {},
            run_root=_workflow_run_root(),
            policy=policy,
            should_cancel=should_cancel,
            on_update=callback,
        )

    current = _read_json(job_dir / "job.json")
    parity_summary = _shadow_parity_summary(shadow_payload, request, result, current)
    state = "cancelled" if result.get("status") == "cancelled" else "completed"
    current.update(
        {
            "state": state,
            "updated_at": _now(),
            "workflow_run_id": result.get("run_id") or "",
            "run_id": result.get("run_id") or "",
            "run_dir": result.get("run_dir") or "",
            "result": _job_result_payload(result),
            "error": "",
        }
    )
    current["progress"] = _progress_payload(
        int(current.get("progress", {}).get("total") or len(result.get("topology") or [])),
        int(current.get("progress", {}).get("total") or len(result.get("topology") or [])),
        "",
    )
    if parity_summary is not None:
        current["parity_summary"] = parity_summary
    _write_json(job_dir / "job.json", current)
    return current


def _progress_callback(job_dir: Path):
    def update(event: dict[str, Any]) -> None:
        job = _read_json(job_dir / "job.json")
        nodes = dict(job.get("nodes") or {})
        event_name = str(event.get("event") or "")
        node_id = str(event.get("node_id") or "")
        total = int(event.get("total") or job.get("progress", {}).get("total") or 0)
        done = int(event.get("done") or 0)
        current_node = str(event.get("current_node") or "")

        if event_name == "run_started":
            job.update(
                {
                    "workflow_run_id": event.get("run_id") or "",
                    "run_id": event.get("run_id") or "",
                    "run_dir": event.get("run_dir") or "",
                    "topology": event.get("topology") or [],
                }
            )
        elif event_name == "node_started" and node_id:
            nodes[node_id] = {
                **dict(nodes.get(node_id) or {}),
                "node_id": node_id,
                "node_type": event.get("node_type") or "",
                "status": "running",
                "updated_at": _now(),
            }
        elif event_name == "node_finished" and node_id:
            nodes[node_id] = {
                **dict(nodes.get(node_id) or {}),
                "node_id": node_id,
                "status": event.get("status") or "",
                "updated_at": _now(),
            }

        job.update(
            {
                "state": "running" if str(job.get("state") or "") not in {"cancel_requested", "cancelled"} else job.get("state"),
                "updated_at": _now(),
                "progress": _progress_payload(total, done, current_node),
                "nodes": nodes,
            }
        )
        _write_json(job_dir / "job.json", job)

    return update


def _progress_payload(total: int, done: int, current_node: str) -> dict[str, Any]:
    percent = round(done / total * 100) if total else 0
    return {
        "total": total,
        "done": min(done, total) if total else done,
        "percent": min(100, max(0, percent)),
        "current_node": current_node,
    }


def _job_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "action": "workflow_result",
        "run_id": result.get("run_id") or "",
        "workflow_id": result.get("workflow_id") or "",
        "mode": result.get("mode") or "",
        "status": result.get("status") or "",
        "run_dir": result.get("run_dir") or "",
        "source_run_id": result.get("source_run_id") or "",
        "side_effect_summary": result.get("side_effect_summary") or {},
        "topology": result.get("topology") or [],
        "nodes": result.get("nodes") or {},
    }


def _shadow_parity_summary(
    shadow: dict[str, Any] | None,
    request: IsoWorkflowRequest,
    result: dict[str, Any],
    workflow_job: dict[str, Any],
) -> dict[str, Any] | None:
    if not shadow:
        return None
    if result.get("status") not in {"completed", "completed_with_blocked"}:
        return {
            "status": "shadow_failed",
            "error": f"workflow status is {result.get('status') or 'unknown'}",
        }
    try:
        from launcher.plugins.iso_tools.workflow.parity import SAFE_WORKFLOW_PATH, compare_plans, write_parity_report
        from launcher.plugins.iso_tools.workflow.projection import plan_from_run

        iso_job_id = str(shadow.get("iso_job_id") or "")
        if not iso_job_id:
            raise ValueError("shadow request missing iso_job_id")
        iso_job = _read_json(_job_dir(iso_job_id) / "job.json")
        legacy_plan = iso_job.get("result")
        if not isinstance(legacy_plan, dict):
            raise ValueError("ISO job does not contain a result plan")
        run_dir = Path(str(result.get("run_dir") or ""))
        workflow_plan = plan_from_run(run_dir)
        report = compare_plans(legacy_plan, workflow_plan)
        timing = {
            "legacy_ms": _elapsed_ms(iso_job.get("created_at"), iso_job.get("updated_at")),
            "workflow_ms": _elapsed_ms(workflow_job.get("created_at"), _now()),
        }
        report_path = write_parity_report(
            report,
            inputs=request.workflow_inputs or {},
            workflow_path=request.workflow_path or SAFE_WORKFLOW_PATH,
            work_dir=run_dir,
            trigger="shadow",
            sample_kind=str(shadow.get("sample_kind") or "real"),
            iso_job_id=iso_job_id,
            workflow_run_id=str(result.get("run_id") or ""),
            timing=timing,
        )
        return {
            "status": "recorded",
            "equal": report.equal,
            "violation_count": len(report.violations),
            "acceptable_diff_count": len(report.acceptable_diffs),
            "report_path": str(report_path),
        }
    except Exception as exc:
        return {
            "status": "shadow_failed",
            "error": str(exc),
        }


def _elapsed_ms(start: Any, end: Any) -> int:
    try:
        started = datetime.fromisoformat(str(start))
        ended = datetime.fromisoformat(str(end))
    except (TypeError, ValueError):
        return 0
    return max(0, int((ended - started).total_seconds() * 1000))


def _fail_job(job_dir: Path, exc: Exception) -> None:
    job_path = job_dir / "job.json"
    job = _read_json(job_path) if job_path.exists() else {}
    job.update(
        {
            "state": "failed",
            "updated_at": _now(),
            "error": str(exc),
            "result": {
                "schema_version": 1,
                "action": "workflow_result",
                "status": "failed",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        }
    )
    _write_json(job_path, job)


if __name__ == "__main__":
    raise SystemExit(main())
