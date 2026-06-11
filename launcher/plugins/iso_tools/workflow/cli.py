from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.workflow.context import json_safe
from launcher.plugins.iso_tools.workflow.errors import GraphValidationError, WorkflowError
from launcher.plugins.iso_tools.workflow.executor import replay_workflow, run_single_node, run_workflow, validate_graph
from launcher.plugins.iso_tools.workflow.policy import GUARDED, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.registry import get_registry
from launcher.plugins.iso_tools.workflow.schema import load_workflow


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-nodes":
            return _print(_node_specs(), args.json)
        if args.command == "list-runs":
            return _print(_list_runs(args.run_root, args.limit), args.json)
        if args.command == "validate":
            graph = load_workflow(Path(args.workflow))
            issues = validate_graph(graph, get_registry())
            payload = {"valid": not any(issue.severity == "error" for issue in issues), "issues": [issue.to_payload() for issue in issues], "edges": [edge.to_payload() for edge in graph.edges]}
            return _print(payload, args.json, exit_code=0 if payload["valid"] else 2)
        if args.command == "run":
            graph = load_workflow(Path(args.workflow))
            result = run_workflow(
                graph,
                inputs=_load_inputs(args.inputs_json, args.set_values),
                run_root=Path(args.run_root) if args.run_root else None,
                policy=_policy_from_args(args, mode="dry_run" if args.dry_run else "run"),
            )
            return _print(_result_payload(result), args.json, exit_code=_exit_for_status(result.get("status")))
        if args.command == "run-node":
            result = run_single_node(
                _run_dir(args.run, args.run_root),
                args.node,
                run_root=Path(args.run_root) if args.run_root else None,
                policy=_policy_from_args(args, mode="run"),
            )
            return _print(_result_payload(result), args.json, exit_code=_exit_for_status(result.get("status")))
        if args.command == "replay":
            result = replay_workflow(
                _run_dir(args.run, args.run_root),
                run_root=Path(args.run_root) if args.run_root else None,
                policy=SideEffectPolicy(mode="replay", include_auto_in_replay=args.include_auto_side_effects),
            )
            return _print(_result_payload(result), args.json, exit_code=_exit_for_status(result.get("status")))
        if args.command == "parity":
            try:
                inputs = _load_inputs(args.inputs_json, [])
            except (OSError, json.JSONDecodeError) as exc:
                return _print({"error": str(exc), "type": type(exc).__name__}, args.json, exit_code=2)
            from launcher.plugins.iso_tools.workflow.parity import SAFE_WORKFLOW_PATH, run_parity, write_parity_report

            workflow_path = Path(args.workflow) if args.workflow else SAFE_WORKFLOW_PATH
            work_dir = Path(args.work_dir) if args.work_dir else Path.cwd() / ".runtime" / "temp" / "workflow_parity"
            report = run_parity(inputs, workflow_path=workflow_path, work_dir=work_dir)
            payload = report.to_payload()
            report_path = write_parity_report(
                report,
                path=Path(args.report_out) if args.report_out else None,
                inputs=inputs,
                workflow_path=workflow_path,
                work_dir=work_dir,
                sample_kind=args.sample_kind,
            )
            payload["report_path"] = str(report_path)
            payload["sample_kind"] = args.sample_kind
            payload["trigger"] = "cli"
            return _print(payload, args.json, exit_code=0 if report.equal else 6)
        if args.command == "parity-history":
            from launcher.plugins.iso_tools.workflow.parity import list_parity_reports

            return _print(list_parity_reports(root=Path(args.root) if args.root else None, limit=args.limit), args.json)
        if args.command == "gate":
            from launcher.plugins.iso_tools.workflow.gate import evaluate_switchover_gate

            payload = evaluate_switchover_gate()
            return _print(payload, args.json, exit_code=0 if payload.get("ready") else 7)
        parser.error("missing command")
        return 2
    except GraphValidationError as exc:
        return _print({"valid": False, "issues": [issue.to_payload() for issue in exc.issues]}, getattr(args, "json", False), exit_code=2)
    except (WorkflowError, OSError, ValueError, KeyError) as exc:
        return _print({"error": str(exc), "type": type(exc).__name__}, getattr(args, "json", False), exit_code=5)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iso-workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    list_nodes = sub.add_parser("list-nodes")
    list_nodes.add_argument("--json", action="store_true")

    list_runs = sub.add_parser("list-runs")
    list_runs.add_argument("--run-root", default="")
    list_runs.add_argument("--limit", type=int, default=20)
    list_runs.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate")
    validate.add_argument("--workflow", required=True)
    validate.add_argument("--json", action="store_true")

    run = sub.add_parser("run")
    run.add_argument("--workflow", required=True)
    run.add_argument("--inputs-json", default="")
    run.add_argument("--set", dest="set_values", action="append", default=[])
    run.add_argument("--run-root", default="")
    run.add_argument("--allow", action="append", default=[])
    run.add_argument("--confirm", action="append", default=[])
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--json", action="store_true")

    run_node = sub.add_parser("run-node")
    run_node.add_argument("--run", required=True)
    run_node.add_argument("--node", required=True)
    run_node.add_argument("--run-root", default="")
    run_node.add_argument("--allow", action="append", default=[])
    run_node.add_argument("--confirm", action="append", default=[])
    run_node.add_argument("--json", action="store_true")

    replay = sub.add_parser("replay")
    replay.add_argument("--run", required=True)
    replay.add_argument("--run-root", default="")
    replay.add_argument("--include-auto-side-effects", action="store_true")
    replay.add_argument("--json", action="store_true")

    parity = sub.add_parser("parity")
    parity.add_argument("--inputs-json", required=True)
    parity.add_argument("--workflow", default="")
    parity.add_argument("--work-dir", default="")
    parity.add_argument("--report-out", default="")
    parity.add_argument("--sample-kind", choices=("real", "fixture", "unknown"), default="fixture")
    parity.add_argument("--json", action="store_true")

    parity_history = sub.add_parser("parity-history")
    parity_history.add_argument("--root", default="")
    parity_history.add_argument("--limit", type=int, default=20)
    parity_history.add_argument("--json", action="store_true")

    gate = sub.add_parser("gate")
    gate.add_argument("--json", action="store_true")

    return parser


def _node_specs() -> dict[str, Any]:
    return {"nodes": [spec.to_payload() for spec in get_registry().list_specs()]}


def _list_runs(run_root: str, limit: int) -> dict[str, Any]:
    root = Path(run_root) if run_root else Path.cwd() / ".runtime" / "runs" / "workflow"
    runs: list[dict[str, Any]] = []
    if root.exists():
        for run_dir in root.iterdir():
            run_log = run_dir / "run_log.json"
            if not run_dir.is_dir() or not run_log.exists():
                continue
            try:
                payload = json.loads(run_log.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            runs.append(
                {
                    "run_id": payload.get("run_id") or run_dir.name,
                    "workflow_id": payload.get("workflow_id"),
                    "mode": payload.get("mode"),
                    "status": payload.get("status"),
                    "started_at": payload.get("started_at"),
                    "ended_at": payload.get("ended_at"),
                    "source_run_id": payload.get("source_run_id"),
                    "run_dir": str(run_dir),
                }
            )
    runs.sort(key=lambda item: str(item.get("started_at") or item.get("run_id") or ""), reverse=True)
    return {"run_root": str(root), "runs": runs[: max(0, limit)]}


def _load_inputs(path: str, set_values: list[str]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    if path:
        inputs.update(json.loads(Path(path).read_text(encoding="utf-8")))
    for item in set_values:
        if "=" not in item:
            raise ValueError(f"--set expects key=value: {item}")
        key, value = item.split("=", 1)
        inputs[key] = value
    return inputs


def _policy_from_args(args: Any, *, mode: str) -> SideEffectPolicy:
    allowed = frozenset(args.allow or [])
    unknown = allowed - GUARDED
    if unknown:
        raise ValueError(f"--allow only accepts guarded kinds {sorted(GUARDED)}; got {sorted(unknown)}")
    return SideEffectPolicy(mode=mode, allowed_guarded=allowed, confirmed_nodes=frozenset(args.confirm or []))


def _run_dir(run: str, run_root: str) -> Path:
    candidate = Path(run)
    if candidate.exists():
        return candidate
    root = Path(run_root) if run_root else Path.cwd() / ".runtime" / "runs" / "workflow"
    return root / run


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    run_id = str(result.get("run_id") or "")
    return {
        "run_id": run_id,
        "workflow_id": result.get("workflow_id"),
        "status": result.get("status"),
        "run_dir": str(result.get("run_dir") or (Path.cwd() / ".runtime" / "runs" / "workflow" / run_id)),
        "side_effect_summary": result.get("side_effect_summary", {}),
    }


def _print(payload: dict[str, Any], as_json: bool, *, exit_code: int = 0) -> int:
    if as_json:
        print(json.dumps(json_safe(payload), ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


def _exit_for_status(status: Any) -> int:
    if status == "failed":
        return 5
    if status == "completed_with_blocked":
        return 4
    return 0


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
