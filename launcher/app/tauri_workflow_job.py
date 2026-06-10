from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    _normalize_request,
    _now,
    _read_json,
    _workflow_graph_from_request,
    _workflow_policy_from_request,
    _workflow_run_dir_required,
    _workflow_run_root,
    _write_json,
)
from launcher.plugins.iso_tools.workflow.executor import replay_workflow, run_workflow


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
    request = IsoWorkflowRequest(**_normalize_request(request_payload))
    job = _read_json(job_dir / "job.json")
    job.update({"state": "running", "updated_at": _now(), "error": ""})
    _write_json(job_dir / "job.json", job)

    mode = request.workflow_mode or "run"
    policy = _workflow_policy_from_request(request)
    callback = _progress_callback(job_dir)
    should_cancel = lambda: (job_dir / "cancel.json").exists()

    if mode == "replay":
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
        "side_effect_summary": result.get("side_effect_summary") or {},
        "topology": result.get("topology") or [],
        "nodes": result.get("nodes") or {},
    }


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
