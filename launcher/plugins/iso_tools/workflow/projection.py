from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.workflow.one_click_guard import validate_one_click_plan

MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


def read_artifact(run_dir: Path, node_id: str, port: str) -> tuple[dict[str, Any], Any]:
    run_dir = run_dir.resolve()
    run_log = _read_run_log(run_dir)
    node = _node_payload(run_log, node_id)
    outputs = node.get("outputs") if isinstance(node.get("outputs"), dict) else {}
    ref_meta = outputs.get(port)
    if not isinstance(ref_meta, dict):
        raise ValueError(f"workflow artifact not found: {node_id}.{port}")
    payload = _read_artifact_ref(run_dir, ref_meta)
    return ref_meta, payload


def plan_from_run(run_dir: Path, *, one_click_guard: bool = False) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    run_log = _read_run_log(run_dir)
    rows_node_id, base = _base_plan(run_dir, run_log)
    rows = list(base.get("rows") or [])
    if not rows and rows_node_id:
        try:
            _, rows_payload = read_artifact(run_dir, rows_node_id, "rows")
            rows = list(rows_payload or [])
        except ValueError:
            rows = []

    pilot_node_id, pilot_results, pilot_summary = _fresh_pilot(run_dir, run_log)
    if pilot_results is not None:
        base["pilot_results"] = pilot_results
    if pilot_summary is not None:
        base["pilot_summary"] = pilot_summary

    projected = deepcopy(base)
    projected["schema_version"] = int(projected.get("schema_version") or 1)
    projected["action"] = "workflow_plan_from_run"
    projected["created_at"] = _now()
    projected["rows"] = rows
    projected["summary"] = _summary_from_rows(rows)
    projected.setdefault("issues", [])
    projected.setdefault("steps", [])
    projected["provenance"] = _provenance(run_dir, run_log, rows_node_id, pilot_node_id)
    if one_click_guard:
        errors = validate_one_click_plan(run_log, projected)
        if errors:
            raise ValueError("one-click workflow projection failed sanity guard: " + "; ".join(errors))
    return projected


def _read_run_log(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run_log.json"
    if not path.exists():
        raise FileNotFoundError(f"workflow run log not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _node_payload(run_log: dict[str, Any], node_id: str) -> dict[str, Any]:
    nodes = run_log.get("nodes") if isinstance(run_log.get("nodes"), dict) else {}
    payload = nodes.get(node_id)
    if not isinstance(payload, dict):
        raise ValueError(f"workflow node not found in run log: {node_id}")
    return payload


def _read_artifact_ref(run_dir: Path, ref_meta: dict[str, Any]) -> Any:
    if "inline" in ref_meta:
        return ref_meta["inline"]
    ref = str(ref_meta.get("artifact_ref") or "")
    if not ref:
        raise ValueError("workflow artifact ref missing artifact_ref")
    path = (run_dir / ref).resolve()
    _ensure_inside(run_dir, path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"workflow artifact file not found: {ref}")
    size = path.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"workflow artifact exceeds 64MB: {ref}")
    declared = ref_meta.get("bytes")
    if declared is not None and int(declared) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"workflow artifact exceeds 64MB: {ref}")
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_inside(root: Path, path: Path) -> None:
    try:
        common = os.path.commonpath([str(root), str(path)])
    except ValueError as exc:
        raise ValueError("workflow artifact path escapes run directory") from exc
    if common != str(root):
        raise ValueError("workflow artifact path escapes run directory")


def _base_plan(run_dir: Path, run_log: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    batch_node = _first_success_node(run_log, "iso.batch_detect_serials")
    if batch_node:
        try:
            _, result = read_artifact(run_dir, batch_node, "result")
            if isinstance(result, dict) and result:
                return batch_node, result
        except ValueError:
            pass

    plan_node = _first_success_node(run_log, "iso.build_plan")
    if plan_node:
        for port in ("plan", "result"):
            try:
                _, result = read_artifact(run_dir, plan_node, port)
                if isinstance(result, dict) and result:
                    return plan_node, result
            except ValueError:
                continue
    raise ValueError("此 run 沒有可投影的 plan 輸出。")


def _fresh_pilot(run_dir: Path, run_log: dict[str, Any]) -> tuple[str, list[dict[str, Any]] | None, dict[str, Any] | None]:
    pilot_node = _first_success_node(run_log, "iso.pilot_report")
    if not pilot_node:
        return "", None, None
    pilot_results = None
    pilot_summary = None
    try:
        _, payload = read_artifact(run_dir, pilot_node, "pilot_results")
        if isinstance(payload, list):
            pilot_results = payload
    except ValueError:
        pass
    try:
        _, payload = read_artifact(run_dir, pilot_node, "pilot_summary")
        if isinstance(payload, dict):
            pilot_summary = payload
    except ValueError:
        pass
    return pilot_node, pilot_results, pilot_summary


def _first_success_node(run_log: dict[str, Any], node_type: str) -> str:
    nodes = run_log.get("nodes") if isinstance(run_log.get("nodes"), dict) else {}
    for instance in _workflow_nodes(run_log):
        node_id = str(instance.get("node_id") or "")
        if instance.get("node_type") == node_type and nodes.get(node_id, {}).get("status") == "success":
            return node_id
    return ""


def _workflow_nodes(run_log: dict[str, Any]) -> list[dict[str, Any]]:
    workflow = run_log.get("workflow") if isinstance(run_log.get("workflow"), dict) else {}
    nodes = workflow.get("nodes") if isinstance(workflow.get("nodes"), list) else []
    return [node for node in nodes if isinstance(node, dict)]


def _provenance(run_dir: Path, run_log: dict[str, Any], rows_node_id: str, pilot_node_id: str) -> dict[str, Any]:
    iso_run_log = {}
    if rows_node_id:
        try:
            _, payload = read_artifact(run_dir, rows_node_id, "iso_run_log")
            if isinstance(payload, dict):
                iso_run_log = payload
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            iso_run_log = {}
    return {
        "workflow_run_id": run_log.get("run_id") or "",
        "workflow_id": run_log.get("workflow_id") or "",
        "graph_hash": run_log.get("graph_hash") or "",
        "run_mode": run_log.get("mode") or "",
        "run_status": run_log.get("status") or "",
        "projected_at": _now(),
        "rows_node": rows_node_id,
        "pilot_node": pilot_node_id,
        "iso_run_log": {
            "run_id": iso_run_log.get("run_id") or "",
            "run_dir": iso_run_log.get("run_dir") or "",
        },
    }


def _summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    # Kept in sync with the app-layer ISO summary helper without importing app code.
    total = len(rows)
    ready = sum(1 for row in rows if row.get("status") == "ready")
    warn = sum(1 for row in rows if row.get("status") == "warn")
    blocked = sum(1 for row in rows if row.get("status") == "blocked")
    selected = sum(1 for row in rows if row.get("selected"))
    return {"total": total, "ready": ready, "warn": warn, "blocked": blocked, "selected": selected}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
