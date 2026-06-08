from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from launcher.app.tauri_iso_workflow import (
    IsoWorkflowRequest,
    SERIAL_AUTO_FILL_CONFIDENCE,
    _SerialDetector,
    _build_plan_rows,
    _now,
    _normalize_request,
    _request_payload,
    _read_json,
    _resolve_iso_records,
    _resolve_pdfs,
    _steps,
    _summary,
    _with_profile_defaults,
    _write_json,
)
from launcher.plugins.iso_tools.iso_naming import build_record_lookup
from launcher.plugins.iso_tools.pilot import build_pilot_report
from launcher.plugins.iso_tools.run_log import (
    IsoRunLogContext,
    append_iso_run_event,
    ensure_iso_run,
    finish_iso_run_cancelled,
    finish_iso_run_failure,
    finish_iso_run_success,
    public_run_ref,
)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("missing job directory", file=sys.stderr)
        return 2
    try:
        run_job(Path(argv[0]))
        return 0
    except Exception as exc:
        try:
            _fail_job(Path(argv[0]), exc)
        except Exception:
            pass
        print(str(exc), file=sys.stderr)
        return 1


def run_job(job_dir: Path) -> dict[str, Any]:
    request_payload = _read_json(job_dir / "request.json")
    request = IsoWorkflowRequest(**_normalize_request(request_payload))
    run_context = ensure_iso_run(_request_payload(request), action="start_batch_detect", run_id=request.run_id)
    job = _read_json(job_dir / "job.json")
    job.update({"state": "running", "updated_at": _now(), "run_id": run_context.run_id, "run_log": public_run_ref(run_context)})
    _write_json(job_dir / "job.json", job)
    append_iso_run_event(run_context, {"code": "JOB_RUNNING", "tone": "ready", "title": "批次判讀開始", "detail": str(job_dir)})

    pdfs, source_kind, page_folder, pdf_events = _resolve_pdfs(request)
    request, loaded_profile = _with_profile_defaults(request, resolved_page_folder=page_folder)
    records, iso_meta = _resolve_iso_records(request)
    iso_meta["record_count"] = len(records)
    lookup = build_record_lookup(records)
    rows: list[dict[str, Any]] = []
    events: list[dict[str, str]] = [*pdf_events, *iso_meta["issues"]]
    total = len(pdfs)
    detector = _SerialDetector() if request.detect_serials else None

    for index, pdf in enumerate(pdfs, start=1):
        if (job_dir / "cancel.json").exists():
            return _cancel_job(job_dir, job, rows, events, total, run_context)
        row, row_events = _build_plan_rows(
            [pdf],
            lookup,
            pattern=request.pattern or "{serial}--{line}.pdf",
            detect_serials=request.detect_serials,
            confidence_threshold=request.confidence_threshold if request.confidence_threshold is not None else SERIAL_AUTO_FILL_CONFIDENCE,
            detector=detector,
            start_index=index,
        )
        row_payload = row[0]
        row_payload["id"] = f"row-{index}"
        row_payload["page"] = index
        rows.append(row_payload)
        events.extend(row_events)
        _write_progress(job_dir, job, rows, events, total, source_kind, page_folder, iso_meta, loaded_profile, request, run_context)

    result = _result_payload(rows, events, source_kind, page_folder, iso_meta, loaded_profile, request)
    job.update(
        {
            "state": "completed",
            "updated_at": _now(),
            "progress": {"total": total, "done": total, "percent": 100},
            "rows": rows,
            "issues": events,
            "result": result,
            "error": "",
        }
    )
    _write_json(job_dir / "job.json", job)
    finish_iso_run_success(run_context, result)
    return job


def _write_progress(
    job_dir: Path,
    job: dict[str, Any],
    rows: list[dict[str, Any]],
    events: list[dict[str, str]],
    total: int,
    source_kind: str,
    page_folder: Path | None,
    iso_meta: dict[str, Any],
    loaded_profile: dict[str, Any],
    request: IsoWorkflowRequest,
    run_context: IsoRunLogContext,
) -> None:
    done = len(rows)
    percent = round(done / total * 100) if total else 0
    row_done_event = {"code": "ROW_DONE", "tone": "ready", "title": f"{done}/{total}", "detail": rows[-1]["source_name"]}
    job.update(
        {
            "state": "running",
            "updated_at": _now(),
            "progress": {"total": total, "done": done, "percent": percent},
            "rows": rows,
            "issues": events,
            "events": [
                *job.get("events", []),
                row_done_event,
            ],
            "result": _result_payload(rows, events, source_kind, page_folder, iso_meta, loaded_profile, request),
        }
    )
    _write_json(job_dir / "job.json", job)
    append_iso_run_event(run_context, row_done_event)


def _cancel_job(
    job_dir: Path,
    job: dict[str, Any],
    rows: list[dict[str, Any]],
    events: list[dict[str, str]],
    total: int,
    run_context: IsoRunLogContext | None = None,
) -> dict[str, Any]:
    job.update(
        {
            "state": "cancelled",
            "updated_at": _now(),
            "progress": {"total": total, "done": len(rows), "percent": round(len(rows) / total * 100) if total else 0},
            "rows": rows,
            "issues": events,
            "events": [*job.get("events", []), {"code": "CANCELLED", "tone": "warn", "title": "批次判讀已取消", "detail": ""}],
        }
    )
    _write_json(job_dir / "job.json", job)
    if run_context is not None:
        finish_iso_run_cancelled(run_context, job)
    return job


def _fail_job(job_dir: Path, exc: Exception) -> None:
    job_path = job_dir / "job.json"
    job = _read_json(job_path) if job_path.exists() else {}
    job.update({"state": "failed", "updated_at": _now(), "error": str(exc)})
    _write_json(job_path, job)
    try:
        request_payload = _read_json(job_dir / "request.json")
        request = IsoWorkflowRequest(**_normalize_request(request_payload))
        run_context = ensure_iso_run(_request_payload(request), action="start_batch_detect", run_id=request.run_id or job.get("run_id"))
        finish_iso_run_failure(run_context, exc, action="start_batch_detect", payload=job)
    except Exception:
        pass


def _result_payload(
    rows: list[dict[str, Any]],
    events: list[dict[str, str]],
    source_kind: str,
    page_folder: Path | None,
    iso_meta: dict[str, Any],
    loaded_profile: dict[str, Any],
    request: IsoWorkflowRequest,
) -> dict[str, Any]:
    summary = _summary(rows)
    payload = {
        "schema_version": 1,
        "action": "batch_detect_result",
        "created_at": _now(),
        "source": {
            "kind": source_kind,
            "work_folder": str(request.work_folder or ""),
            "combine_pdf": str(request.combine_pdf or ""),
            "page_folder": str(page_folder or ""),
            "pdf_count": len(rows),
            "iso_list": str(iso_meta["iso_list"]),
            "sheet_name": iso_meta["sheet_name"],
            "sheet_options": iso_meta["sheet_options"],
            "headers": iso_meta["headers"],
            "serial_col": iso_meta["serial_col"],
            "line_col": iso_meta["line_col"],
            "record_count": iso_meta.get("record_count", 0),
            "pattern": request.pattern or "{serial}--{line}.pdf",
            "detect_serials": request.detect_serials,
            "profile": loaded_profile,
        },
        "summary": summary,
        "steps": _steps(source_kind, len(rows), int(iso_meta.get("record_count") or 0), request.detect_serials, summary),
        "rows": rows,
        "issues": events,
    }
    report = build_pilot_report(request=_request_payload(request), plan=payload)
    payload["pilot_results"] = report["items"]
    payload["pilot_summary"] = report["summary"]
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
