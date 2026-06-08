from __future__ import annotations

import json
import os
import re
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from launcher.core.paths import runtime_root

ISO_RUN_ROOT_ENV = "DESKTOP_SUPPORT_ISO_RUN_ROOT"
RUN_LOG_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class IsoRunLogContext:
    run_id: str
    run_dir: Path
    action: str
    request: dict[str, Any]

    @property
    def run_json_path(self) -> Path:
        return self.run_dir / "run.json"

    @property
    def events_path(self) -> Path:
        return self.run_dir / "events.jsonl"


def iso_run_root() -> Path:
    override = os.environ.get(ISO_RUN_ROOT_ENV)
    if override and override.strip():
        return Path(override).expanduser().resolve(strict=False)
    return runtime_root() / ".runtime" / "runs" / "iso"


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"iso-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def start_iso_run(request: dict[str, Any], *, action: str | None = None, run_type: str | None = None, run_id: str | None = None) -> IsoRunLogContext:
    request_payload = _jsonable(request)
    action = action or str(request_payload.get("action") or "unknown")
    run_id = _safe_run_id(run_id or str(request_payload.get("run_id") or "") or new_run_id())
    request_payload["run_id"] = run_id
    run_dir = iso_run_root() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    now = _now()
    payload = {
        "schema_version": RUN_LOG_SCHEMA_VERSION,
        "run_id": run_id,
        "run_type": run_type or _run_type_for_action(action),
        "action": action,
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "inputs": _inputs_from_request(request_payload),
        "profile": _profile_from_request(request_payload),
        "stages": [_stage_payload(action, "running")],
        "summary": {},
        "rows": [],
        "failure": None,
        "replay": {
            "action": action,
            "request": request_payload,
        },
    }
    _write_json(run_dir / "run.json", payload)
    context = IsoRunLogContext(run_id=run_id, run_dir=run_dir, action=action, request=request_payload)
    append_iso_run_event(context, {"code": "RUN_STARTED", "tone": "ready", "title": action, "detail": run_id})
    return context


def ensure_iso_run(request: dict[str, Any], *, action: str | None = None, run_type: str | None = None, run_id: str | None = None) -> IsoRunLogContext:
    request_payload = _jsonable(request)
    action = action or str(request_payload.get("action") or "unknown")
    run_id = _safe_run_id(run_id or str(request_payload.get("run_id") or "") or new_run_id())
    request_payload["run_id"] = run_id
    run_dir = iso_run_root() / run_id
    if (run_dir / "run.json").exists():
        return IsoRunLogContext(run_id=run_id, run_dir=run_dir, action=action, request=request_payload)
    return start_iso_run(request_payload, action=action, run_type=run_type, run_id=run_id)


def mark_iso_run_started(context: IsoRunLogContext, payload: dict[str, Any]) -> None:
    run = read_iso_run(context)
    now = _now()
    run.update(
        {
            "status": "running",
            "updated_at": now,
            "job": _job_from_payload(payload),
            "stages": _merge_stage(run.get("stages"), _stage_payload(context.action, "running")),
        }
    )
    _write_json(context.run_json_path, run)
    append_iso_run_event(context, {"code": "JOB_STARTED", "tone": "ready", "title": context.action, "detail": str(payload.get("job_id") or "")})


def finish_iso_run_success(context: IsoRunLogContext, payload: dict[str, Any], *, status: str = "completed") -> None:
    result_payload = _jsonable(payload)
    run = read_iso_run(context)
    now = _now()
    run.update(
        {
            "status": status,
            "updated_at": now,
            "stages": _merge_stage(run.get("stages"), _stage_payload(context.action, "completed")),
            "summary": _summary_from_payload(result_payload),
            "rows": _rows_from_payload(result_payload),
            "failure": None,
            "result": result_payload,
        }
    )
    if "source" in result_payload:
        run["inputs"] = {**run.get("inputs", {}), **_inputs_from_source(result_payload.get("source"))}
        run["profile"] = _profile_from_source(result_payload.get("source")) or run.get("profile", {})
    _write_json(context.run_json_path, run)
    append_iso_run_event(context, {"code": "RUN_COMPLETED", "tone": "ready", "title": context.action, "detail": status})


def finish_iso_run_cancelled(context: IsoRunLogContext, payload: dict[str, Any]) -> None:
    result_payload = _jsonable(payload)
    run = read_iso_run(context)
    now = _now()
    run.update(
        {
            "status": "cancelled",
            "updated_at": now,
            "stages": _merge_stage(run.get("stages"), _stage_payload(context.action, "cancelled")),
            "summary": _summary_from_payload(result_payload),
            "rows": _rows_from_payload(result_payload),
            "result": result_payload,
        }
    )
    _write_json(context.run_json_path, run)
    append_iso_run_event(context, {"code": "RUN_CANCELLED", "tone": "warn", "title": context.action, "detail": context.run_id})


def finish_iso_run_failure(context: IsoRunLogContext, exc: BaseException, *, action: str | None = None, payload: dict[str, Any] | None = None) -> None:
    action = action or context.action
    message = str(exc)
    failed_stage = classify_failed_stage(action, message)
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    traceback_lines = stack.splitlines()
    run = read_iso_run(context)
    now = _now()
    failure = {
        "failed_stage": failed_stage,
        "error_type": type(exc).__name__,
        "error_message": message,
        "user_summary": user_summary_for_failure(failed_stage, message),
        "exception_stack": stack,
        "traceback_lines": traceback_lines,
    }
    run.update(
        {
            "status": "failed",
            "updated_at": now,
            "stages": _merge_stage(run.get("stages"), _stage_payload(failed_stage, "failed")),
            "failure": failure,
        }
    )
    if payload:
        run["result"] = _jsonable(payload)
    _write_json(context.run_json_path, run)
    append_iso_run_event(context, {"code": "RUN_FAILED", "tone": "blocked", "title": failed_stage, "detail": message})


def append_iso_run_event(context: IsoRunLogContext, event: dict[str, Any]) -> None:
    event_payload = {
        "ts": _now(),
        "run_id": context.run_id,
        **_jsonable(event),
    }
    context.run_dir.mkdir(parents=True, exist_ok=True)
    with context.events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, ensure_ascii=False, sort_keys=True) + "\n")


def read_iso_run(context: IsoRunLogContext) -> dict[str, Any]:
    if not context.run_json_path.exists():
        return {
            "schema_version": RUN_LOG_SCHEMA_VERSION,
            "run_id": context.run_id,
            "run_type": _run_type_for_action(context.action),
            "action": context.action,
            "status": "running",
            "created_at": _now(),
            "updated_at": _now(),
            "inputs": _inputs_from_request(context.request),
            "profile": _profile_from_request(context.request),
            "stages": [],
            "summary": {},
            "rows": [],
            "failure": None,
            "replay": {"action": context.action, "request": context.request},
        }
    return json.loads(context.run_json_path.read_text(encoding="utf-8"))


def public_run_ref(context: IsoRunLogContext) -> dict[str, Any]:
    return {
        "schema_version": RUN_LOG_SCHEMA_VERSION,
        "run_id": context.run_id,
        "run_dir": str(context.run_dir),
        "run_json": str(context.run_json_path),
        "events_jsonl": str(context.events_path),
    }


def classify_failed_stage(action: str, message: str) -> str:
    text = f"{action} {message}".casefold()
    if action in {"apply"}:
        return "apply"
    if action in {"export_plan_csv"}:
        return "export_report"
    if action in {"start_batch_detect"}:
        return "serial_detection"
    if any(token in text for token in ("iso list", "sheet", "欄位", "流水號", "圖號", "有效資料")):
        return "iso_parse"
    if any(token in text for token in ("pdf", "combine", "頁面", "拆頁")):
        return "pdf_source"
    if action in {"plan", "build_rename_plan"}:
        return "naming_draft"
    if action in {"load_profile", "save_profile"}:
        return "profile"
    return action or "unknown"


def user_summary_for_failure(stage: str, message: str) -> str:
    if stage == "iso_parse":
        return "ISO List 讀取或欄位對應失敗，請到工作台檢查 sheet、流水號欄與圖號欄。"
    if stage == "pdf_source":
        return "PDF 來源讀取失敗，請確認檔案存在、可開啟，且沒有被其他程式鎖定。"
    if stage == "serial_detection":
        return "流水號判讀未完成，請到調校模式檢查 ROI、信心門檻與批次判讀紀錄。"
    if stage == "apply":
        return "更名套用失敗，請檢查目標檔名、檔案鎖定或路徑權限。"
    if stage == "profile":
        return "ISO profile 讀寫失敗，請檢查設定儲存位置是否可寫。"
    if message:
        return f"ISO 命名流程失敗：{message}"
    return "ISO 命名流程失敗，請匯出問題包交給工程師。"


def _run_type_for_action(action: str) -> str:
    if action == "start_batch_detect":
        return "batch_detect"
    if action == "apply":
        return "apply"
    if action in {"plan", "build_rename_plan"}:
        return "plan"
    return "workflow"


def _stage_payload(stage: str, status: str) -> dict[str, Any]:
    now = _now()
    payload: dict[str, Any] = {
        "id": stage,
        "status": status,
        "updated_at": now,
    }
    if status == "running":
        payload["started_at"] = now
    if status in {"completed", "failed", "cancelled"}:
        payload["finished_at"] = now
    return payload


def _merge_stage(stages: Any, stage: dict[str, Any]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    replaced = False
    for item in stages if isinstance(stages, list) else []:
        if isinstance(item, dict) and item.get("id") == stage.get("id"):
            merged.append({**item, **stage})
            replaced = True
        elif isinstance(item, dict):
            merged.append(item)
    if not replaced:
        merged.append(stage)
    return merged


def _job_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": payload.get("job_id"),
        "state": payload.get("state"),
        "progress": payload.get("progress"),
    }


def _summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("summary"), dict):
        return dict(payload["summary"])
    if isinstance(payload.get("result"), dict) and isinstance(payload["result"].get("summary"), dict):
        return dict(payload["result"]["summary"])
    if "renamed_count" in payload:
        return {"renamed_count": payload.get("renamed_count")}
    if isinstance(payload.get("progress"), dict):
        return {"progress": payload.get("progress")}
    return {}


def _rows_from_payload(payload: dict[str, Any]) -> list[Any]:
    rows = payload.get("rows")
    if isinstance(rows, list):
        return rows
    result = payload.get("result")
    if isinstance(result, dict) and isinstance(result.get("rows"), list):
        return result["rows"]
    return []


def _inputs_from_request(request: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "work_folder",
        "combine_pdf",
        "page_folder",
        "iso_list",
        "sheet_name",
        "serial_col",
        "line_col",
        "pattern",
        "detect_serials",
        "export_path",
        "job_id",
        "run_id",
    )
    return {key: request.get(key) for key in keys if request.get(key) not in (None, "")}


def _profile_from_request(request: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "profile_folder",
        "serial_region",
        "drawing_region",
        "confidence_threshold",
    )
    return {key: request.get(key) for key in keys if request.get(key) not in (None, "")}


def _inputs_from_source(source: Any) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    keys = (
        "work_folder",
        "combine_pdf",
        "page_folder",
        "pdf_count",
        "iso_list",
        "sheet_name",
        "serial_col",
        "line_col",
        "record_count",
        "pattern",
        "detect_serials",
    )
    return {key: source.get(key) for key in keys if source.get(key) not in (None, "")}


def _profile_from_source(source: Any) -> dict[str, Any] | None:
    if not isinstance(source, dict):
        return None
    profile = source.get("profile")
    return profile if isinstance(profile, dict) else None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _safe_run_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "", value)
    if not cleaned:
        return new_run_id()
    return cleaned[:96]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
