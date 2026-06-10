from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from launcher.app import tauri_iso_workflow
from launcher.app.tauri_iso_worker import run_job
from launcher.core.paths import runtime_root
from launcher.plugins.iso_tools.workflow.context import json_safe
from launcher.plugins.iso_tools.workflow import nodes as _registered_nodes  # noqa: F401 - registers node classes
from launcher.plugins.iso_tools.workflow.projection import plan_from_run
from launcher.plugins.iso_tools.workflow.schema import load_workflow

SAFE_WORKFLOW_PATH = Path("launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json")


@dataclass
class ParityReport:
    equal: bool
    acceptable_diffs: list[dict[str, Any]] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    legacy_digest: str = ""
    workflow_digest: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "action": "workflow_parity",
            "equal": self.equal,
            "legacy_digest": self.legacy_digest,
            "workflow_digest": self.workflow_digest,
            "acceptable_diffs": self.acceptable_diffs,
            "violations": self.violations,
        }


def normalize_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized, _diffs = _normalize_with_diffs(payload, side="")
    return normalized


def compare_plans(legacy: dict[str, Any], workflow_projected: dict[str, Any]) -> ParityReport:
    legacy_norm, legacy_diffs = _normalize_with_diffs(legacy, side="legacy")
    workflow_norm, workflow_diffs = _normalize_with_diffs(workflow_projected, side="workflow")
    violations = _compare_normalized(legacy_norm, workflow_norm)
    return ParityReport(
        equal=not violations,
        acceptable_diffs=[*legacy_diffs, *workflow_diffs],
        violations=violations,
        legacy_digest=_digest(legacy_norm),
        workflow_digest=_digest(workflow_norm),
    )


def run_parity(inputs: dict[str, Any], *, workflow_path: Path = SAFE_WORKFLOW_PATH, work_dir: Path) -> ParityReport:
    work_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = workflow_path if workflow_path.is_absolute() else Path.cwd() / workflow_path
    legacy_root = work_dir / "legacy"
    workflow_root = work_dir / "workflow"
    env = {
        "DESKTOP_SUPPORT_JOB_ROOT": str(work_dir / "iso_jobs"),
        "DESKTOP_SUPPORT_ISO_RUN_ROOT": str(work_dir / "iso_runs"),
        "DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT": str(workflow_root / "runs"),
    }
    with _patched_environ(env), _patched_attr(tauri_iso_workflow, "_spawn_iso_worker", lambda job_dir: run_job(Path(job_dir))):
        legacy_plan = _run_legacy_batch(inputs, legacy_root)
        workflow = load_workflow(workflow_path)
        from launcher.plugins.iso_tools.workflow.executor import run_workflow

        workflow_result = run_workflow(workflow, inputs=inputs, run_root=workflow_root / "runs")
        workflow_plan = plan_from_run(Path(str(workflow_result["run_dir"])))
    return compare_plans(legacy_plan, workflow_plan)


def parity_report_root() -> Path:
    return runtime_root() / ".runtime" / "runs" / "parity"


def default_parity_report_path(now: datetime | None = None) -> Path:
    now = now or datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    return parity_report_root() / f"{stamp}_{uuid.uuid4().hex[:6]}" / "report.json"


def write_parity_report(
    report: ParityReport,
    *,
    path: Path | None = None,
    inputs: dict[str, Any] | None = None,
    workflow_path: Path | None = None,
    work_dir: Path | None = None,
) -> Path:
    target = path or default_parity_report_path()
    payload = report.to_payload()
    payload.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "inputs_digest": _digest(json_safe(inputs or {})),
            "workflow_path": str(workflow_path or SAFE_WORKFLOW_PATH),
            "work_dir": str(work_dir or ""),
        }
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(json_safe(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def list_parity_reports(*, root: Path | None = None, limit: int = 20) -> dict[str, Any]:
    report_root = root or parity_report_root()
    reports: list[dict[str, Any]] = []
    if report_root.exists():
        for path in report_root.glob("*/report.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            reports.append(
                {
                    "created_at": str(payload.get("created_at") or path.parent.name),
                    "equal": bool(payload.get("equal")),
                    "violation_count": len(payload.get("violations") or []),
                    "acceptable_diff_count": len(payload.get("acceptable_diffs") or []),
                    "inputs_digest": str(payload.get("inputs_digest") or ""),
                    "legacy_digest": str(payload.get("legacy_digest") or ""),
                    "workflow_digest": str(payload.get("workflow_digest") or ""),
                    "report_path": str(path),
                }
            )
    reports.sort(key=lambda item: (item["created_at"], item["report_path"]), reverse=True)
    return {
        "schema_version": 1,
        "action": "workflow_parity_history",
        "report_root": str(report_root),
        "report_count": len(reports),
        "reports": reports[: max(0, limit)],
    }


def _run_legacy_batch(inputs: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    job_id = f"legacy-parity-{uuid.uuid4().hex[:10]}"
    run_id = f"legacy-parity-run-{uuid.uuid4().hex[:10]}"
    job_dir = work_dir / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    request_payload = {
        **inputs,
        "action": "start_batch_detect",
        "job_id": job_id,
        "run_id": run_id,
    }
    request = tauri_iso_workflow.IsoWorkflowRequest(**tauri_iso_workflow._normalize_request(request_payload))
    tauri_iso_workflow._write_json(job_dir / "job.json", tauri_iso_workflow._initial_job_payload(job_id, "queued"))
    tauri_iso_workflow._write_json(job_dir / "request.json", tauri_iso_workflow._request_payload(request))
    job = run_job(job_dir)
    result = job.get("result")
    if not isinstance(result, dict) or job.get("state") != "completed":
        raise RuntimeError(f"legacy batch did not complete: {job.get('state')} {job.get('error')}")
    return result


def _normalize_with_diffs(payload: dict[str, Any], *, side: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    diffs: list[dict[str, Any]] = []
    normalized = {
        "source": _normalize_source(payload.get("source"), diffs, side),
        "summary": dict(payload.get("summary") or {}),
        "rows": _normalize_rows(payload.get("rows")),
        "issues": _normalize_issues(payload.get("issues")),
        "pilot_results": _normalize_pilot(payload.get("pilot_results")),
    }
    _record_removed_top_level(payload, diffs, side)
    return normalized, diffs


def _normalize_source(value: Any, diffs: list[dict[str, Any]], side: str) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    normalized: dict[str, Any] = {}
    ignored = {"combine_pdf", "iso_candidates", "kind", "sheet_options", "profile"}
    path_keys = {"work_folder", "combine_pdf", "page_folder", "iso_list"}
    for key, item in source.items():
        if key in ignored:
            _record_diff(diffs, side, f"source.{key}", "environment field ignored")
            continue
        if key in path_keys:
            normalized[key] = _basename(item)
            if str(item or "") != str(normalized[key] or ""):
                _record_diff(diffs, side, f"source.{key}", "absolute path prefix ignored")
            continue
        normalized[key] = item
    return normalized


def _normalize_rows(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "page": row.get("page"),
                "source_name": row.get("source_name") or _basename(row.get("source_path")),
                "source_path": _basename(row.get("source_path")),
                "serial": row.get("serial") or "",
                "line_no": row.get("line_no") or "",
                "new_name": row.get("new_name") or "",
                "target_path": _basename(row.get("target_path")),
                "status": row.get("status") or "",
                "selected": bool(row.get("selected")),
                "confidence": _round_confidence(row.get("confidence")),
                "note_empty": not bool(str(row.get("note") or "").strip()),
            }
        )
    return sorted(normalized, key=lambda item: (int(item.get("page") or 0), str(item.get("source_name") or "")))


def _normalize_issues(value: Any) -> list[str]:
    issues = value if isinstance(value, list) else []
    codes = []
    for issue in issues:
        if isinstance(issue, dict):
            codes.append(str(issue.get("code") or ""))
    return sorted(code for code in codes if code and not code.startswith("PDF"))


def _normalize_pilot(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        normalized.append(
            {
                "id": item_id,
                "status": "<ignored>" if item_id == "P15" else str(item.get("status") or ""),
                "blocks_apply": bool(item.get("blocks_apply")),
            }
        )
    return sorted(normalized, key=lambda item: item["id"])


def _record_removed_top_level(payload: dict[str, Any], diffs: list[dict[str, Any]], side: str) -> None:
    ignored = {
        "action",
        "created_at",
        "run_log",
        "job",
        "steps",
        "export_path",
        "included_files",
        "provenance",
        "source_run_id",
        "replay_dry_run",
        "message",
        "pilot_summary",
    }
    for key in sorted(ignored & set(payload)):
        _record_diff(diffs, side, key, "metadata ignored")
    for row in payload.get("rows") or []:
        if isinstance(row, dict) and row.get("id"):
            _record_diff(diffs, side, "rows.id", "row id ignored")
            break


def _compare_normalized(legacy: dict[str, Any], workflow: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    _compare_section(violations, "source", legacy.get("source"), workflow.get("source"))
    _compare_section(violations, "summary", legacy.get("summary"), workflow.get("summary"))
    _compare_rows(violations, legacy.get("rows") or [], workflow.get("rows") or [])
    _compare_section(violations, "issues.codes", legacy.get("issues"), workflow.get("issues"))
    _compare_pilot(violations, legacy.get("pilot_results") or [], workflow.get("pilot_results") or [])
    _compare_blocked_rows(violations, legacy.get("rows") or [], workflow.get("rows") or [])
    return violations


def _compare_section(violations: list[dict[str, Any]], field: str, legacy: Any, workflow: Any) -> None:
    if legacy != workflow:
        violations.append({"field": field, "legacy": legacy, "workflow": workflow})


def _compare_rows(violations: list[dict[str, Any]], legacy_rows: list[dict[str, Any]], workflow_rows: list[dict[str, Any]]) -> None:
    if len(legacy_rows) != len(workflow_rows):
        violations.append({"field": "rows.length", "legacy": len(legacy_rows), "workflow": len(workflow_rows)})
    for legacy, workflow in zip(legacy_rows, workflow_rows):
        page = legacy.get("page")
        if page != workflow.get("page"):
            violations.append({"field": "rows.page", "row_page": page, "legacy": page, "workflow": workflow.get("page")})
            continue
        for key in (
            "source_name",
            "source_path",
            "serial",
            "line_no",
            "new_name",
            "target_path",
            "status",
            "selected",
            "confidence",
            "note_empty",
        ):
            if legacy.get(key) != workflow.get(key):
                violations.append({"field": f"rows.{key}", "row_page": page, "legacy": legacy.get(key), "workflow": workflow.get(key)})


def _compare_pilot(violations: list[dict[str, Any]], legacy_items: list[dict[str, Any]], workflow_items: list[dict[str, Any]]) -> None:
    legacy_by_id = {item["id"]: item for item in legacy_items}
    workflow_by_id = {item["id"]: item for item in workflow_items}
    if "P15" not in legacy_by_id or "P15" not in workflow_by_id:
        violations.append({"field": "pilot_results.P15", "legacy": "P15" in legacy_by_id, "workflow": "P15" in workflow_by_id})
    for item_id in sorted(set(legacy_by_id) | set(workflow_by_id)):
        if item_id == "P15":
            continue
        legacy = legacy_by_id.get(item_id)
        workflow = workflow_by_id.get(item_id)
        if legacy != workflow:
            violations.append({"field": "pilot_results", "pilot_id": item_id, "legacy": legacy, "workflow": workflow})


def _compare_blocked_rows(violations: list[dict[str, Any]], legacy_rows: list[dict[str, Any]], workflow_rows: list[dict[str, Any]]) -> None:
    legacy_blocked = sorted(row.get("page") for row in legacy_rows if row.get("status") == "blocked")
    workflow_blocked = sorted(row.get("page") for row in workflow_rows if row.get("status") == "blocked")
    if legacy_blocked != workflow_blocked:
        violations.append({"field": "rows.blocked_pages", "legacy": legacy_blocked, "workflow": workflow_blocked})


def _digest(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _round_confidence(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def _basename(value: Any) -> str:
    text = str(value or "")
    return Path(text.replace("\\", "/")).name if text else ""


def _record_diff(diffs: list[dict[str, Any]], side: str, field: str, reason: str) -> None:
    diffs.append({"side": side, "field": field, "reason": reason})


@contextlib.contextmanager
def _patched_environ(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def _patched_attr(target: Any, name: str, value: Any) -> Iterator[None]:
    previous = getattr(target, name)
    setattr(target, name, value)
    try:
        yield
    finally:
        setattr(target, name, previous)
