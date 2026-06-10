from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.core.paths import PROJECT_ROOT_ENV, STATE_PATH_ENV, runtime_root
from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.debug_bundle import export_iso_debug_bundle
from launcher.plugins.iso_tools.iso_naming import (
    IsoRecord,
    build_record_lookup,
    format_iso_name,
    guess_iso_columns,
    list_iso_sheets,
    natural_pdf_key,
    parse_iso_filename,
    read_iso_table,
    records_from_table,
    split_pdf_to_pages,
)
from launcher.plugins.iso_tools.profile import (
    IsoNamingProfile,
    iso_naming_profile_history,
    load_iso_naming_profile,
    load_iso_naming_profile_draft,
    publish_iso_naming_profile,
    revert_iso_naming_profile,
    save_iso_naming_profile,
    save_iso_naming_profile_draft,
)
from launcher.plugins.iso_tools.pilot import build_pilot_report
from launcher.plugins.iso_tools.roi_calibration import confidence_distribution
from launcher.plugins.iso_tools.run_log import (
    ensure_iso_run,
    finish_iso_run_failure,
    finish_iso_run_success,
    iso_run_root,
    list_iso_run_logs,
    mark_iso_run_started,
    public_run_ref,
    read_iso_run_log,
    start_iso_run,
)
from launcher.plugins.iso_tools.serial_correction import correct_result_with_iso_lookup
from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialVisionRegion, SerialVisionResult
from launcher.plugins.rename_tools.rename_actions import RenameOperation, _apply_operations, _validate_file_name, _validate_operations

SERIAL_AUTO_FILL_CONFIDENCE = 0.70
DEFAULT_PATTERN = "{serial}--{line}.pdf"


@dataclass(frozen=True)
class IsoWorkflowRequest:
    action: str
    profile_folder: Path | None = None
    work_folder: Path | None = None
    combine_pdf: Path | None = None
    page_folder: Path | None = None
    iso_list: Path | None = None
    sheet_name: str | None = None
    serial_col: int | None = None
    line_col: int | None = None
    pattern: str | None = None
    serial_region: dict[str, Any] | None = None
    drawing_region: dict[str, Any] | None = None
    confidence_threshold: float | None = None
    detect_serials: bool = False
    export_path: Path | None = None
    job_id: str | None = None
    run_id: str | None = None
    workflow_path: Path | None = None
    workflow: dict[str, Any] | None = None
    workflow_inputs: dict[str, Any] | None = None
    workflow_allow: tuple[str, ...] = ()
    workflow_confirm: tuple[str, ...] = ()
    workflow_mode: str | None = None
    workflow_job_id: str | None = None
    workflow_run_id: str | None = None
    workflow_node_id: str | None = None
    workflow_port: str | None = None
    rows: tuple[dict[str, Any], ...] = ()


def main() -> int:
    _configure_stdio()
    run_context = None
    request: IsoWorkflowRequest | None = None
    try:
        request = IsoWorkflowRequest(**_normalize_request(json.loads(_read_stdin_json() or "{}")))
        if _should_write_run_log(request):
            if request.run_id:
                run_context = ensure_iso_run(_request_payload(request), action=request.action, run_id=request.run_id)
            else:
                run_context = start_iso_run(_request_payload(request), action=request.action)
            request = replace(request, run_id=run_context.run_id)
        payload = _dispatch_request(request)
        if run_context is not None:
            if request.action == "start_batch_detect":
                mark_iso_run_started(run_context, payload)
            else:
                finish_iso_run_success(run_context, payload)
            payload = {**payload, "run_log": public_run_ref(run_context)}
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        if run_context is not None:
            finish_iso_run_failure(run_context, exc, action=request.action if request is not None else None)
        print(str(exc), file=sys.stderr, flush=True)
        return 1


def _dispatch_request(request: IsoWorkflowRequest) -> dict[str, Any]:
    if request.action == "discover_sources":
        return discover_sources(request)
    if request.action == "split_pdf":
        return split_iso_pdf(request)
    if request.action == "load_iso_table":
        return load_iso_table(request)
    if request.action == "plan":
        return build_iso_plan(request)
    if request.action == "build_rename_plan":
        return build_rename_plan(request)
    if request.action == "export_plan_csv":
        return export_plan_csv(request)
    if request.action == "export_debug_bundle":
        return export_debug_bundle(request)
    if request.action == "pilot_report":
        return pilot_report(request)
    if request.action == "roi_distribution":
        return roi_distribution(request)
    if request.action == "list_run_logs":
        return list_run_logs_action(request)
    if request.action == "read_run_log":
        return read_run_log_action(request)
    if request.action == "replay_run_log":
        return replay_run_log_action(request)
    if request.action == "start_batch_detect":
        return start_batch_detect(request)
    if request.action == "job_status":
        return iso_job_status(request)
    if request.action == "cancel_job":
        return cancel_iso_job(request)
    if request.action == "apply":
        return apply_iso_plan(request)
    if request.action == "load_profile":
        return load_iso_profile(request)
    if request.action == "save_profile":
        return save_iso_profile(request)
    if request.action == "save_draft_profile":
        return save_iso_draft_profile(request)
    if request.action == "publish_profile":
        return publish_iso_profile_action(request)
    if request.action == "revert_profile":
        return revert_iso_profile_action(request)
    if request.action == "workflow_list_nodes":
        return workflow_list_nodes_action(request)
    if request.action == "workflow_load":
        return workflow_load_action(request)
    if request.action == "workflow_validate":
        return workflow_validate_action(request)
    if request.action == "workflow_run":
        return workflow_run_action(request)
    if request.action == "workflow_run_status":
        return workflow_run_status_action(request)
    if request.action == "workflow_cancel":
        return workflow_cancel_action(request)
    if request.action == "workflow_list_runs":
        return workflow_list_runs_action(request)
    if request.action == "workflow_read_run_log":
        return workflow_read_run_log_action(request)
    if request.action == "workflow_plan_from_run":
        return workflow_plan_from_run_action(request)
    if request.action == "workflow_read_artifact":
        return workflow_read_artifact_action(request)
    if request.action == "workflow_parity_history":
        return workflow_parity_history_action(request)
    raise ValueError(f"unknown action: {request.action}")


def build_iso_plan(request: IsoWorkflowRequest) -> dict[str, Any]:
    pdfs, source_kind, page_folder, pdf_events = _resolve_pdfs(request)
    request, loaded_profile = _with_profile_defaults(request, resolved_page_folder=page_folder)
    pattern = _plan_pattern(request)
    records, iso_meta = _resolve_iso_records(request)
    lookup = build_record_lookup(records)
    rows, row_events = _build_plan_rows(
        pdfs,
        lookup,
        pattern=pattern,
        detect_serials=request.detect_serials,
        confidence_threshold=request.confidence_threshold if request.confidence_threshold is not None else SERIAL_AUTO_FILL_CONFIDENCE,
    )
    issues = [*pdf_events, *iso_meta["issues"], *row_events]
    summary = _summary(rows)
    payload = {
        "schema_version": 1,
        "action": "plan",
        "created_at": _now(),
        "source": {
            "kind": source_kind,
            "work_folder": str(request.work_folder or ""),
            "combine_pdf": str(request.combine_pdf or ""),
            "page_folder": str(page_folder or ""),
            "pdf_count": len(pdfs),
            "iso_list": str(iso_meta["iso_list"]),
            "iso_candidates": iso_meta["iso_candidates"],
            "sheet_name": iso_meta["sheet_name"],
            "sheet_options": iso_meta["sheet_options"],
            "headers": iso_meta["headers"],
            "serial_col": iso_meta["serial_col"],
            "line_col": iso_meta["line_col"],
            "record_count": len(records),
            "pattern": pattern,
            "detect_serials": request.detect_serials,
            "confidence_threshold": request.confidence_threshold if request.confidence_threshold is not None else SERIAL_AUTO_FILL_CONFIDENCE,
            "serial_region": request.serial_region,
            "drawing_region": request.drawing_region,
            "profile": loaded_profile,
        },
        "summary": summary,
        "steps": _steps(source_kind, len(pdfs), len(records), request.detect_serials, summary),
        "rows": rows,
        "issues": issues,
    }
    return _with_pilot_results(payload, request)


def discover_sources(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder, profile, candidates = _load_profile_for_request(request)
    return _profile_response(
        action="discover_sources",
        folder=folder,
        profile=profile or IsoNamingProfile(),
        exists=profile is not None,
        candidates=candidates,
        message=f"已探索來源：{folder}" if folder is not None else "尚未選擇可探索的來源。",
    )


def split_iso_pdf(request: IsoWorkflowRequest) -> dict[str, Any]:
    pdfs, source_kind, page_folder, events = _resolve_pdfs(request)
    return {
        "schema_version": 1,
        "action": "split_pdf",
        "created_at": _now(),
        "source": {
            "kind": source_kind,
            "work_folder": str(request.work_folder or ""),
            "combine_pdf": str(request.combine_pdf or ""),
            "page_folder": str(page_folder or ""),
            "pdf_count": len(pdfs),
        },
        "pages": [
            {
                "page": index,
                "source_path": str(path),
                "source_name": path.name,
            }
            for index, path in enumerate(pdfs, start=1)
        ],
        "issues": events,
    }


def load_iso_table(request: IsoWorkflowRequest) -> dict[str, Any]:
    request, loaded_profile = _with_profile_defaults(request)
    records, iso_meta = _resolve_iso_records(request)
    return {
        "schema_version": 1,
        "action": "load_iso_table",
        "created_at": _now(),
        "source": {
            "work_folder": str(request.work_folder or ""),
            "iso_list": str(iso_meta["iso_list"]),
            "iso_candidates": iso_meta["iso_candidates"],
            "sheet_name": iso_meta["sheet_name"],
            "sheet_options": iso_meta["sheet_options"],
            "headers": iso_meta["headers"],
            "serial_col": iso_meta["serial_col"],
            "line_col": iso_meta["line_col"],
            "record_count": len(records),
            "profile": loaded_profile,
        },
        "sample_records": [
            {"serial": record.serial, "line_no": record.line_no}
            for record in records[:8]
        ],
        "issues": iso_meta["issues"],
    }


def build_rename_plan(request: IsoWorkflowRequest) -> dict[str, Any]:
    payload = build_iso_plan(request)
    payload["action"] = "build_rename_plan"
    return payload


def pilot_report(request: IsoWorkflowRequest) -> dict[str, Any]:
    if request.rows:
        payload = {
            "schema_version": 1,
            "action": "pilot_report_source",
            "created_at": _now(),
            "source": {
                "work_folder": str(request.work_folder or ""),
                "combine_pdf": str(request.combine_pdf or ""),
                "page_folder": str(request.page_folder or ""),
                "iso_list": str(request.iso_list or ""),
                "sheet_name": request.sheet_name or "",
                "serial_col": request.serial_col,
                "line_col": request.line_col,
                "pattern": _plan_pattern(request),
                "detect_serials": request.detect_serials,
                "confidence_threshold": request.confidence_threshold if request.confidence_threshold is not None else SERIAL_AUTO_FILL_CONFIDENCE,
                "serial_region": request.serial_region,
                "drawing_region": request.drawing_region,
                "pdf_count": len(request.rows),
                "record_count": 0,
            },
            "summary": _summary(list(request.rows)),
            "rows": list(request.rows),
            "issues": [],
        }
        return build_pilot_report(request=_request_payload(request), plan=payload)
    plan = build_iso_plan(request)
    report = build_pilot_report(request=_request_payload(request), plan=plan)
    return {**report, "source": plan.get("source", {}), "rows": plan.get("rows", [])}


def roi_distribution(request: IsoWorkflowRequest) -> dict[str, Any]:
    rows = [dict(row) for row in request.rows]
    if not rows:
        plan = build_iso_plan(request)
        rows = [dict(row) for row in plan.get("rows", []) if isinstance(row, dict)]
    threshold = request.confidence_threshold if request.confidence_threshold is not None else SERIAL_AUTO_FILL_CONFIDENCE
    distribution = confidence_distribution(rows, threshold=threshold)
    return {
        "schema_version": 1,
        "action": "roi_distribution",
        "created_at": _now(),
        **distribution,
    }


def list_run_logs_action(_request: IsoWorkflowRequest) -> dict[str, Any]:
    runs = list_iso_run_logs(limit=30)
    return {
        "schema_version": 1,
        "action": "list_run_logs",
        "created_at": _now(),
        "runs": runs,
    }


def read_run_log_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    if not request.run_id:
        raise ValueError("缺少 run_id，無法讀取 ISO run log。")
    return read_iso_run_log(request.run_id)


def replay_run_log_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    if not request.run_id:
        raise ValueError("缺少 run_id，無法 replay ISO run log。")
    payload = read_iso_run_log(request.run_id)
    run = payload["run"]
    replay = run.get("replay") if isinstance(run.get("replay"), dict) else {}
    replay_request = replay.get("request") if isinstance(replay.get("request"), dict) else {}
    if not replay_request:
        raise ValueError("此 ISO run log 沒有可 replay 的 request。")
    dry_run_request = dict(replay_request)
    dry_run_request["action"] = "plan"
    dry_run_request["run_id"] = ""
    dry_run_request["rows"] = []
    dry_run_request["export_path"] = ""
    plan = build_iso_plan(IsoWorkflowRequest(**_normalize_request(dry_run_request)))
    return {
        **plan,
        "action": "replay_run_log",
        "source_run_id": run.get("run_id") or request.run_id,
        "replay_dry_run": True,
        "message": f"已 dry-run replay：{run.get('run_id') or request.run_id}",
    }


def load_iso_profile(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder, profile, candidates = _load_profile_for_request(request)
    if folder is None:
        return _profile_response(
            action="load_profile",
            folder=None,
            profile=IsoNamingProfile(),
            exists=False,
            candidates=candidates,
            message="尚未選擇可對應 profile 的工作資料夾。",
        )
    return _profile_response(
        action="load_profile",
        folder=folder,
        profile=profile or IsoNamingProfile(),
        exists=profile is not None,
        candidates=candidates,
        message=f"已載入資料夾設定：{folder}" if profile is not None else f"此資料夾尚未建立 ISO profile：{folder}",
    )


def save_iso_profile(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder = _profile_folder(request)
    if folder is None:
        raise ValueError("請先選擇工作資料夾，才能儲存 ISO profile。")
    store = _state_store()
    existing = load_iso_naming_profile(store, folder)
    profile = _profile_from_request(request, existing or IsoNamingProfile())
    save_iso_naming_profile(store, folder, profile)
    return _profile_response(
        action="save_profile",
        folder=folder,
        profile=profile,
        exists=True,
        candidates=_profile_folder_candidates(request),
        message=f"已儲存 ISO profile：{folder}",
    )


def save_iso_draft_profile(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder = _profile_folder(request)
    if folder is None:
        raise ValueError("請先選擇工作資料夾，才能儲存 ISO profile 草稿。")
    store = _state_store()
    existing = load_iso_naming_profile_draft(store, folder) or load_iso_naming_profile(store, folder)
    profile = _profile_from_request(request, existing or IsoNamingProfile())
    save_iso_naming_profile_draft(store, folder, profile)
    return _profile_response(
        action="save_draft_profile",
        folder=folder,
        profile=profile,
        exists=True,
        candidates=_profile_folder_candidates(request),
        message=f"已儲存 ISO profile 草稿：{folder}",
        profile_scope="draft",
    )


def publish_iso_profile_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder = _profile_folder(request)
    if folder is None:
        raise ValueError("請先選擇工作資料夾，才能發布 ISO profile。")
    store = _state_store()
    draft = load_iso_naming_profile_draft(store, folder)
    existing = load_iso_naming_profile(store, folder)
    profile = _profile_from_request(request, draft or existing or IsoNamingProfile()) if _request_has_profile_values(request) else None
    published = publish_iso_naming_profile(store, folder, profile)
    return _profile_response(
        action="publish_profile",
        folder=folder,
        profile=published,
        exists=True,
        candidates=_profile_folder_candidates(request),
        message=f"已發布 ISO profile：{folder}",
        profile_scope="published",
    )


def revert_iso_profile_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    folder = _profile_folder(request)
    if folder is None:
        raise ValueError("請先選擇工作資料夾，才能回復 ISO profile。")
    store = _state_store()
    profile = revert_iso_naming_profile(store, folder)
    return _profile_response(
        action="revert_profile",
        folder=folder,
        profile=profile,
        exists=True,
        candidates=_profile_folder_candidates(request),
        message=f"已回復上一版 ISO profile：{folder}",
        profile_scope="published",
    )


def workflow_list_nodes_action(_request: IsoWorkflowRequest) -> dict[str, Any]:
    from launcher.plugins.iso_tools.workflow.registry import get_registry

    specs = [spec.to_payload() for spec in get_registry().list_specs()]
    return {
        "schema_version": 1,
        "action": "workflow_list_nodes",
        "created_at": _now(),
        "nodes": specs,
        "node_count": len(specs),
    }


def workflow_load_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    graph = _workflow_graph_from_request(request)
    validation = _workflow_validation_payload(graph)
    return {
        "schema_version": 1,
        "action": "workflow_load",
        "created_at": _now(),
        "workflow_path": str(request.workflow_path or ""),
        "graph": graph.to_payload(),
        **validation,
    }


def workflow_validate_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    graph = _workflow_graph_from_request(request)
    return {
        "schema_version": 1,
        "action": "workflow_validate",
        "created_at": _now(),
        "workflow_path": str(request.workflow_path or ""),
        "workflow_id": graph.workflow_id,
        **_workflow_validation_payload(graph),
    }


def workflow_run_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    _workflow_policy_from_request(request)
    if (request.workflow_mode or "run") != "replay":
        _workflow_graph_from_request(request)
    else:
        _workflow_run_dir_required(request)

    job_id = request.workflow_job_id or uuid.uuid4().hex
    job_dir = _workflow_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    job = _initial_workflow_job_payload(job_id, "queued")
    _write_json(job_dir / "job.json", job)
    _write_json(job_dir / "request.json", _workflow_request_payload(request, job_id=job_id))
    _spawn_workflow_job(job_dir)
    return _read_json(job_dir / "job.json")


def workflow_run_status_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    return _read_json(_workflow_job_dir_required(request) / "job.json")


def workflow_cancel_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    job_dir = _workflow_job_dir_required(request)
    _write_json(job_dir / "cancel.json", {"cancelled_at": _now()})
    job = _read_json(job_dir / "job.json")
    if job.get("state") in {"queued", "running"}:
        job["state"] = "cancel_requested"
        job["updated_at"] = _now()
        _write_json(job_dir / "job.json", job)
    return job


def workflow_list_runs_action(_request: IsoWorkflowRequest) -> dict[str, Any]:
    root = _workflow_run_root()
    runs: list[dict[str, Any]] = []
    if root.exists():
        for run_dir in root.iterdir():
            run_log = run_dir / "run_log.json"
            if not run_dir.is_dir() or not run_log.exists():
                continue
            try:
                payload = _read_json(run_log)
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
                    "side_effect_summary": payload.get("side_effect_summary") or {},
                }
            )
    runs.sort(key=lambda item: str(item.get("started_at") or item.get("run_id") or ""), reverse=True)
    return {
        "schema_version": 1,
        "action": "workflow_list_runs",
        "created_at": _now(),
        "run_root": str(root),
        "run_count": len(runs),
        "runs": runs[:30],
    }


def workflow_read_run_log_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    return _read_json(_workflow_run_dir_required(request) / "run_log.json")


def workflow_plan_from_run_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    from launcher.plugins.iso_tools.workflow.projection import plan_from_run

    return plan_from_run(_workflow_run_dir_required(request))


def workflow_read_artifact_action(request: IsoWorkflowRequest) -> dict[str, Any]:
    from launcher.plugins.iso_tools.workflow.projection import read_artifact

    node_id = (request.workflow_node_id or "").strip()
    port = (request.workflow_port or "").strip()
    if not node_id or not port:
        raise ValueError("workflow_read_artifact 需要 workflow_node_id 與 workflow_port。")
    run_dir = _workflow_run_dir_required(request)
    ref, payload = read_artifact(run_dir, node_id, port)
    return {
        "schema_version": 1,
        "action": "workflow_read_artifact",
        "created_at": _now(),
        "run_id": request.workflow_run_id or request.run_id or "",
        "node_id": node_id,
        "port": port,
        "ref": ref,
        "payload": payload,
    }


def workflow_parity_history_action(_request: IsoWorkflowRequest) -> dict[str, Any]:
    from launcher.plugins.iso_tools.workflow.parity import list_parity_reports

    return list_parity_reports(limit=10)


def apply_iso_plan(request: IsoWorkflowRequest) -> dict[str, Any]:
    selected_rows = [row for row in request.rows if row.get("selected")]
    operations = [RenameOperation(Path(row["source_path"]), Path(row["target_path"])) for row in selected_rows]
    if not operations:
        return {
            "schema_version": 1,
            "action": "apply",
            "created_at": _now(),
            "renamed_count": 0,
            "rows": [],
            "message": "沒有勾選需要更名的 PDF。",
        }
    _validate_operations(operations)
    record = _record_apply_csv(request, selected_rows, operations)
    _apply_operations(operations)
    payload = {
        "schema_version": 1,
        "action": "apply",
        "created_at": _now(),
        "renamed_count": len(operations),
        "rows": [
            {
                "source_path": str(operation.source),
                "target_path": str(operation.target),
                "source_name": operation.source.name,
                "target_name": operation.target.name,
            }
            for operation in operations
        ],
        "message": f"已更名 {len(operations)} 個 PDF。",
    }
    if record is not None:
        payload["record_path"] = record["path"]
        payload["record_row_count"] = record["row_count"]
    return payload


def _record_apply_csv(
    request: IsoWorkflowRequest,
    rows: list[dict[str, Any]],
    operations: list[RenameOperation],
) -> dict[str, Any] | None:
    if not request.run_id:
        return None
    created_at = _now()
    record_path = iso_run_root() / request.run_id / "artifacts" / "apply_rename_record.csv"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    operation_by_source = {str(operation.source): operation for operation in operations}
    columns = [
        "selected",
        "page",
        "source_name",
        "serial",
        "line_no",
        "new_name",
        "status",
        "confidence",
        "note",
        "vision_message",
        "source_path",
        "target_path",
        "target_name",
        "created_at",
    ]
    with record_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            operation = operation_by_source.get(str(row.get("source_path") or ""))
            source = operation.source if operation is not None else Path(str(row.get("source_path") or ""))
            target = operation.target if operation is not None else Path(str(row.get("target_path") or ""))
            exported_row = {column: row.get(column, "") for column in columns}
            exported_row["selected"] = True
            exported_row["source_path"] = str(source)
            exported_row["target_path"] = str(target)
            exported_row["target_name"] = target.name
            exported_row["created_at"] = created_at
            writer.writerow(exported_row)
    return {"path": str(record_path), "row_count": len(rows)}


def export_plan_csv(request: IsoWorkflowRequest) -> dict[str, Any]:
    rows = list(request.rows)
    if not rows:
        rows = build_iso_plan(request)["rows"]
    if not rows:
        raise ValueError("沒有可匯出的命名草稿。")

    created_at = _now()
    explicit_export_path = request.export_path is not None
    export_path = request.export_path or _default_export_path(request, rows)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "selected",
        "page",
        "source_name",
        "serial",
        "line_no",
        "new_name",
        "status",
        "confidence",
        "note",
        "vision_message",
        "source_path",
        "target_path",
        "created_at",
    ]
    _write_export_csv_atomic(export_path, columns, rows, created_at)
    retention_issues = [] if explicit_export_path else _prune_exports(export_path.parent)

    selected_count = sum(1 for row in rows if row.get("selected"))
    payload = {
        "schema_version": 1,
        "action": "export_plan_csv",
        "created_at": created_at,
        "export_path": str(export_path),
        "export_dir": str(export_path.parent),
        "row_count": len(rows),
        "selected_count": selected_count,
        "message": f"已匯出命名草稿 CSV：{export_path}",
    }
    if retention_issues:
        payload["retention_issues"] = retention_issues
    return payload


def _write_export_csv_atomic(export_path: Path, columns: list[str], rows: list[dict[str, Any]], created_at: str) -> None:
    temporary = export_path.with_name(f".{export_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                exported_row = {column: row.get(column, "") for column in columns}
                exported_row["created_at"] = created_at
                writer.writerow(exported_row)
        os.replace(temporary, export_path)
    except (PermissionError, OSError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        if _is_csv_lock_error(exc):
            raise ValueError(f"CSV 正被其他程式（例如 Excel）開啟，請關閉後重試：{export_path}") from exc
        raise


def _prune_exports(folder: Path, *, keep: int = 50) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    files = sorted(folder.glob("iso_rename_plan_*.csv"), key=_export_prune_key, reverse=True)
    for path in files[max(0, keep) :]:
        try:
            path.unlink()
        except OSError as exc:
            issues.append({"path": str(path), "error": str(exc)})
    return issues


def _export_prune_key(path: Path) -> tuple[float, str]:
    try:
        return path.stat().st_mtime, path.name
    except OSError:
        return 0.0, path.name


def _is_csv_lock_error(exc: OSError) -> bool:
    return isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {32, 33}


def export_debug_bundle(request: IsoWorkflowRequest) -> dict[str, Any]:
    if not request.run_id:
        raise ValueError("缺少 run_id，無法匯出 ISO 問題包。")
    return export_iso_debug_bundle(request.run_id, request.export_path)


def start_batch_detect(request: IsoWorkflowRequest) -> dict[str, Any]:
    job_id = request.job_id or uuid.uuid4().hex
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    job = _initial_job_payload(job_id, "queued")
    if request.run_id:
        job["run_id"] = request.run_id
    _write_json(job_dir / "job.json", job)
    _write_json(job_dir / "request.json", _request_payload(request))
    _spawn_iso_worker(job_dir)
    return _read_json(job_dir / "job.json")


def iso_job_status(request: IsoWorkflowRequest) -> dict[str, Any]:
    job_dir = _job_dir_required(request)
    return _read_json(job_dir / "job.json")


def cancel_iso_job(request: IsoWorkflowRequest) -> dict[str, Any]:
    job_dir = _job_dir_required(request)
    _write_json(job_dir / "cancel.json", {"cancelled_at": _now()})
    job = _read_json(job_dir / "job.json")
    if job.get("state") in {"queued", "running"}:
        job["state"] = "cancel_requested"
        job["updated_at"] = _now()
        _write_json(job_dir / "job.json", job)
    return job


def _resolve_pdfs(request: IsoWorkflowRequest) -> tuple[list[Path], str, Path | None, list[dict[str, str]]]:
    events: list[dict[str, str]] = []
    if request.page_folder is not None:
        if not request.page_folder.exists() or not request.page_folder.is_dir():
            raise FileNotFoundError(f"頁面資料夾不存在：{request.page_folder}")
        pdfs = _pdfs_from_folder(request.page_folder)
        if not pdfs:
            raise ValueError(f"頁面資料夾沒有 PDF：{request.page_folder}")
        return pdfs, "page_folder", request.page_folder, events

    combine_pdf = request.combine_pdf
    if combine_pdf is None and request.work_folder is not None:
        combine_pdf = _auto_combine_pdf_candidate(request.work_folder)
        if combine_pdf is None:
            pdfs = _pdfs_from_folder(request.work_folder) if request.work_folder.exists() and request.work_folder.is_dir() else []
            if pdfs:
                events.append({"code": "PDF00", "tone": "ready", "title": "使用資料夾內 PDF", "detail": str(request.work_folder)})
                return pdfs, "work_folder_pages", request.work_folder, events

    if combine_pdf is None:
        raise ValueError("請選擇 combine PDF 或頁面 PDF 資料夾。")
    if not combine_pdf.exists():
        raise FileNotFoundError(f"combine PDF 不存在：{combine_pdf}")

    page_folder = combine_pdf.with_name(f"{combine_pdf.stem}_pages")
    if page_folder.exists():
        existing_pages = _pdfs_from_folder(page_folder)
        if existing_pages:
            events.append({"code": "PDF01", "tone": "ready", "title": "使用既有拆頁資料夾", "detail": str(page_folder)})
            return existing_pages, "existing_pages", page_folder, events

    outputs = split_pdf_to_pages(combine_pdf)
    if not outputs:
        raise ValueError("combine PDF 沒有可拆出的頁面。")
    events.append({"code": "PDF02", "tone": "ready", "title": "已拆成單頁 PDF", "detail": f"{len(outputs)} pages"})
    return outputs, "combine_pdf", outputs[0].parent, events


def _resolve_iso_records(request: IsoWorkflowRequest) -> tuple[list[IsoRecord], dict[str, Any]]:
    iso_candidates = [str(path) for path in _nearby_iso_list_candidates(request)]
    iso_list = request.iso_list or (Path(iso_candidates[0]) if iso_candidates else None)
    if iso_list is None:
        raise ValueError("請選擇 ISO List。")
    if not iso_list.exists():
        raise FileNotFoundError(f"ISO List 不存在：{iso_list}")

    sheet_name, sheet_options = _resolve_sheet_name(iso_list, request.sheet_name)
    table = read_iso_table(iso_list, sheet_name=sheet_name)
    guessed_serial_col, guessed_line_col = guess_iso_columns(table.headers)
    serial_col = request.serial_col if request.serial_col is not None else guessed_serial_col
    line_col = request.line_col if request.line_col is not None else guessed_line_col
    if serial_col is None or line_col is None:
        raise ValueError("找不到 ISO List 欄位，請確認有「流水號」與「圖號/檔名」欄位。")
    records = records_from_table(table, serial_col=serial_col, line_col=line_col)
    if not records:
        raise ValueError("ISO List 沒有有效資料。")
    return records, {
        "iso_list": iso_list,
        "iso_candidates": iso_candidates,
        "sheet_name": table.sheet_name,
        "sheet_options": sheet_options,
        "headers": list(table.headers),
        "serial_col": serial_col,
        "line_col": line_col,
        "issues": [
            {
                "code": "ISO01",
                "tone": "ready",
                "title": "ISO List 已載入",
                "detail": f"{table.sheet_name} · {len(records)} rows",
            }
        ],
    }


def _build_plan_rows(
    pdfs: list[Path],
    lookup: dict[str, IsoRecord],
    *,
    pattern: str,
    detect_serials: bool,
    confidence_threshold: float = SERIAL_AUTO_FILL_CONFIDENCE,
    detector: Any | None = None,
    start_index: int = 1,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    events: list[dict[str, str]] = []
    serial_detector = detector if detect_serials else None
    if detect_serials and serial_detector is None:
        serial_detector = _SerialDetector()
    seen_targets: set[Path] = set()

    for index, source in enumerate(pdfs, start=start_index):
        default_serial = str(index)
        filename_vision = _vision_from_existing_iso_filename(source, lookup)
        vision = filename_vision or (
            serial_detector.detect(source, lookup)
            if serial_detector is not None
            else SerialVisionResult("", 0.0, "")
        )
        serial, note = _serial_for_row(default_serial, vision, lookup, confidence_threshold)
        record = lookup.get(serial)
        line_no = record.line_no if record else ""
        new_name = format_iso_name(pattern, serial=serial, line=line_no)
        target = source.with_name(new_name) if new_name else source
        status, status_note = _row_status(source, target, new_name, line_no, note, seen_targets)
        if new_name:
            seen_targets.add(target)
        selected = status in ("ready", "warn") and bool(new_name) and new_name != source.name
        row_note = status_note or note
        if row_note:
            events.append({"code": "ROW", "tone": status, "title": source.name, "detail": row_note})
        rows.append(
            {
                "id": f"row-{index}",
                "page": index,
                "source_path": str(source),
                "source_name": source.name,
                "serial": serial,
                "line_no": line_no,
                "new_name": new_name,
                "target_path": str(target),
                "status": status,
                "selected": selected,
                "confidence": round(float(vision.confidence), 3),
                "vision_message": vision.message,
                "note": row_note,
            }
        )
    return rows, events


def _vision_from_existing_iso_filename(source: Path, lookup: dict[str, IsoRecord]) -> SerialVisionResult | None:
    parsed = parse_iso_filename(source.name)
    if parsed is None:
        return None
    record = lookup.get(parsed.serial)
    if record is None:
        return None
    expected_name = format_iso_name(DEFAULT_PATTERN, serial=record.serial, line=record.line_no)
    if source.name.casefold() != expected_name.casefold():
        return None
    return SerialVisionResult(record.serial, 1.0, "檔名已符合 ISO List")


def _serial_for_row(default_serial: str, vision: SerialVisionResult, lookup: dict[str, IsoRecord], confidence_threshold: float) -> tuple[str, str]:
    if not vision.text:
        return default_serial, vision.message
    result = correct_result_with_iso_lookup(vision, lookup)
    if result.confidence < confidence_threshold:
        return default_serial, f"判讀信心太低 {result.confidence:.2f}，暫用頁序 {default_serial}"
    if result.text not in lookup:
        return default_serial, f"ISO List 無此流水號 {result.text}，暫用頁序 {default_serial}"
    return result.text, ""


def _row_status(source: Path, target: Path, new_name: str, line_no: str, note: str, seen_targets: set[Path]) -> tuple[str, str]:
    if not new_name:
        return "blocked", note or "無法產生新檔名"
    try:
        _validate_file_name(Path(new_name).name)
    except ValueError as exc:
        return "blocked", str(exc)
    if not line_no:
        return "blocked", note or "ISO List 找不到對應圖號/檔名"
    if target in seen_targets:
        return "blocked", f"目標檔名重複：{target.name}"
    if target.exists() and target != source:
        return "blocked", f"目標已存在：{target.name}"
    if note:
        return "warn", note
    if new_name == source.name:
        return "idle", "檔名已相同"
    return "ready", ""


def _summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "ready": sum(1 for row in rows if row["status"] == "ready"),
        "warn": sum(1 for row in rows if row["status"] == "warn"),
        "blocked": sum(1 for row in rows if row["status"] == "blocked"),
        "selected": sum(1 for row in rows if row["selected"]),
    }


def _default_export_path(request: IsoWorkflowRequest, rows: list[dict[str, Any]]) -> Path:
    folder = _default_export_folder(request, rows)
    return folder / f"iso_rename_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


def _default_export_folder(request: IsoWorkflowRequest, rows: list[dict[str, Any]]) -> Path:
    return runtime_root() / ".runtime" / "exports" / "iso"


def _steps(source_kind: str, pdf_count: int, record_count: int, detect_serials: bool, summary: dict[str, int]) -> list[dict[str, str]]:
    split_state = "ready" if source_kind in {"combine_pdf", "existing_pages", "page_folder", "work_folder_pages"} and pdf_count else "blocked"
    detect_state = "ready" if detect_serials else "idle"
    plan_state = "blocked" if summary["blocked"] else "warn" if summary["warn"] else "ready"
    return [
        {"label": "來源", "state": "ready" if pdf_count else "blocked", "meta": f"{pdf_count} PDFs"},
        {"label": "拆頁", "state": split_state, "meta": source_kind},
        {"label": "ISO", "state": "ready" if record_count else "blocked", "meta": f"{record_count} rows"},
        {"label": "判讀", "state": detect_state, "meta": "enabled" if detect_serials else "page order"},
        {"label": "命名", "state": plan_state, "meta": f"{summary['selected']} selected"},
        {"label": "更名", "state": "idle", "meta": "manual apply"},
    ]


def _pdfs_from_folder(folder: Path) -> list[Path]:
    return sorted((path for path in folder.iterdir() if path.suffix.lower() == ".pdf"), key=natural_pdf_key)


def _auto_combine_pdf_candidate(folder: Path) -> Path | None:
    if not folder.exists() or not folder.is_dir():
        return None
    pdfs = _pdfs_from_folder(folder)
    if not pdfs:
        return None
    non_page_pdfs = [path for path in pdfs if not _looks_like_page_pdf(path)]
    if len(non_page_pdfs) == 1:
        return non_page_pdfs[0]
    if len(pdfs) == 1:
        return pdfs[0]
    scored = sorted(
        non_page_pdfs,
        key=lambda path: (
            30 if "combine" in path.stem.lower() else 0,
            20 if "合併" in path.stem else 0,
            path.stat().st_size,
            path.stat().st_mtime,
        ),
        reverse=True,
    )
    return scored[0] if scored else None


def _nearby_iso_list_candidates(request: IsoWorkflowRequest) -> list[Path]:
    candidates: list[Path] = []
    for root in _source_roots(request):
        for pattern in ("*.xlsx", "*.xlsm", "*.csv"):
            candidates.extend(path for path in root.glob(pattern) if not path.name.startswith("~$"))

    def score(path: Path) -> tuple[int, float]:
        name = path.stem.lower()
        value = 0
        for keyword, points in (
            ("iso", 40),
            ("圖號", 35),
            ("清單", 25),
            ("list", 20),
            ("dwg", 20),
            ("pdf_page_to_new_name", -80),
            ("rename_plan", -100),
        ):
            if keyword in name:
                value += points
        return value, path.stat().st_mtime

    unique = sorted(set(candidates), key=score, reverse=True)
    return [path for path in unique if score(path)[0] > -50]


def _source_roots(request: IsoWorkflowRequest) -> list[Path]:
    roots: list[Path] = []
    for path in (
        request.page_folder,
        request.combine_pdf.parent if request.combine_pdf else None,
        request.work_folder,
        request.iso_list.parent if request.iso_list else None,
    ):
        if path and path.exists():
            root = path if path.is_dir() else path.parent
            if root not in roots:
                roots.append(root)
    return roots


def _looks_like_page_pdf(path: Path) -> bool:
    stem = path.stem.casefold()
    return bool(
        re.search(r"(^|[_\-\s])(p|page|頁)\s*0*\d{1,4}$", stem)
        or re.search(r"(^|[_\-\s])0*\d{1,4}$", stem)
    )


def _normalize_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": str(payload.get("action") or "plan"),
        "profile_folder": _path_or_none(payload.get("profile_folder")),
        "work_folder": _path_or_none(payload.get("work_folder")),
        "combine_pdf": _path_or_none(payload.get("combine_pdf")),
        "page_folder": _path_or_none(payload.get("page_folder")),
        "iso_list": _path_or_none(payload.get("iso_list")),
        "sheet_name": str(payload.get("sheet_name") or "").strip() or None,
        "serial_col": _int_or_none(payload.get("serial_col")),
        "line_col": _int_or_none(payload.get("line_col")),
        "pattern": str(payload.get("pattern") or "").strip() or None,
        "serial_region": _dict_or_none(payload.get("serial_region")),
        "drawing_region": _dict_or_none(payload.get("drawing_region")),
        "confidence_threshold": _float_or_none(payload.get("confidence_threshold")),
        "detect_serials": bool(payload.get("detect_serials")),
        "export_path": _path_or_none(payload.get("export_path")),
        "job_id": str(payload.get("job_id") or "").strip() or None,
        "run_id": str(payload.get("run_id") or "").strip() or None,
        "workflow_path": _path_or_none(payload.get("workflow_path")),
        "workflow": _dict_or_none(payload.get("workflow") or payload.get("graph")),
        "workflow_inputs": _dict_or_none(payload.get("workflow_inputs")),
        "workflow_allow": _str_tuple(payload.get("workflow_allow") or payload.get("allow")),
        "workflow_confirm": _str_tuple(payload.get("workflow_confirm") or payload.get("confirm")),
        "workflow_mode": str(payload.get("workflow_mode") or payload.get("mode") or "").strip() or None,
        "workflow_job_id": str(payload.get("workflow_job_id") or "").strip() or None,
        "workflow_run_id": str(payload.get("workflow_run_id") or payload.get("source_run_id") or "").strip() or None,
        "workflow_node_id": str(payload.get("workflow_node_id") or "").strip() or None,
        "workflow_port": str(payload.get("workflow_port") or "").strip() or None,
        "rows": tuple(payload.get("rows") or ()),
    }


def _path_or_none(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _str_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _state_store() -> AppStateStore:
    override = os.environ.get(STATE_PATH_ENV)
    return AppStateStore(Path(override)) if override else AppStateStore()


def _workflow_graph_from_request(request: IsoWorkflowRequest) -> Any:
    from launcher.plugins.iso_tools.workflow.schema import load_workflow, normalize_graph

    if request.workflow is not None:
        return normalize_graph(request.workflow)
    if request.workflow_path is None:
        raise ValueError("請提供 workflow_path 或 workflow graph。")
    path = _resolve_workflow_path(request.workflow_path)
    return load_workflow(path)


def _workflow_validation_payload(graph: Any) -> dict[str, Any]:
    from launcher.plugins.iso_tools.workflow.errors import GraphValidationError
    from launcher.plugins.iso_tools.workflow.executor import topological_order, validate_graph
    from launcher.plugins.iso_tools.workflow.registry import get_registry

    issues = validate_graph(graph, get_registry())
    errors = [issue for issue in issues if issue.severity == "error"]
    topology: list[str] = []
    if not errors:
        try:
            topology = topological_order(graph)
        except GraphValidationError as exc:
            issues.extend(exc.issues)
    return {
        "valid": not any(issue.severity == "error" for issue in issues),
        "issues": [issue.to_payload() for issue in issues],
        "edges": [edge.to_payload() for edge in graph.edges],
        "topology": topology,
    }


def _workflow_policy_from_request(request: IsoWorkflowRequest) -> Any:
    from launcher.plugins.iso_tools.workflow.policy import GUARDED, SideEffectPolicy

    mode = (request.workflow_mode or "run").strip() or "run"
    if mode not in {"run", "dry_run", "replay"}:
        raise ValueError(f"workflow_mode 不支援：{mode}")
    if mode == "replay" and (request.workflow_allow or request.workflow_confirm):
        raise ValueError("workflow replay 不接受 allow/confirm。")
    allowed = frozenset(request.workflow_allow)
    unknown = allowed - GUARDED
    if unknown:
        raise ValueError(f"workflow_allow 只接受 guarded side effects {sorted(GUARDED)}；收到 {sorted(unknown)}")
    return SideEffectPolicy(
        mode=mode,
        allowed_guarded=allowed,
        confirmed_nodes=frozenset(request.workflow_confirm),
    )


def _workflow_request_payload(request: IsoWorkflowRequest, *, job_id: str) -> dict[str, Any]:
    return {
        "action": "workflow_run",
        "workflow_path": str(request.workflow_path or ""),
        "workflow": request.workflow,
        "workflow_inputs": request.workflow_inputs or {},
        "workflow_allow": list(request.workflow_allow),
        "workflow_confirm": list(request.workflow_confirm),
        "workflow_mode": request.workflow_mode or "run",
        "workflow_job_id": job_id,
        "workflow_run_id": request.workflow_run_id or request.run_id or "",
    }


def _resolve_workflow_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _workflow_job_root() -> Path:
    root = os.environ.get("DESKTOP_SUPPORT_WORKFLOW_JOB_ROOT")
    if root:
        return Path(root)
    project_root = os.environ.get(PROJECT_ROOT_ENV)
    if project_root:
        return Path(project_root) / ".runtime" / "jobs" / "workflow"
    return runtime_root() / ".runtime" / "jobs" / "workflow"


def _workflow_run_root() -> Path:
    root = os.environ.get("DESKTOP_SUPPORT_WORKFLOW_RUN_ROOT")
    if root:
        return Path(root)
    project_root = os.environ.get(PROJECT_ROOT_ENV)
    if project_root:
        return Path(project_root) / ".runtime" / "runs" / "workflow"
    return runtime_root() / ".runtime" / "runs" / "workflow"


def _workflow_job_dir(job_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "", job_id)
    if not safe_id:
        raise ValueError("workflow_job_id 不合法。")
    return _workflow_job_root() / safe_id


def _workflow_job_dir_required(request: IsoWorkflowRequest) -> Path:
    job_id = request.workflow_job_id or request.job_id
    if not job_id:
        raise ValueError("缺少 workflow_job_id。")
    job_dir = _workflow_job_dir(job_id)
    if not (job_dir / "job.json").exists():
        raise FileNotFoundError(f"找不到 workflow job：{job_id}")
    return job_dir


def _workflow_run_dir_required(request: IsoWorkflowRequest) -> Path:
    run_id = request.workflow_run_id or request.run_id
    if not run_id:
        raise ValueError("缺少 workflow_run_id。")
    candidate = Path(run_id)
    if candidate.exists() and candidate.is_dir():
        root = _workflow_run_root().resolve()
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("workflow_run_id 不可指向 run root 以外路徑。")
        if not (resolved / "run_log.json").exists():
            raise FileNotFoundError(f"找不到 workflow run log：{run_id}")
        return resolved
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "", run_id)
    if not safe_id:
        raise ValueError("workflow_run_id 不合法。")
    run_dir = _workflow_run_root() / safe_id
    if not (run_dir / "run_log.json").exists():
        raise FileNotFoundError(f"找不到 workflow run log：{run_id}")
    return run_dir


def _initial_workflow_job_payload(job_id: str, state: str) -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": 1,
        "action": "workflow_job",
        "workflow_job_id": job_id,
        "job_id": job_id,
        "state": state,
        "created_at": now,
        "updated_at": now,
        "progress": {"total": 0, "done": 0, "percent": 0, "current_node": ""},
        "topology": [],
        "nodes": {},
        "result": None,
        "error": "",
    }


def _job_root() -> Path:
    root = os.environ.get("DESKTOP_SUPPORT_JOB_ROOT")
    if root:
        return Path(root)
    project_root = os.environ.get(PROJECT_ROOT_ENV)
    if project_root:
        return Path(project_root) / ".runtime" / "jobs" / "iso"
    return runtime_root() / ".runtime" / "jobs" / "iso"


def _job_dir(job_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "", job_id)
    if not safe_id:
        raise ValueError("job_id 不合法。")
    return _job_root() / safe_id


def _job_dir_required(request: IsoWorkflowRequest) -> Path:
    if not request.job_id:
        raise ValueError("缺少 job_id。")
    job_dir = _job_dir(request.job_id)
    if not (job_dir / "job.json").exists():
        raise FileNotFoundError(f"找不到 ISO job：{request.job_id}")
    return job_dir


def _initial_job_payload(job_id: str, state: str) -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": 1,
        "action": "batch_detect_job",
        "job_id": job_id,
        "state": state,
        "created_at": now,
        "updated_at": now,
        "progress": {"total": 0, "done": 0, "percent": 0},
        "rows": [],
        "issues": [],
        "events": [],
        "result": None,
        "error": "",
    }


def _request_payload(request: IsoWorkflowRequest) -> dict[str, Any]:
    return {
        "action": request.action,
        "profile_folder": str(request.profile_folder or ""),
        "work_folder": str(request.work_folder or ""),
        "combine_pdf": str(request.combine_pdf or ""),
        "page_folder": str(request.page_folder or ""),
        "iso_list": str(request.iso_list or ""),
        "sheet_name": request.sheet_name or "",
        "serial_col": request.serial_col,
        "line_col": request.line_col,
        "pattern": request.pattern or "",
        "serial_region": request.serial_region,
        "drawing_region": request.drawing_region,
        "confidence_threshold": request.confidence_threshold,
        "detect_serials": request.detect_serials,
        "export_path": str(request.export_path or ""),
        "job_id": request.job_id,
        "run_id": request.run_id,
        "workflow_run_id": request.workflow_run_id,
        "workflow_node_id": request.workflow_node_id,
        "workflow_port": request.workflow_port,
        "rows": list(request.rows),
    }


def _should_write_run_log(request: IsoWorkflowRequest) -> bool:
    return request.action in {"plan", "build_rename_plan", "start_batch_detect", "apply"}


def _spawn_iso_worker(job_dir: Path) -> None:
    command = [sys.executable, "-m", "launcher.app.tauri_iso_worker", str(job_dir)]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )


def _spawn_workflow_job(job_dir: Path) -> None:
    command = [sys.executable, "-m", "launcher.app.tauri_workflow_job", str(job_dir)]
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _with_profile_defaults(
    request: IsoWorkflowRequest,
    *,
    resolved_page_folder: Path | None = None,
) -> tuple[IsoWorkflowRequest, dict[str, Any]]:
    folder, profile, candidates = _load_profile_for_request(request, resolved_page_folder=resolved_page_folder)
    if profile is None:
        return request, _profile_response(
            action="load_profile",
            folder=folder,
            profile=IsoNamingProfile(),
            exists=False,
            candidates=candidates,
            message="未套用既有 profile。",
        )

    updates: dict[str, Any] = {}
    if request.iso_list is None and profile.iso_list_path is not None and profile.iso_list_path.exists():
        updates["iso_list"] = profile.iso_list_path
    if request.sheet_name is None:
        updates["sheet_name"] = profile.sheet_name
    if request.serial_col is None:
        updates["serial_col"] = profile.serial_col
    if request.line_col is None:
        updates["line_col"] = profile.line_col
    if request.pattern is None or request.pattern == DEFAULT_PATTERN:
        updates["pattern"] = profile.pattern
    if request.serial_region is None:
        updates["serial_region"] = _region_payload(profile.serial_region)
    if request.drawing_region is None:
        updates["drawing_region"] = _region_payload(profile.drawing_region)
    if request.confidence_threshold is None:
        updates["confidence_threshold"] = profile.confidence_threshold
    return replace(request, **updates), _profile_response(
        action="load_profile",
        folder=folder,
        profile=profile,
        exists=True,
        candidates=candidates,
        message=f"已套用 ISO profile：{folder}",
    )


def _profile_folder(request: IsoWorkflowRequest) -> Path | None:
    return next(iter(_profile_folder_candidates(request)), None)


def _load_profile_for_request(
    request: IsoWorkflowRequest,
    *,
    resolved_page_folder: Path | None = None,
) -> tuple[Path | None, IsoNamingProfile | None, list[Path]]:
    candidates = _profile_folder_candidates(request, resolved_page_folder=resolved_page_folder)
    store = _state_store()
    for folder in candidates:
        profile = load_iso_naming_profile(store, folder)
        if profile is not None:
            return folder, profile, candidates
    return (candidates[0] if candidates else None), None, candidates


def _profile_folder_candidates(
    request: IsoWorkflowRequest,
    *,
    resolved_page_folder: Path | None = None,
) -> list[Path]:
    candidates: list[Path] = []

    def add_folder(path: Path | None) -> None:
        if path is None:
            return
        folder = path if _is_probable_folder(path) else path.parent
        if folder not in candidates:
            candidates.append(folder)

    def add_exact_folder(path: Path | None) -> None:
        if path is not None and path not in candidates:
            candidates.append(path)

    add_folder(request.profile_folder)
    add_exact_folder(request.page_folder)
    add_exact_folder(resolved_page_folder)
    if request.combine_pdf is not None:
        add_exact_folder(request.combine_pdf.with_name(f"{request.combine_pdf.stem}_pages"))
    if request.work_folder is not None:
        combine_candidate = _auto_combine_pdf_candidate(request.work_folder)
        if combine_candidate is not None:
            add_exact_folder(combine_candidate.with_name(f"{combine_candidate.stem}_pages"))
        add_existing_page_folders(request.work_folder, candidates)
    add_folder(request.work_folder)
    add_folder(request.combine_pdf.parent if request.combine_pdf else None)
    add_folder(request.iso_list.parent if request.iso_list else None)
    return candidates


def add_existing_page_folders(root: Path, candidates: list[Path]) -> None:
    if not root.exists() or not root.is_dir():
        return
    page_folders = sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.casefold().endswith("_pages")),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for folder in page_folders:
        if folder not in candidates:
            candidates.append(folder)


def _is_probable_folder(path: Path) -> bool:
    if path.exists():
        return path.is_dir()
    return not path.suffix


def _profile_from_request(request: IsoWorkflowRequest, base: IsoNamingProfile) -> IsoNamingProfile:
    return IsoNamingProfile(
        serial_region=_region_from_payload(request.serial_region, base.serial_region),
        drawing_region=_region_from_payload(request.drawing_region, base.drawing_region),
        confidence_threshold=request.confidence_threshold if request.confidence_threshold is not None else base.confidence_threshold,
        pattern=_plan_pattern(request, base.pattern),
        iso_list_path=request.iso_list or base.iso_list_path,
        sheet_name=request.sheet_name or base.sheet_name,
        serial_col=request.serial_col if request.serial_col is not None else base.serial_col,
        line_col=request.line_col if request.line_col is not None else base.line_col,
    )


def _profile_response(
    *,
    action: str,
    folder: Path | None,
    profile: IsoNamingProfile,
    exists: bool,
    candidates: list[Path],
    message: str,
    profile_scope: str = "published",
) -> dict[str, Any]:
    payload = profile.to_payload()
    discovery = _source_discovery(folder=folder, profile=profile)
    draft_exists = False
    published_exists = exists
    history_count = 0
    if folder is not None:
        store = _state_store()
        draft_exists = load_iso_naming_profile_draft(store, folder) is not None
        published_exists = load_iso_naming_profile(store, folder) is not None
        history_count = len(iso_naming_profile_history(store, folder))
    return {
        "schema_version": 1,
        "action": action,
        "created_at": _now(),
        "exists": exists,
        "profile_scope": profile_scope,
        "published_exists": published_exists,
        "draft_exists": draft_exists,
        "history_count": history_count,
        "folder": str(folder or ""),
        "folder_exists": bool(folder and folder.exists()),
        "candidate_folders": [str(candidate) for candidate in candidates],
        "serial_region": payload["serial_region"],
        "drawing_region": payload["drawing_region"],
        "confidence_threshold": payload["confidence_threshold"],
        "pattern": payload["pattern"],
        "iso_list_path": payload["iso_list_path"],
        "sheet_name": payload["sheet_name"],
        "serial_col": payload["serial_col"],
        "line_col": payload["line_col"],
        **discovery,
        "message": message,
    }


def _request_has_profile_values(request: IsoWorkflowRequest) -> bool:
    return any(
        value is not None and value != ""
        for value in (
            request.serial_region,
            request.drawing_region,
            request.confidence_threshold,
            request.pattern,
            request.iso_list,
            request.sheet_name,
            request.serial_col,
            request.line_col,
        )
    )


def _with_pilot_results(payload: dict[str, Any], request: IsoWorkflowRequest) -> dict[str, Any]:
    report = build_pilot_report(request=_request_payload(request), plan=payload)
    return {
        **payload,
        "pilot_results": report["items"],
        "pilot_summary": report["summary"],
    }


def _source_discovery(*, folder: Path | None, profile: IsoNamingProfile) -> dict[str, Any]:
    combine_pdf = _discover_combine_pdf(folder)
    page_folder = _discover_page_folder(folder, combine_pdf)
    iso_list = (
        profile.iso_list_path
        if profile.iso_list_path is not None and profile.iso_list_path.exists()
        else _discover_iso_list(folder, combine_pdf, page_folder)
    )
    return {
        "detected_combine_pdf": str(combine_pdf) if combine_pdf else None,
        "detected_page_folder": str(page_folder) if page_folder else None,
        "detected_page_folder_exists": bool(page_folder and page_folder.exists()),
        "detected_iso_list": str(iso_list) if iso_list else None,
    }


def _discover_combine_pdf(folder: Path | None) -> Path | None:
    if folder is None:
        return None
    if folder.name.casefold().endswith("_pages"):
        stem = folder.name[:-6]
        inferred = folder.parent / f"{stem}.pdf"
        if inferred.exists():
            return inferred
        return _auto_combine_pdf_candidate(folder.parent)
    return _auto_combine_pdf_candidate(folder)


def _discover_page_folder(folder: Path | None, combine_pdf: Path | None) -> Path | None:
    if folder is not None and folder.name.casefold().endswith("_pages"):
        return folder
    if combine_pdf is not None:
        return combine_pdf.with_name(f"{combine_pdf.stem}_pages")
    return None


def _discover_iso_list(folder: Path | None, combine_pdf: Path | None, page_folder: Path | None) -> Path | None:
    roots: list[Path] = []
    for path in (
        folder,
        combine_pdf.parent if combine_pdf else None,
        page_folder.parent if page_folder else None,
    ):
        if path and path.exists():
            root = path if path.is_dir() else path.parent
            if root not in roots:
                roots.append(root)
    candidates: list[Path] = []
    for root in roots:
        for pattern in ("*.xlsx", "*.xlsm", "*.csv"):
            candidates.extend(path for path in root.glob(pattern) if not path.name.startswith("~$"))
    return _best_iso_candidate(candidates)


def _best_iso_candidate(candidates: list[Path]) -> Path | None:
    if not candidates:
        return None

    def score(path: Path) -> tuple[int, float]:
        name = path.stem.lower()
        value = 0
        for keyword, points in (
            ("iso", 40),
            ("圖號", 35),
            ("清單", 25),
            ("list", 20),
            ("dwg", 20),
            ("pdf_page_to_new_name", -80),
            ("rename_plan", -100),
        ):
            if keyword in name:
                value += points
        return value, path.stat().st_mtime

    scored = sorted(set(candidates), key=score, reverse=True)
    return scored[0] if scored and score(scored[0])[0] > -50 else None


def _plan_pattern(request: IsoWorkflowRequest, fallback: str = DEFAULT_PATTERN) -> str:
    return (request.pattern or fallback or DEFAULT_PATTERN).strip() or DEFAULT_PATTERN


def _region_from_payload(payload: dict[str, Any] | None, default: SerialVisionRegion) -> SerialVisionRegion:
    if not isinstance(payload, dict):
        return default
    return SerialVisionRegion(
        left=_float_value(payload.get("left"), default.left),
        top=_float_value(payload.get("top"), default.top),
        width=_float_value(payload.get("width"), default.width),
        height=_float_value(payload.get("height"), default.height),
    )


def _region_payload(region: SerialVisionRegion) -> dict[str, float]:
    return {
        "left": region.left,
        "top": region.top,
        "width": region.width,
        "height": region.height,
    }


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _read_stdin_json() -> str:
    return sys.stdin.buffer.read().decode("utf-8")


def _resolve_sheet_name(path: Path, requested_sheet: str | None) -> tuple[str | None, list[str]]:
    sheets = list_iso_sheets(path)
    if requested_sheet:
        return requested_sheet, sheets
    if len(sheets) <= 1:
        return None, sheets
    return _preferred_sheet_name(path, sheets), sheets


def _preferred_sheet_name(path: Path, sheets: list[str]) -> str | None:
    scored = [(_score_iso_sheet(path, sheet), index, sheet) for index, sheet in enumerate(sheets)]
    scored.sort(reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][2]
    preferred_keywords = ("dwg", "iso", "isometric", "list", "管線", "清單", "圖號")
    for sheet in sheets:
        normalized = sheet.lower().replace(" ", "")
        if any(keyword in normalized for keyword in preferred_keywords):
            return sheet
    return sheets[0] if sheets else None


def _score_iso_sheet(path: Path, sheet_name: str) -> int:
    score = 0
    normalized_sheet = sheet_name.lower().replace(" ", "")
    if any(keyword in normalized_sheet for keyword in ("dwg", "iso", "圖號", "清單", "list")):
        score += 10
    try:
        table = read_iso_table(path, sheet_name=sheet_name)
    except Exception:
        return score
    serial_col, line_col = guess_iso_columns(table.headers)
    if serial_col is not None:
        score += 30
    if line_col is not None:
        score += 30
        header = table.headers[line_col].lower()
        if any(keyword in header for keyword in ("file_basename", "dst_pdf_name", "source_pdf_name", "pdf", "檔名", "圖號")):
            score += 50
    score += min(20, len(table.rows) // 10)
    return score


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class _SerialDetector:
    def __init__(self) -> None:
        self._app = None
        self._cache_dir = Path(tempfile.mkdtemp(prefix="tauri_iso_preview_"))

    def detect(self, source: Path, lookup: dict[str, IsoRecord]) -> SerialVisionResult:
        try:
            self._ensure_qt()
            from launcher.ui.iso_pdf.batch_detect import detect_serial_from_pdf

            return correct_result_with_iso_lookup(detect_serial_from_pdf(source, DEFAULT_SERIAL_REGION), lookup)
        except Exception as exc:
            return SerialVisionResult("", 0.0, f"影像判讀失敗：{exc}")

    def _ensure_qt(self) -> None:
        if self._app is not None:
            return
        from PyQt6.QtWidgets import QApplication

        self._app = QApplication.instance() or QApplication([])


if __name__ == "__main__":
    raise SystemExit(main())
