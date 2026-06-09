from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any

PILOT_SCHEMA_VERSION = 2
PILOT_ITEM_IDS = (
    "P01",
    "P02",
    "P03",
    "P04",
    "P05",
    "P06",
    "P07",
    "P08",
    "P09",
    "P10",
    "P11",
    "P12",
    "P13",
    "P14",
    "P15",
)
PILOT_STATUSES = {"pending", "running", "ready", "warn", "blocked", "skipped"}
# Orthogonal, append-only freshness flag (schema v2). Kept separate from the 6
# primary statuses so the status enum / pilot_summary stay backward compatible.
PILOT_FRESHNESS = {"fresh", "stale"}
DEFAULT_PATTERN = "{serial}--{line}.pdf"


def build_pilot_report(
    *,
    request: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    plan = _plan_payload(plan, job)
    source = _source_payload(request, plan)
    plan_source = dict(plan.get("source") if isinstance(plan.get("source"), dict) else {})
    rows = _rows_payload(plan, job, request)
    summary = _summary_payload(plan, job, rows)
    issues = _issues_payload(plan, job)
    items = _build_items(
        request=request,
        source=source,
        plan_source=plan_source,
        rows=rows,
        summary=summary,
        issues=issues,
        job=job or {},
    )
    return {
        "schema_version": PILOT_SCHEMA_VERSION,
        "action": "pilot_report",
        "created_at": _now(),
        "summary": _status_counts(items),
        "items": items,
    }


def _build_items(
    *,
    request: dict[str, Any],
    source: dict[str, Any],
    plan_source: dict[str, Any],
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    issues: list[dict[str, Any]],
    job: dict[str, Any],
) -> list[dict[str, Any]]:
    pdf_count = _int_value(source.get("pdf_count"), len(rows))
    record_count = _int_value(source.get("record_count"), 0)
    pattern = str(source.get("pattern") or request.get("pattern") or DEFAULT_PATTERN)
    detect_serials = _bool_value(source.get("detect_serials"), request.get("detect_serials"))
    status_counts = Counter(str(row.get("status") or "") for row in rows)
    serials = [str(row.get("serial") or "").strip() for row in rows]
    line_values = [str(row.get("line_no") or "").strip() for row in rows]
    duplicate_serials = sorted(serial for serial, count in Counter(serial for serial in serials if serial).items() if count > 1)
    missing_serial_rows = [row for row in rows if not str(row.get("serial") or "").strip()]
    missing_line_rows = [row for row in rows if str(row.get("serial") or "").strip() and not str(row.get("line_no") or "").strip()]
    low_confidence_rows = [
        row for row in rows
        if _float_value(row.get("confidence"), 1.0) < _float_value(source.get("confidence_threshold"), 0.70)
        and str(row.get("vision_message") or "").strip()
    ]
    invalid_name_rows = [
        row for row in rows
        if str(row.get("status") or "") == "blocked" and any(token in str(row.get("note") or "") for token in ("檔名", "目標", "invalid"))
    ]
    selected_count = _int_value(summary.get("selected"), sum(1 for row in rows if row.get("selected")))
    blocked_count = _int_value(summary.get("blocked"), status_counts["blocked"])
    warn_count = _int_value(summary.get("warn"), status_counts["warn"])
    job_state = str(job.get("state") or "")
    confidence_values = [
        _float_value(row.get("confidence"), 0.0)
        for row in rows
        if str(row.get("vision_message") or "").strip()
    ]
    avg_confidence = sum(confidence_values) / len(confidence_values) if confidence_values else 0.0
    low_ratio = (len(low_confidence_rows) / len(rows)) if rows else 0.0
    roi_status = (
        "skipped" if not detect_serials
        else "pending" if not rows
        else "blocked" if low_ratio > 0.50
        else "warn" if low_confidence_rows
        else "ready"
    )
    roi_text = (
        "影像判讀未啟用。" if roi_status == "skipped"
        else "尚未有判讀資料。" if roi_status == "pending"
        else "判讀品質良好。" if roi_status == "ready"
        else f"{len(low_confidence_rows)} 頁低於門檻，需確認（平均信心 {avg_confidence:.0%}）。"
    )
    profile = source.get("profile") if isinstance(source.get("profile"), dict) else {}
    missing_profile_paths = [
        key for key in ("iso_list", "page_folder", "combine_pdf")
        if str(source.get(key) or "").strip() and not _path_exists(source.get(key))
    ]
    draft_mismatch = bool(profile.get("draft_exists")) and not bool(profile.get("published_exists"))
    profile_status = "blocked" if missing_profile_paths else "warn" if draft_mismatch else "ready"
    freshness_changed = _changed_source_keys(request, plan_source)
    is_replay = str((job or {}).get("action") or plan_source.get("action") or "").endswith("replay_run_log")
    draft_stale = bool(freshness_changed) or is_replay

    return [
        _item(
            "P01",
            "input",
            "ready" if _has_input_source(request, source) else "blocked",
            "已定位來源。" if _has_input_source(request, source) else "尚未選擇工作資料夾、Combine PDF 或 Page folder。",
            engineer_detail=f"candidates={_compact_paths(request, source)}",
            metrics={"has_source": _has_input_source(request, source)},
            manual_hint="選擇工作資料夾或 PDF 來源。",
            blocks_apply=not _has_input_source(request, source),
            issue_codes=_issue_codes(issues, stage="source"),
        ),
        _item(
            "P02",
            "pdf_source",
            "ready" if pdf_count > 0 else "blocked",
            f"PDF 來源共 {pdf_count} 頁/檔。" if pdf_count > 0 else "找不到可命名的 PDF 頁面。",
            engineer_detail=f"kind={source.get('kind', '')}; page_folder={source.get('page_folder', '')}",
            metrics={"pdf_count": pdf_count},
            manual_hint="檢查 Combine PDF 是否可讀，或改選 Page folder。",
            blocks_apply=pdf_count <= 0,
            issue_codes=_issue_codes(issues, stage="pdf"),
        ),
        _item(
            "P03",
            "split",
            "ready" if pdf_count > 0 else "blocked",
            "拆頁/頁面來源可用。" if pdf_count > 0 else "拆頁結果不可用。",
            engineer_detail=f"source_kind={source.get('kind', '')}",
            metrics={"pdf_count": pdf_count, "page_folder_exists": _path_exists(source.get("page_folder"))},
            auto_fix="重新執行 split_pdf 或改用既有 page folder。",
            manual_hint="確認 pages 資料夾或 Combine PDF。",
            blocks_apply=pdf_count <= 0,
            issue_codes=_issue_codes(issues, stage="split"),
        ),
        _item(
            "P04",
            "iso_list",
            "ready" if record_count > 0 else "blocked" if source.get("iso_list") else "pending",
            f"ISO List 讀到 {record_count} 筆。" if record_count > 0 else "ISO List 尚未有可用資料。",
            engineer_detail=f"iso_list={source.get('iso_list', '')}; sheet={source.get('sheet_name', '')}",
            metrics={"record_count": record_count, "candidate_count": len(source.get("iso_candidates") or [])},
            manual_hint="檢查 sheet、header、流水號欄與圖號欄。",
            blocks_apply=record_count <= 0,
            issue_codes=_issue_codes(issues, stage="iso"),
        ),
        _item(
            "P05",
            "mapping",
            "ready" if source.get("serial_col") is not None and source.get("line_col") is not None else "warn" if record_count else "pending",
            "欄位對應已決定。" if source.get("serial_col") is not None and source.get("line_col") is not None else "欄位對應尚未明確。",
            engineer_detail=f"serial_col={source.get('serial_col')}; line_col={source.get('line_col')}; headers={source.get('headers', [])}",
            metrics={"serial_col": source.get("serial_col"), "line_col": source.get("line_col")},
            auto_fix="使用 guess_iso_columns 自動推測。",
            manual_hint="在調校頁手動選流水號欄與圖號欄。",
            blocks_apply=False,
            issue_codes=_issue_codes(issues, stage="mapping"),
        ),
        _item(
            "P06",
            "serial_detection",
            "running" if job_state in {"queued", "running", "cancel_requested"} else "skipped" if not detect_serials else "warn" if low_confidence_rows else "ready" if rows else "pending",
            "影像判讀未啟用。" if not detect_serials else f"低信心 {len(low_confidence_rows)} 筆。" if low_confidence_rows else "流水號判讀可用。",
            engineer_detail=f"detect_serials={detect_serials}; threshold={source.get('confidence_threshold', 0.70)}",
            metrics={"low_confidence": len(low_confidence_rows), "row_count": len(rows)},
            auto_fix="二階段 ROI/ISO lookup 校正。",
            manual_hint="到調校頁調整 ROI 或降低門檻後重跑。",
            blocks_apply=False,
            issue_codes=_issue_codes(issues, stage="vision"),
        ),
        _item(
            "P07",
            "iso_correction",
            "blocked" if missing_line_rows else "ready" if rows else "pending",
            f"{len(missing_line_rows)} 筆流水號找不到 ISO 對應。" if missing_line_rows else "ISO 對應完成。" if rows else "尚未建立命名列。",
            engineer_detail=f"missing_line_pages={_pages(missing_line_rows)}",
            metrics={"missing_line": len(missing_line_rows), "mapped_line": sum(1 for value in line_values if value)},
            auto_fix="correct_result_with_iso_lookup。",
            manual_hint="手動修正流水號或 ISO List 欄位。",
            blocks_apply=bool(missing_line_rows),
            issue_codes=_issue_codes(issues, stage="correction"),
        ),
        _item(
            "P08",
            "duplicates",
            "blocked" if duplicate_serials else "ready" if rows else "pending",
            f"流水號重複：{', '.join(duplicate_serials)}" if duplicate_serials else "沒有重複流水號。" if rows else "尚未可檢查重複。",
            engineer_detail=f"duplicates={duplicate_serials}",
            metrics={"duplicate_count": len(duplicate_serials)},
            manual_hint="檢查重複頁的判讀值或 ISO List。",
            blocks_apply=bool(duplicate_serials),
            issue_codes=[],
        ),
        _item(
            "P09",
            "missing_serial",
            "blocked" if missing_serial_rows else "ready" if rows else "pending",
            f"{len(missing_serial_rows)} 筆缺流水號。" if missing_serial_rows else "沒有缺流水號。" if rows else "尚未可檢查缺漏。",
            engineer_detail=f"missing_serial_pages={_pages(missing_serial_rows)}",
            metrics={"missing_serial": len(missing_serial_rows), "pdf_count": pdf_count, "record_count": record_count},
            manual_hint="手動填入流水號或重新判讀該頁。",
            blocks_apply=bool(missing_serial_rows),
            issue_codes=[],
        ),
        _item(
            "P10",
            "naming_pattern",
            "blocked" if invalid_name_rows else "warn" if not _pattern_has_tokens(pattern) else "ready",
            "命名格式可用。" if _pattern_has_tokens(pattern) and not invalid_name_rows else "命名格式需要檢查。",
            engineer_detail=f"pattern={pattern}; invalid_rows={_pages(invalid_name_rows)}",
            metrics={"invalid_name": len(invalid_name_rows), "has_serial_token": "{serial}" in pattern, "has_line_token": "{line}" in pattern},
            manual_hint="確認 pattern 至少包含 {serial} 或 {line}，且不會產生非法檔名。",
            blocks_apply=bool(invalid_name_rows),
            issue_codes=_issue_codes(issues, stage="naming"),
        ),
        _item(
            "P11",
            "rename_draft",
            "ready" if rows and selected_count > 0 else "warn" if rows else "pending",
            f"命名草稿已建立，選取 {selected_count} 筆。" if rows else "尚未產生命名草稿。",
            engineer_detail=f"rows={len(rows)}; selected={selected_count}",
            metrics={"rows": len(rows), "selected": selected_count},
            auto_fix="build_rename_plan。",
            manual_hint="產生命名草稿後檢查問題列。",
            blocks_apply=False,
            issue_codes=[],
        ),
        _item(
            "P12",
            "apply_readiness",
            "blocked" if blocked_count else "warn" if warn_count else "ready" if selected_count else "pending",
            f"{blocked_count} 筆 blocked，禁止套用。" if blocked_count else f"{warn_count} 筆 warn 需要確認。" if warn_count else "可套用。" if selected_count else "沒有可套用列。",
            engineer_detail=f"summary={summary}",
            metrics={"ready": _int_value(summary.get("ready"), status_counts["ready"]), "warn": warn_count, "blocked": blocked_count, "selected": selected_count},
            manual_hint="先處理 blocked，warn 需確認後才套用。",
            blocks_apply=bool(blocked_count),
            issue_codes=_issue_codes(issues, stage="apply"),
        ),
        _item(
            "P13",
            "roi_confidence",
            roi_status,
            roi_text,
            engineer_detail=f"avg={avg_confidence:.3f}; low_ratio={low_ratio:.2f}; low={len(low_confidence_rows)}",
            metrics={"avg_confidence": avg_confidence, "low_ratio": low_ratio, "low": len(low_confidence_rows)},
            auto_fix="重新自動校準 ROI 或降低門檻。",
            manual_hint="到調校調整 ROI / 門檻。",
            blocks_apply=False,
            next_action={"label": "到調校檢查判讀品質", "view": "engineer", "anchor": "roi"},
        ),
        _item(
            "P14",
            "profile_consistency",
            profile_status,
            f"設定指向的檔案不存在：{', '.join(missing_profile_paths)}" if missing_profile_paths else "草稿尚未發布到一鍵。" if draft_mismatch else "Profile 一致。",
            engineer_detail=f"missing={missing_profile_paths}; draft_mismatch={draft_mismatch}",
            metrics={"missing": len(missing_profile_paths), "draft_mismatch": draft_mismatch},
            manual_hint="到調校重新選來源或發布草稿。",
            blocks_apply=bool(missing_profile_paths),
            next_action={"label": "到調校檢查 Profile", "view": "engineer", "anchor": "profile"},
        ),
        _item(
            "P15",
            "draft_freshness",
            "warn" if draft_stale else "ready",
            "設定已變更，草稿可能過期，建議重新產生。" if draft_stale else "草稿與目前設定一致。",
            engineer_detail=f"changed={freshness_changed}; replay={is_replay}",
            metrics={"changed": freshness_changed, "replay": is_replay},
            freshness="stale" if draft_stale else "fresh",
            manual_hint="重新產生命名草稿。",
            blocks_apply=False,
            next_action={"label": "重新產生草稿", "view": "workbench", "anchor": "dryrun"},
        ),
    ]


def _item(
    item_id: str,
    stage: str,
    status: str,
    user_text: str,
    *,
    engineer_detail: str = "",
    metrics: dict[str, Any] | None = None,
    auto_fix: str = "",
    manual_hint: str = "",
    blocks_apply: bool = False,
    issue_codes: list[str] | None = None,
    freshness: str = "fresh",
    needs_review: bool = False,
    next_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in PILOT_STATUSES:
        raise ValueError(f"Unsupported pilot status: {status}")
    if freshness not in PILOT_FRESHNESS:
        raise ValueError(f"Unsupported pilot freshness: {freshness}")
    return {
        "id": item_id,
        "stage": stage,
        "status": status,
        "user_text": user_text,
        "engineer_detail": engineer_detail,
        "metrics": metrics or {},
        "auto_fix": auto_fix,
        "manual_hint": manual_hint,
        "blocks_apply": blocks_apply,
        "issue_codes": issue_codes or [],
        # --- schema v2 additive fields (safe defaults; old readers ignore) ---
        "freshness": freshness,
        "needs_review": bool(needs_review),
        "next_action": next_action,
    }


def _plan_payload(plan: dict[str, Any] | None, job: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(plan, dict):
        return plan
    if isinstance(job, dict) and isinstance(job.get("result"), dict):
        return dict(job["result"])
    return {}


def _source_payload(request: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    source = dict(plan.get("source") if isinstance(plan.get("source"), dict) else {})
    for key in (
        "work_folder",
        "combine_pdf",
        "page_folder",
        "iso_list",
        "sheet_name",
        "serial_col",
        "line_col",
        "pattern",
        "detect_serials",
        "confidence_threshold",
    ):
        if source.get(key) in (None, "") and request.get(key) not in (None, ""):
            source[key] = request.get(key)
    return source


def _rows_payload(plan: dict[str, Any], job: dict[str, Any] | None, request: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("rows")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    if isinstance(job, dict) and isinstance(job.get("rows"), list):
        return [dict(row) for row in job["rows"] if isinstance(row, dict)]
    if isinstance(request.get("rows"), list):
        return [dict(row) for row in request["rows"] if isinstance(row, dict)]
    return []


def _summary_payload(plan: dict[str, Any], job: dict[str, Any] | None, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(plan.get("summary"), dict):
        return dict(plan["summary"])
    if isinstance(job, dict) and isinstance(job.get("progress"), dict):
        return {"progress": dict(job["progress"])}
    counter = Counter(str(row.get("status") or "") for row in rows)
    return {
        "total": len(rows),
        "ready": counter["ready"],
        "warn": counter["warn"],
        "blocked": counter["blocked"],
        "selected": sum(1 for row in rows if row.get("selected")),
    }


def _issues_payload(plan: dict[str, Any], job: dict[str, Any] | None) -> list[dict[str, Any]]:
    issues = plan.get("issues")
    if isinstance(issues, list):
        return [dict(issue) for issue in issues if isinstance(issue, dict)]
    if isinstance(job, dict) and isinstance(job.get("issues"), list):
        return [dict(issue) for issue in job["issues"] if isinstance(issue, dict)]
    return []


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(str(item.get("status") or "") for item in items)
    return {status: counter[status] for status in sorted(PILOT_STATUSES)}


def _has_input_source(request: dict[str, Any], source: dict[str, Any]) -> bool:
    return any(
        bool(source.get(key) or request.get(key))
        for key in ("work_folder", "combine_pdf", "page_folder")
    )


def _compact_paths(request: dict[str, Any], source: dict[str, Any]) -> dict[str, str]:
    return {
        key: str(source.get(key) or request.get(key) or "")
        for key in ("work_folder", "combine_pdf", "page_folder", "iso_list")
    }


def _issue_codes(issues: list[dict[str, Any]], *, stage: str) -> list[str]:
    stage_text = stage.casefold()
    codes: list[str] = []
    for issue in issues:
        text = " ".join(str(issue.get(key) or "") for key in ("code", "title", "detail")).casefold()
        if stage_text in text:
            codes.append(str(issue.get("code") or issue.get("title") or stage))
    return codes[:8]


def _pages(rows: list[dict[str, Any]]) -> list[int]:
    pages: list[int] = []
    for row in rows:
        page = _int_value(row.get("page"), -1)
        if page >= 0:
            pages.append(page)
    return pages[:20]


def _path_exists(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and Path(text).exists()


def _changed_source_keys(request: dict[str, Any], plan_source: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key in (
        "sheet_name",
        "serial_col",
        "line_col",
        "pattern",
        "confidence_threshold",
        "serial_region",
        "drawing_region",
    ):
        request_value = request.get(key)
        if request_value in (None, ""):
            continue
        if not _values_match(request_value, plan_source.get(key)):
            changed.append(key)
    return changed


def _values_match(left: Any, right: Any) -> bool:
    return _stable_value(left) == _stable_value(right)


def _stable_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _pattern_has_tokens(pattern: str) -> bool:
    return "{serial}" in pattern or "{line}" in pattern


def _bool_value(*values: Any) -> bool:
    for value in values:
        if value not in (None, ""):
            return bool(value)
    return False


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
